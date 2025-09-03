import hmac
import hashlib
import time
import json
import requests
from typing import Dict, List, Optional, Any
import logging

class DeltaExchangeClient:
    """
    Delta Exchange API Client for portfolio management and trading
    """
    
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://api.delta.exchange"):
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
        self.session = requests.Session()
        
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
        message = method + timestamp + path + query_string + body
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature, timestamp
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                     data: Optional[Dict] = None) -> Dict[str, Any]:
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
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        
        if data:
            body = json.dumps(data)
        
        # Generate signature
        signature, timestamp = self._generate_signature(method, endpoint, query_string, body)
        
        # Prepare headers
        headers = {
            'api-key': self.api_key,
            'signature': signature,
            'timestamp': timestamp,
            'Content-Type': 'application/json'
        }
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = self.session.post(url, headers=headers, json=data)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    self.logger.error(f"Error details: {error_data}")
                    return error_data
                except:
                    self.logger.error(f"Response content: {e.response.text}")
            raise
    
    def get_account_balance(self) -> Dict[str, Any]:
        """
        Get account balance and wallet information
        
        Returns:
            Account balance data
        """
        return self._make_request('GET', '/v2/wallet/balances')
    
    def get_positions(self, product_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Get current positions
        
        Args:
            product_ids: Optional list of product IDs to filter
            
        Returns:
            Positions data
        """
        params = {}
        if product_ids:
            params['product_ids'] = ','.join(map(str, product_ids))
        
        return self._make_request('GET', '/v2/positions', params=params)
    
    def get_orders(self, product_ids: Optional[List[int]] = None, 
                   page_size: int = 100) -> Dict[str, Any]:
        """
        Get open orders
        
        Args:
            product_ids: Optional list of product IDs to filter
            page_size: Number of orders per page
            
        Returns:
            Orders data
        """
        params = {'page_size': page_size}
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
    
    def get_mark_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get mark price for a product
        
        Args:
            symbol: Product symbol
            
        Returns:
            Mark price data
        """
        try:
            # Get product first to get the mark price
            product_data = self.get_product_by_symbol(symbol)
            if product_data.get('success'):
                product = product_data.get('result', {})
                # Mark price might be in the product specs or we need to get it from ticker
                return {'success': True, 'mark_price': product.get('mark_price')}
            return product_data
        except Exception as e:
            self.logger.error(f"Failed to get mark price for {symbol}: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_orderbook(self, symbol: str, depth: int = 20) -> Dict[str, Any]:
        """
        Get orderbook for a product
        
        Args:
            symbol: Product symbol
            depth: Orderbook depth
            
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
    
    def cancel_order(self, order_id: int) -> Dict[str, Any]:
        """
        Cancel an order
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            Cancellation response
        """
        return self._make_request('DELETE', f'/v2/orders/{order_id}')
    
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
    
    def test_connection(self) -> bool:
        """
        Test API connection
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.get_account_balance()
            return response.get('success', False)
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
