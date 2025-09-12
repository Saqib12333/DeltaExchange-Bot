import hmac
import hashlib
import time
import json
import requests
from typing import Dict, List, Optional, Any
import logging
from functools import wraps
import os
import threading
import queue
import socket

def rate_limit(calls_per_second=10):
    """Rate limiting decorator"""
    def decorator(func):
        last_called = [0.0]
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = 1.0 / calls_per_second - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

class DeltaExchangeClient:
    """
    Delta Exchange API Client for portfolio management and trading
    """
    
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://api.india.delta.exchange"):
        """
        Initialize the Delta Exchange client
        
        Args:
            api_key: Your Delta Exchange API key
            api_secret: Your Delta Exchange API secret
            base_url: Base URL for the API (production or testnet)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip('/')

        # Optionally force IPv4 for all outbound requests to avoid IPv6-only egress
        # triggering ip_not_whitelisted_for_api_key on exchanges that whitelist IPv4s.
        force_ipv4 = os.getenv('DELTA_FORCE_IPV4', 'false').lower() in ('1', 'true', 'yes', 'on')
        if force_ipv4:
            try:
                import urllib3.util.connection as urllib3_cn  # type: ignore

                def allowed_gai_family() -> int:  # pragma: no cover - simple monkeypatch
                    return socket.AF_INET

                # Monkeypatch urllib3 to only use IPv4 address family
                urllib3_cn.allowed_gai_family = allowed_gai_family  # type: ignore[attr-defined]
            except Exception as e:
                # Logger not yet set; use root logger to avoid missing early errors
                logging.getLogger(__name__).warning(f"Failed to enforce IPv4 (continuing with default): {e}")

        self.session = requests.Session()
        # Set default timeout for requests
        self.timeout = 30
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def _generate_signature(self, method: str, path: str, query_string: str = '', body: str = '') -> tuple:
        """
        Generate signature for API authentication
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            query_string: Query parameters
            body: Request body
            
        Returns:
            Tuple of (signature, timestamp)
        """
        timestamp = str(int(time.time()))
        # Per server context, include '?' when query params are present
        if query_string:
            message = method + timestamp + path + '?' + query_string + body
        else:
            message = method + timestamp + path + body
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Optional debug for auth issues
        if os.getenv('DELTA_DEBUG_AUTH', 'false').lower() == 'true':
            try:
                self.logger.info(f"Signature debug -> method={method}, timestamp={timestamp}, path={path}, query='{query_string}', body='{body}', signature_data='{message}'")
            except Exception:
                pass

        return signature, timestamp
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                     data: Optional[Dict] = None, *, suppress_log: bool = False) -> Dict[str, Any]:
        """
        Make authenticated request to Delta Exchange API
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            
        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}{endpoint}"
        query_string = ''
        body = ''

        if params:
            # Properly format query string for Delta API
            query_params = []
            for k, v in params.items():
                query_params.append(f"{k}={v}")
            # Build query pieces in insertion order
            query_string = '&'.join(query_params)
            # For URL construction: include the '?' character
            url = f"{url}?{query_string}"

        # Prepare body exactly once and reuse for signing AND sending
        if data is not None:
            # Use compact JSON so we can sign and send the exact same bytes
            body = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

        # Determine if this endpoint is public (no auth headers needed)
        is_public_get = (
            method == 'GET' and (
                endpoint.startswith('/v2/products') or
                endpoint.startswith('/v2/history') or
                (endpoint.endswith('/orders') and '/v2/products/' in endpoint)  # product orderbook
            )
        )

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'DeltaBot/3.1 cancel-diagnostics'
        }

        # Only sign/authenticate non-public endpoints
        if not is_public_get:
            signature, timestamp = self._generate_signature(method, endpoint, query_string, body)
            headers.update({
                'api-key': self.api_key,
                'signature': signature,
                'timestamp': timestamp,
            })

        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, timeout=self.timeout)
            elif method == 'POST':
                response = self.session.post(url, headers=headers, data=body if body else None, timeout=self.timeout)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers, data=body if body else None, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            if not suppress_log:
                self.logger.error(f"API request failed: {e}")
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            text = None
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    if not suppress_log:
                        self.logger.error(f"Error details: {error_data}")
                    return {'success': False, 'status': status, 'error': error_data}
                except Exception:
                    text = e.response.text
                    if os.getenv('DELTA_DEBUG_CANCEL', 'false').lower() in ('1','true','yes','on') and not suppress_log:
                        try:
                            if os.getenv('DELTA_DEBUG_CANCEL', 'false').lower() in ('1','true','yes','on'):
                                self.logger.error(f"[cancel] raw_response status={status} text={text[:400]}")
                        except Exception:
                            pass
                    if not suppress_log:
                        self.logger.error(f"Response content: {text}")
                    return {'success': False, 'status': status, 'error': text}
            return {'success': False, 'status': status, 'error': str(e)}
    
    @rate_limit(calls_per_second=5)
    def get_account_balance(self) -> Dict[str, Any]:
        """
        Get account balance and wallet information
        
        Returns:
            Account balance data
        """
        return self._make_request('GET', '/v2/wallet/balances')
    
    @rate_limit(calls_per_second=5)
    def get_positions(self, product_ids: Optional[List[int]] = None, 
                     underlying_asset_symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current positions
        
        Args:
            product_ids: Optional list of product IDs to filter
            underlying_asset_symbol: Optional underlying asset symbol to filter (e.g., "BTC")
            
        Returns:
            Positions data
        """
        params: Dict[str, Any] = {}
        if product_ids:
            params['product_ids'] = ','.join(map(str, product_ids))
        elif underlying_asset_symbol:
            params['underlying_asset_symbol'] = underlying_asset_symbol
        else:
            # If no filter provided, get all positions by using a common underlying asset
            params['underlying_asset_symbol'] = 'BTC'
        
        return self._make_request('GET', '/v2/positions', params=params)
    
    @rate_limit(calls_per_second=5)
    def get_orders(self, product_ids: Optional[List[int]] = None,
                   page_size: int = 100,
                   state: str = 'open') -> Dict[str, Any]:
        """
        Get orders (defaults to only 'open')

        Args:
            product_ids: Optional list of product IDs to filter
            page_size: Number of orders per page
            state: Filter by state (e.g., 'open', 'filled', 'cancelled'). Default 'open'.

        Returns:
            Orders data
        """
        params: Dict[str, Any] = {'page_size': page_size, 'state': state}
        if product_ids:
            params['product_ids'] = ','.join(map(str, product_ids))
        
        return self._make_request('GET', '/v2/orders', params=params)
    
    def get_products(self, contract_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get all available products
        
        Args:
            contract_types: Optional list of contract types to filter
            
        Returns:
            Products data
        """
        params = {}
        if contract_types:
            params['contract_types'] = ','.join(contract_types)
        
        return self._make_request('GET', '/v2/products', params=params)
    
    def get_product_by_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Get product details by symbol
        
        Args:
            symbol: Product symbol (e.g., "BTCUSD")
            
        Returns:
            Product data
        """
        return self._make_request('GET', f'/v2/products/{symbol}')
    
    @rate_limit(calls_per_second=3)  # More conservative for mark price calls
    def get_mark_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get mark price for a product using historical candles
        
        Args:
            symbol: Product symbol
            
        Returns:
            Mark price data
        """
        try:
            import time
            
            # Use MARK:symbol format to get mark price from candles
            mark_symbol = f"MARK:{symbol}"
            
            # Get current time and 2 minutes ago to ensure we get latest data
            end_time = int(time.time())
            start_time = end_time - 120  # 2 minutes ago
            
            params = {
                'symbol': mark_symbol,
                'resolution': '1m',
                'start': start_time,
                'end': end_time
            }
            
            candles_data = self._make_request('GET', '/v2/history/candles', params=params)
            
            if candles_data.get('success'):
                candles = candles_data.get('result', [])
                if candles:
                    # Get the most recent candle and use its close price as mark price
                    latest_candle = candles[-1]
                    mark_price = float(latest_candle['close'])
                    return {'success': True, 'mark_price': mark_price}
                else:
                    return {'success': False, 'error': 'No candle data available'}
            else:
                return candles_data
                
        except Exception as e:
            self.logger.error(f"Failed to get mark price for {symbol}: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_historical_candles(self, symbol: str, resolution: str = '1m', 
                              start_time: Optional[int] = None, 
                              end_time: Optional[int] = None) -> Dict[str, Any]:
        """
        Get historical OHLC candle data
        
        Args:
            symbol: Product symbol (use "MARK:SYMBOL" for mark price data)
            resolution: Time resolution (1m, 5m, 15m, 1h, 4h, 1d, etc.)
            start_time: Start time (Unix timestamp)
            end_time: End time (Unix timestamp)
            
        Returns:
            Historical candle data
        """
        import time
        
        if not end_time:
            end_time = int(time.time())
        if not start_time:
            start_time = end_time - 3600  # Default to 1 hour ago
            
        params = {
            'symbol': symbol,
            'resolution': resolution,
            'start': start_time,
            'end': end_time
        }
        
        return self._make_request('GET', '/v2/history/candles', params=params)
    
    def get_orderbook(self, symbol: str, depth: int = 20) -> Dict[str, Any]:
        """
        Get orderbook for a product
        
        Args:
            symbol: Product symbol
            depth: Orderbook depth (default: 20, max: 1000)
            
        Returns:
            Orderbook data
        """
        params = {'depth': depth}
        return self._make_request('GET', f'/v2/products/{symbol}/orders', params=params)
    
    def place_order(self, product_id: int, size: int, side: str, 
                   order_type: str = "limit_order", limit_price: Optional[str] = None,
                   time_in_force: str = "gtc", post_only: bool = False,
                   reduce_only: bool = False, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Place a new order
        
        Args:
            product_id: Product ID
            size: Order size in contracts
            side: "buy" or "sell"
            order_type: Order type ("limit_order", "market_order", etc.)
            limit_price: Limit price for limit orders
            time_in_force: Time in force ("gtc", "ioc", "fok")
            post_only: Post-only flag
            reduce_only: Reduce-only flag
            client_order_id: Client-provided order ID
            
        Returns:
            Order placement response
        """
        data = {
            'product_id': product_id,
            'size': size,
            'side': side,
            'order_type': order_type,
            'time_in_force': time_in_force,
            'post_only': post_only,
            'reduce_only': reduce_only
        }
        
        if limit_price:
            data['limit_price'] = limit_price
        if client_order_id:
            data['client_order_id'] = client_order_id
        
        return self._make_request('POST', '/v2/orders', data=data)
    
    def cancel_order(self, order_id: int, *, product_id: Optional[int] = None, product_symbol: Optional[str] = None) -> Dict[str, Any]:
        """Cancel a single order using the observed reliable batch endpoint.

        Strategy:
        1. Use DELETE /v2/orders/batch with {'orders':[{'id': id}], product_symbol|product_id}
        2. If no product context supplied, still attempt batch with only the id list.
        3. OPTIONAL one-shot fallback: path DELETE /v2/orders/{id} (only if batch fails) for forward compatibility.

        Logging: Guarded by DELTA_DEBUG_CANCEL to avoid noisy production logs.
        """
        debug_cancel = os.getenv('DELTA_DEBUG_CANCEL', 'false').lower() in ('1','true','yes','on')

        def dlog(msg: str):
            if debug_cancel:
                try:
                    self.logger.info(f"[cancel] {msg}")
                except Exception:
                    pass

        masked_key = (self.api_key[:4] + '***' + self.api_key[-4:]) if (debug_cancel and self.api_key) else ''
        if debug_cancel:
            dlog(f"start order_id={order_id} product_id={product_id} product_symbol={product_symbol} base_url={self.base_url} api_key={masked_key}")

        # Primary batch attempt with context if provided
        payload: Dict[str, Any] = {'orders': [{'id': order_id}]}
        if product_id:
            payload['product_id'] = product_id
        elif product_symbol:
            payload['product_symbol'] = product_symbol
        batch_resp = self._make_request('DELETE', '/v2/orders/batch', data=payload, suppress_log=True)
        if debug_cancel:
            dlog(f"batch context={'yes' if (product_id or product_symbol) else 'no'} success={getattr(batch_resp, 'get', lambda k: None)('success') if isinstance(batch_resp, dict) else None} status={batch_resp.get('status') if isinstance(batch_resp, dict) else None}")
        if isinstance(batch_resp, dict) and batch_resp.get('success'):
            batch_resp['note'] = 'cancel via batch'
            return batch_resp

        # If first attempt had context, try once more without context (some variants accept bare list)
        if product_id or product_symbol:
            bare_resp = self._make_request('DELETE', '/v2/orders/batch', data={'orders': [{'id': order_id}]}, suppress_log=True)
            if debug_cancel:
                dlog(f"batch bare success={bare_resp.get('success') if isinstance(bare_resp, dict) else None} status={bare_resp.get('status') if isinstance(bare_resp, dict) else None}")
            if isinstance(bare_resp, dict) and bare_resp.get('success'):
                bare_resp['note'] = 'cancel via batch bare'
                return bare_resp
        else:
            # Already tried bare (since no context); fall through
            pass

        # Optional: single path fallback
        path_resp = self._make_request('DELETE', f'/v2/orders/{order_id}', suppress_log=True)
        if debug_cancel:
            dlog(f"path-fallback success={path_resp.get('success') if isinstance(path_resp, dict) else None} status={path_resp.get('status') if isinstance(path_resp, dict) else None}")
        return path_resp
    
    def cancel_all_orders(self, product_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Cancel all orders
        
        Args:
            product_ids: Optional list of product IDs
            
        Returns:
            Cancellation response
        """
        data = {}
        if product_ids:
            data['product_ids'] = product_ids
        
        return self._make_request('DELETE', '/v2/orders/all', data=data)
    
    @rate_limit(calls_per_second=5)
    def test_connection(self) -> bool:
        """
        Test API connection
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.get_account_balance()
            return response.get('success', False) if isinstance(response, dict) else bool(response)
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False


class DeltaWebSocketClient:
    """Minimal WebSocket client for public mark_price feed."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.ws_url = self._get_ws_url(base_url)
        self.logger = logging.getLogger(__name__)
        self._thread: Optional[threading.Thread] = None
        self._ws = None  # type: ignore
        self._connected = False
        self._latest: Dict[str, Dict[str, Any]] = {}
        self._cmd_q: "queue.Queue[dict]" = queue.Queue()
        self._stop_event = threading.Event()

    def _get_ws_url(self, base_url: str) -> str:
        if 'testnet' in base_url:
            return 'wss://socket-ind.testnet.deltaex.org'
        return 'wss://socket.india.delta.exchange'

    def start(self):
        try:
            import websocket  # websocket-client
        except Exception as e:
            self.logger.error(f"websocket-client not installed: {e}")
            return False

        def on_open(ws):  # noqa: ANN001
            self._connected = True
            self.logger.info("WebSocket connected")
            # Default subscribe to BTCUSD mark price
            self.subscribe_mark_price('BTCUSD')

        def on_message(ws, message):  # noqa: ANN001
            try:
                data = json.loads(message)
                if data.get('type') == 'mark_price':
                    symbol = data.get('symbol', '')
                    # symbol is like 'MARK:BTCUSD'
                    core_symbol = symbol.replace('MARK:', '')
                    price = float(data.get('price')) if data.get('price') is not None else None
                    self._latest[core_symbol] = {
                        'price': price,
                        'received_at': int(time.time())
                    }
                # Process queued commands (subscribe/unsubscribe) if any
                while not self._cmd_q.empty():
                    ws.send(json.dumps(self._cmd_q.get_nowait()))
            except Exception as e:
                self.logger.error(f"WS on_message error: {e}")

        def on_error(ws, error):  # noqa: ANN001
            self.logger.error(f"WebSocket error: {error}")

        def on_close(ws, status_code, msg):  # noqa: ANN001
            self._connected = False
            self.logger.info(f"WebSocket closed: {status_code} {msg}")

        def run():
            ws = websocket.WebSocketApp(self.ws_url,
                                        on_open=on_open,
                                        on_message=on_message,
                                        on_error=on_error,
                                        on_close=on_close)
            self._ws = ws
            # Heartbeat/ping can be handled by run_forever params if needed
            while not self._stop_event.is_set():
                try:
                    ws.run_forever(ping_interval=20, ping_timeout=10)
                except Exception as e:  # reconnect loop
                    self.logger.error(f"WS run_forever error: {e}")
                    time.sleep(3)
                if not self._stop_event.is_set():
                    time.sleep(1)

        if self._thread and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop_event.set()
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def subscribe_mark_price(self, symbol: str):
        """Subscribe to mark_price channel for MARK:SYMBOL."""
        payload = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {"name": "mark_price", "symbols": [f"MARK:{symbol}"]}
                ]
            }
        }
        if self._ws is not None and self._connected:
            try:
                self._ws.send(json.dumps(payload))
            except Exception:
                pass
        else:
            self._cmd_q.put(payload)

    def get_latest_mark_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        entry = self._latest.get(symbol)
        return entry
