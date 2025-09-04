import json
import threading
import time
import websocket
import logging
from typing import Optional, Dict


class DeltaWSClient:
    """Minimal WebSocket client for Delta 'mark_price' public channel."""

    def __init__(self, use_testnet: bool = False):
        self.ws_url = (
            "wss://socket-ind.testnet.deltaex.org" if use_testnet else "wss://socket.india.delta.exchange"
        )
        self.ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._latest_mark: Dict[str, float] = {}
        self._connected = threading.Event()
        self._stop = threading.Event()
        self.logger = logging.getLogger(__name__)

    def _on_open(self, ws):
        self.logger.info("WebSocket opened")
        self._connected.set()

    def _on_close(self, ws, status_code, msg):
        self.logger.info(f"WebSocket closed: {status_code} {msg}")
        self._connected.clear()

    def _on_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        if data.get("type") == "mark_price":
            symbol = data.get("symbol", "")
            # Symbol comes as MARK:BTCUSD etc.
            price = data.get("price")
            try:
                price_f = float(price) if price is not None else None
            except Exception:
                price_f = None
            if symbol.startswith("MARK:") and price_f:
                product = symbol.split(":", 1)[1]
                with self._lock:
                    self._latest_mark[product] = price_f

    def connect(self):
        self._stop.clear()
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_close=self._on_close,
            on_error=self._on_error,
            on_message=self._on_message,
        )
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()
        # Wait briefly for connection
        self._connected.wait(timeout=3.0)
        return self

    def _run_forever(self):
        while not self._stop.is_set():
            try:
                if self.ws is None:
                    # Recreate WS app if needed
                    self.ws = websocket.WebSocketApp(
                        self.ws_url,
                        on_open=self._on_open,
                        on_close=self._on_close,
                        on_error=self._on_error,
                        on_message=self._on_message,
                    )
                self.ws.run_forever(ping_interval=25, ping_timeout=5)
            except Exception as e:
                self.logger.error(f"WS run_forever error: {e}")
                time.sleep(1)
            if not self._stop.is_set():
                # try reconnect after brief backoff
                time.sleep(2)

    def subscribe_mark(self, symbols: list[str]):
        if not self.ws:
            return
        payload = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {
                        "name": "mark_price",
                        "symbols": [f"MARK:{s}" for s in symbols],
                    }
                ]
            },
        }
        try:
            self.ws.send(json.dumps(payload))
        except Exception as e:
            self.logger.error(f"WS subscribe error: {e}")

    def get_latest_mark(self, symbol: str) -> Optional[float]:
        with self._lock:
            return self._latest_mark.get(symbol)

    # Backward-compatible alias used in older code/logs
    def get_latest_mark_price(self, symbol: str) -> Optional[float]:
        return self.get_latest_mark(symbol)

    def close(self):
        self._stop.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        self._connected.clear()
