from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
import requests
from loguru import logger

BASE_URLS = {
    "live": "https://api.india.delta.exchange",
    "demo": "https://cdn-ind.testnet.deltaex.org",
}


class DeltaAPIError(Exception):
    pass


@dataclass
class InstrumentInfo:
    product_id: int
    symbol: str
    tick_size: float
    contract_value: float  # e.g., 0.001 BTC per contract for BTCUSD


class DeltaAdapter:
    def __init__(self, api_key: str, api_secret: str, mode: str = "demo", user_agent: str = "python-3.10") -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = BASE_URLS.get(mode, BASE_URLS["demo"])  # default demo
        self.user_agent = user_agent

    # --- low level ---
    def _headers(self, signature: str, timestamp: str) -> Dict[str, str]:
        return {
            "api-key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _sign(self, method: str, path: str, query_string: str, payload: str) -> Dict[str, str]:
        import hmac, hashlib

        ts = str(int(time.time()))
        signature_data = method + ts + path + query_string + payload
        digest = hmac.new(self.api_secret.encode(), signature_data.encode(), hashlib.sha256).hexdigest()
        return {"signature": digest, "timestamp": ts}

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None, auth: bool = False) -> Any:
        url = f"{self.base_url}{path}"
        query_string = ""
        payload = ""
        if json is not None:
            import json as _json
            payload = _json.dumps(json, separators=(",", ":"))
        if params:
            from urllib.parse import urlencode
            query_string = "?" + urlencode(params)
        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if auth:
            sig = self._sign(method, path, query_string, payload)
            headers = self._headers(sig["signature"], sig["timestamp"])  # includes UA and content-type
        resp = requests.request(method, url, params=params, data=payload if payload else None, headers=headers, timeout=(5, 30))
        if resp.status_code == 429:
            raise DeltaAPIError(f"Rate limited: {resp.text}")
        if not resp.ok:
            raise DeltaAPIError(f"HTTP {resp.status_code}: {resp.text}")
        data = resp.json()
        if isinstance(data, dict) and data.get("success") is False:
            raise DeltaAPIError(str(data))
        return data

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
