import json
import threading
import time
import logging
import hmac
import hashlib
import os
from typing import Optional, Dict, Any, List
import socket
from urllib.parse import urlparse

try:
    import websocket  # type: ignore
except Exception:  # pragma: no cover - imported at runtime in app
    websocket = None  # type: ignore


class DeltaWSClient:
    """
    Delta Exchange WebSocket client supporting:
    - Public mark_price subscriptions
    - Optional private authentication + subscriptions to orders and positions

    Thread-safe, reconnecting, and stateful. Intended for use as a singleton in Streamlit via @st.cache_resource.
    """

    def __init__(self):
        # Prefer explicit env override, else infer from BASE_URL (prod vs testnet)
        base_env = os.getenv("DELTA_BASE_URL", "").lower()
        explicit_ws = os.getenv("DELTA_WS_URL")
        if explicit_ws:
            self.ws_url = explicit_ws
        else:
            if "testnet" in base_env:
                self.ws_url = "wss://socket-ind.testnet.deltaex.org"
            else:
                self.ws_url = "wss://socket.india.delta.exchange"
        self.ws = None
        self._thread = None

        # IPv4 enforcement flag; implemented via getaddrinfo monkeypatch in run loop
        self._force_ipv4 = os.getenv("DELTA_FORCE_IPV4", "false").lower() in {"1", "true", "yes", "on"}

        # Runtime flags/events
        self._connected_evt = threading.Event()
        self._stop_evt = threading.Event()
        self.is_connected = False
        self.is_authenticated = False

        # Locks and state stores
        self._lock = threading.Lock()
        self._latest_mark = {}
        self._positions = {}
        self._orders = {}

        # Pending outbound messages (subscribe, etc.) queued until connected/authenticated
        self._outbox = []

        # Auth creds (optional)
        self._api_key = None
        self._api_secret = None

        self.logger = logging.getLogger(__name__)

    # ---------- Public API ----------
    def configure_auth(self, api_key: Optional[str], api_secret: Optional[str]):
        """Optionally set API key/secret for private channels."""
        self._api_key = api_key
        self._api_secret = api_secret

    def connect(self):
        """Connect WS in a background thread and authenticate (if creds present)."""
        if websocket is None:
            raise RuntimeError("websocket-client is not installed")

        if self._thread and self._thread.is_alive():
            return self

        self._stop_evt.clear()
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_close=self._on_close,
            on_error=self._on_error,
            on_message=self._on_message,
        )

        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()
        self._connected_evt.wait(timeout=5.0)
        return self

    def close(self):
        self._stop_evt.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        self._connected_evt.clear()

    # Subscriptions
    def subscribe_mark(self, symbols: List[str]):
        # Subscribe to both mark_price and ticker as a fallback in case one channel is unavailable
        channels = [
            {"name": "mark_price", "symbols": [f"MARK:{s}" for s in symbols]},
            {"name": "ticker", "symbols": symbols},
        ]
        payload = {"type": "subscribe", "payload": {"channels": channels}}
        if os.getenv("DELTA_WS_DEBUG", "false").lower() in {"1", "true", "yes"}:
            try:
                self.logger.info(f"WS send subscribe payload={payload}")
            except Exception:
                pass
        self._send_or_queue(payload)

    def subscribe_private_channels(self):
        """Subscribe to private orders and positions after successful auth."""
        subs = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {"name": "orders", "symbols": ["all"]},
                    {"name": "positions", "symbols": ["all"]},
                ]
            },
        }
        self._send_or_queue(subs)

    def enable_heartbeat(self):
        """Ask server to send heartbeat messages periodically."""
        hb = {"type": "enable_heartbeat"}
        self._send_or_queue(hb, require_auth=False)

    # Safe getters
    def get_latest_mark(self, symbol: str) -> Optional[float]:
        with self._lock:
            return self._latest_mark.get(symbol)

    def get_positions(self) -> Dict[str, Any]:
        with self._lock:
            # Return shallow copy to avoid cross-thread mutation
            return {k: dict(v) for k, v in self._positions.items()}

    def get_orders(self) -> Dict[str, Any]:
        with self._lock:
            return {k: dict(v) for k, v in self._orders.items()}

    # Backward-compatible alias used in older code/logs
    def get_latest_mark_price(self, symbol: str) -> Optional[float]:
        return self.get_latest_mark(symbol)

    # ---------- Internals ----------
    def _run_forever(self):
        assert self.ws is not None
        while not self._stop_evt.is_set():
            try:
                if self._force_ipv4:
                    orig_getaddrinfo = socket.getaddrinfo
                    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):  # noqa: ANN001
                        res = orig_getaddrinfo(host, port, family, type, proto, flags)
                        ipv4_res = [r for r in res if r and r[0] == socket.AF_INET]
                        return ipv4_res or res
                    try:
                        socket.getaddrinfo = ipv4_only  # type: ignore[assignment]
                        self.ws.run_forever(ping_interval=25, ping_timeout=10)
                    finally:
                        socket.getaddrinfo = orig_getaddrinfo  # type: ignore[assignment]
                else:
                    self.ws.run_forever(ping_interval=25, ping_timeout=10)
            except Exception as e:
                self.logger.error(f"WS run_forever error: {e}")
                time.sleep(2)
            if not self._stop_evt.is_set():
                time.sleep(1)

    def _on_open(self, ws):  # noqa: ANN001
        if os.getenv("DELTA_ACTION_LOG_ONLY", "true").lower() in {"1","true","yes","on"}:
            self.logger.debug("WebSocket opened")
        else:
            self.logger.info("WebSocket opened")
        self.is_connected = True
        self._connected_evt.set()

        # If creds were provided, authenticate immediately
        if self._api_key and self._api_secret:
            try:
                self._send_auth(ws)
            except Exception as e:
                self.logger.error(f"Failed to send auth: {e}")

        # Enable heartbeat to detect connection drops reliably
        try:
            self.enable_heartbeat()
        except Exception:
            pass

        # Flush any queued messages (e.g., public subscriptions)
        self._flush_outbox(ws)

    def _on_close(self, ws, status_code, msg):  # noqa: ANN001
        if os.getenv("DELTA_ACTION_LOG_ONLY", "true").lower() in {"1","true","yes","on"}:
            self.logger.debug(f"WebSocket closed: {status_code} {msg}")
        else:
            self.logger.info(f"WebSocket closed: {status_code} {msg}")
        self.is_connected = False
        self.is_authenticated = False
        self._connected_evt.clear()

    def _on_error(self, ws, error):  # noqa: ANN001
        self.logger.error(f"WebSocket error: {error}")

    def _on_message(self, ws, message):  # noqa: ANN001
        try:
            data = json.loads(message)
        except Exception:
            return

        if not isinstance(data, dict):
            return

        mtype = data.get("type")

        # Optional raw debug
        if os.getenv("DELTA_WS_DEBUG", "false").lower() in {"1", "true", "yes"}:
            try:
                self.logger.debug(f"WS recv type={mtype} keys={list(data.keys())[:6]} raw={str(data)[:240]}")
            except Exception:
                pass

        # Auth success
        if mtype == "success" and data.get("message") == "Authenticated":
            self.is_authenticated = True
            # Subscribe to private channels now
            self.subscribe_private_channels()
            return

        # Heartbeat or housekeeping types can be ignored
        if mtype in {"heartbeat", "subscriptions"}:
            return

        # Public mark price
        if mtype == "mark_price":
            symbol = data.get("symbol", "")
            price = data.get("price")
            if isinstance(symbol, str) and symbol.startswith("MARK:") and price is not None:
                try:
                    price_f = float(price)
                except Exception:
                    price_f = None
                if price_f is not None:
                    core = symbol.split(":", 1)[1]
                    with self._lock:
                        self._latest_mark[core] = price_f
            return

        # Some deployments may use ticker channel name variations; capture them if present
        if mtype in {"ticker", "v2/ticker"}:
            # Attempt to normalise to mark price if mark field provided
            try:
                symbol = data.get("symbol") or data.get("product_symbol")
                mark_price = data.get("mark_price") or data.get("mark")
                if symbol and mark_price is not None:
                    core = str(symbol).replace("MARK:", "")
                    price_f = None
                    try:
                        price_f = float(mark_price)
                    except Exception:
                        pass
                    if price_f is not None:
                        with self._lock:
                            self._latest_mark[core] = price_f
            except Exception:
                pass
            return

        # Private: positions updates
        if mtype == "positions":
            # Data shape may vary; normalize to list of position dicts
            payload = data.get("result") or data.get("positions") or data.get("data") or data
            items: List[Dict[str, Any]]
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict):
                items = [payload]
            else:
                items = []
            with self._lock:
                for pos in items:
                    sym = str(pos.get("product_symbol") or pos.get("symbol") or "").strip()
                    if not sym:
                        continue
                    self._positions[sym] = pos
            return

        # Private: orders updates
        if mtype == "orders":
            payload = data.get("result") or data.get("orders") or data.get("data") or data
            items2: List[Dict[str, Any]]
            if isinstance(payload, list):
                items2 = payload
            elif isinstance(payload, dict):
                items2 = [payload]
            else:
                items2 = []
            with self._lock:
                for od in items2:
                    oid = od.get("id") or od.get("order_id")
                    if oid is None:
                        continue
                    key = str(oid)
                    state = (od.get("state") or "").lower()
                    if state in {"cancelled", "filled", "closed"}:
                        # Remove from open orders map if present
                        if key in self._orders:
                            try:
                                del self._orders[key]
                            except Exception:
                                pass
                    else:
                        self._orders[key] = od
            return

    # Utilities
    def _send_auth(self, ws):  # noqa: ANN001
        if not (self._api_key and self._api_secret):
            return
        method = "GET"
        timestamp = str(int(time.time()))
        path = "/live"
        message = method + timestamp + path
        try:
            sig = hmac.new(
                self._api_secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        except Exception as e:
            self.logger.error(f"Auth signature failed: {e}")
            return
        payload = {
            "type": "auth",
            "payload": {
                "api-key": self._api_key,
                "signature": sig,
                "timestamp": timestamp,
            },
        }
        self._send_or_queue(payload, require_auth=False)  # can send immediately on open

    def _send_or_queue(self, msg: dict, require_auth: bool = True):
        # If WS not connected yet, queue
        if not self.is_connected or not self.ws:
            self._outbox.append(msg)
            return
        # If this message requires auth and we're not yet authenticated, queue
        if require_auth and self._api_key and not self.is_authenticated:
            self._outbox.append(msg)
            return
        try:
            self.ws.send(json.dumps(msg))
        except Exception as e:
            self.logger.error(f"WS send failed, queueing: {e}")
            self._outbox.append(msg)

    def _flush_outbox(self, ws):  # noqa: ANN001
        # Attempt to send queued messages in order
        if not self._outbox:
            return
        pending = list(self._outbox)
        self._outbox.clear()
        for msg in pending:
            try:
                ws.send(json.dumps(msg))
            except Exception as e:
                self.logger.error(f"WS send (flush) failed, requeue: {e}")
                self._outbox.append(msg)

    # No extra helpers needed; IPv4 enforcement is handled in _run_forever
