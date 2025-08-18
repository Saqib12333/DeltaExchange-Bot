from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
import requests
from loguru import logger
import os


class DeltaAPIError(Exception):
    pass


@dataclass
class InstrumentInfo:
    product_id: int
    symbol: str
    tick_size: float
    contract_value: float  # e.g., 0.001 BTC per contract for BTCUSD


class DeltaAdapter:
    def __init__(self, api_key: str, api_secret: str, base_url: Optional[str] = None, user_agent: str = "python-3.10") -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        # Single URL config: use provided base_url, else env, else demo host by default
        self.base_url = (base_url or os.getenv("DELTA_BASE_URL") or "https://cdn-ind.testnet.deltaex.org").rstrip("/")
        # Optional alternate base URL for fallback (e.g., Global testnet). Only used if set via env.
        self.alt_base_url = (os.getenv("DELTA_ALT_BASE_URL") or "").rstrip("/")
        self.user_agent = user_agent
        # Optional subaccount routing: provide subaccount name or id and header key
        self.subaccount = os.getenv("DELTA_SUBACCOUNT") or None
        # Default header name; adjust if the exchange expects a different key
        self.subaccount_header = os.getenv("DELTA_SUBACCOUNT_HEADER") or "X-Subaccount"

    # --- low level ---
    def _headers(self, signature: str, timestamp: str) -> Dict[str, str]:
        headers = {
            "api-key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # Attach subaccount header if configured
        if self.subaccount:
            headers[self.subaccount_header] = self.subaccount
        return headers

    def _sign(self, method: str, path: str, query_string: str, payload: str) -> Dict[str, str]:
        import hmac, hashlib

        ts = str(int(time.time()))
        signature_data = method + ts + path + query_string + payload
        digest = hmac.new(self.api_secret.encode(), signature_data.encode(), hashlib.sha256).hexdigest()
        # Extra debug: log prehash characteristics without exposing secrets
        try:
            prehash_sha = hashlib.sha256(signature_data.encode()).hexdigest()
            logger.debug(
                f"[delta/_sign] method={method} ts={ts} path={path} qlen={len(query_string)} prehash_len={len(signature_data)} prehash_sha256={prehash_sha[:12]} payload_len={len(payload)}"
            )
        except Exception:
            # best-effort logging only
            pass
        return {"signature": digest, "timestamp": ts}

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None, auth: bool = False) -> Any:
        import time as _time
        from urllib.parse import urlencode
        import json as _json
        import hashlib as _hashlib
        url = f"{self.base_url}{path}"
        query_string = ""
        payload = ""
        if json is not None:
            payload = _json.dumps(json, separators=(",", ":"))
        if params:
            query_string = "?" + urlencode(params)

        retry_status = {502, 503, 504, 522, 524}
        attempts = 0
        backoff = 0.6
        last_err: Optional[Exception] = None
        used_alt = False

        while attempts < 4:  # initial try + up to 3 retries
            attempts += 1
            headers = {"Accept": "application/json", "User-Agent": self.user_agent}
            if auth:
                # Extra debug: payload hash/length (no payload content)
                try:
                    p_hash = _hashlib.sha256(payload.encode()).hexdigest() if payload else ""
                    logger.debug(
                        f"[delta/_request] auth request prep method={method} path={path} qlen={len(query_string)} payload_len={len(payload)} payload_sha256={(p_hash[:12] if p_hash else '')}"
                    )
                except Exception:
                    pass
                sig = self._sign(method, path, query_string, payload)
                headers = self._headers(sig["signature"], sig["timestamp"])  # includes UA and content-type
            try:
                logger.debug(f"[delta/_request] -> {method} {url} (attempt {attempts})")
                resp = requests.request(
                    method,
                    url,
                    params=params,
                    data=payload if payload else None,
                    headers=headers,
                    timeout=(5, 30),
                )
            except requests.RequestException as e:
                last_err = e
                if attempts >= 4:
                    break
                _time.sleep(backoff)
                backoff *= 1.8
                continue

            # Handle HTTP responses
            logger.debug(f"[delta/_request] <- status={resp.status_code} url={url}")
            if resp.status_code == 429:
                # Rate limited: honor Retry-After if present
                ra = resp.headers.get("Retry-After")
                delay = float(ra) if ra and ra.isdigit() else backoff
                if attempts >= 4:
                    raise DeltaAPIError(f"Rate limited: {resp.text}")
                _time.sleep(delay)
                backoff *= 1.8
                continue

            if not resp.ok:
                # Non-OK
                if resp.status_code in retry_status and attempts < 4:
                    # transient 5xx; optional alt-host retry for private endpoints if configured
                    if auth and not used_alt and self.alt_base_url and self.alt_base_url != self.base_url:
                        logger.warning(f"{resp.status_code} on {url}; retrying once against alt host {self.alt_base_url}")
                        url = f"{self.alt_base_url}{path}"
                        used_alt = True
                        _time.sleep(backoff)
                        backoff *= 1.4
                        continue
                    _time.sleep(backoff)
                    backoff *= 1.8
                    continue
                # Non-retryable or maxed attempts
                raise DeltaAPIError(f"HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            if isinstance(data, dict) and data.get("success") is False:
                # Treat generic failure as non-retryable unless explicitly 5xx
                raise DeltaAPIError(str(data))
            return data

        # If loop exits without return
        if last_err is not None:
            raise DeltaAPIError(str(last_err))
        raise DeltaAPIError("Request failed after retries")

    # --- high level ---
    def get_product_by_symbol(self, symbol: str) -> InstrumentInfo:
        data = self._request("GET", "/v2/products/" + symbol, auth=False)
        result = data.get("result") or {}
        try:
            pid = int(result["id"])  # required
            sym = str(result["symbol"])  # required
            tick = float(result.get("tick_size", 0))
            cval = float(result.get("contract_value", 0))
        except Exception as e:
            raise DeltaAPIError(f"Unexpected product payload for {symbol}: {result}") from e
        return InstrumentInfo(
            product_id=pid,
            symbol=sym,
            tick_size=tick,
            contract_value=cval,
        )

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        data = self._request("GET", f"/v2/tickers/{symbol}", auth=False)
        return data.get("result") or {}

    def get_mark_price(self, symbol: str) -> float:
        # Ticker includes mark_price as string
        t = self.get_ticker(symbol)
        mp = t.get("mark_price")
        return float(mp) if mp is not None else float("nan")

    def get_positions(self, product_id: Optional[int] = None, underlying_asset_symbol: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if product_id is not None:
            params["product_id"] = product_id
        if underlying_asset_symbol is not None:
            params["underlying_asset_symbol"] = underlying_asset_symbol
        return self._request("GET", "/v2/positions", params=params, auth=True)

    def get_open_orders(self, product_ids: Optional[str] = None, states: str = "open,pending") -> Dict[str, Any]:
        params: Dict[str, Any] = {"states": states}
        if product_ids:
            params["product_ids"] = product_ids
        return self._request("GET", "/v2/orders", params=params, auth=True)

    def place_limit_order(self, product_id: int, side: str, size: int, limit_price: float, post_only: bool = True, client_order_id: Optional[str] = None, tif: str = "gtc", reduce_only: bool = False) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "product_id": product_id,
            "size": size,
            "side": side,
            "order_type": "limit_order",
            "limit_price": str(limit_price),  # send as string to preserve precision
            "time_in_force": tif,
            "post_only": post_only,
            "reduce_only": reduce_only,
        }
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", "/v2/orders", json=body, auth=True)

    def cancel_order(self, order_id: Optional[int] = None, client_order_id: Optional[str] = None, product_id: Optional[int] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if order_id is not None:
            body["id"] = order_id
        if client_order_id is not None:
            body["client_order_id"] = client_order_id
        if product_id is not None:
            body["product_id"] = product_id
        return self._request("DELETE", "/v2/orders", json=body, auth=True)

    def cancel_all(self, product_id: Optional[int] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if product_id is not None:
            body["product_id"] = product_id
        return self._request("DELETE", "/v2/orders/all", json=body, auth=True)

    def set_order_leverage(self, product_id: int, leverage: int) -> Dict[str, Any]:
        return self._request("POST", f"/v2/products/{product_id}/orders/leverage", json={"leverage": leverage}, auth=True)
