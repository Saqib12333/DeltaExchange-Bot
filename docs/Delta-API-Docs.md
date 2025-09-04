# Delta Exchange India API Documentation

**Official Documentation**: https://docs.delta.exchange/

## Introduction

Welcome to the Delta Exchange India API! This documentation provides comprehensive information about our trading API, which allows programmatic access to Delta Exchange India trading features.

Delta Exchange India is a cryptocurrency derivatives exchange that offers trading in futures, options, and perpetual contracts. Our API provides:

- Real-time market data access
- Order management and trading
- Account and portfolio management  
- WebSocket feeds for live data
- Deadman switch safety mechanisms

## Base URLs

### REST API
- **Production**: `https://api.india.delta.exchange`
- **Testnet**: `https://cdn-ind.testnet.deltaex.org`

### WebSocket API
- **Production**: `wss://socket.india.delta.exchange`
- **Testnet**: `wss://socket-ind.testnet.deltaex.org`

### Connection Limits
- WebSocket connection limit guidance has varied; a historical note mentions "150 connections every 5 minutes per IP address" but this could not be verified in the current official docs. Confirm via testing or Delta support if you are near limits.
- You will be disconnected if there is no activity within 60 seconds after establishing a connection.

## API Versions

This documentation covers API version 2. All endpoints are prefixed with `/v2/`.

## Rate Limits

### REST API Rate Limits

When a rate limit is exceeded, the API returns HTTP 429 Too Many Requests. A response header `X-RATE-LIMIT-RESET` contains the time left in milliseconds after which the next API request can be attempted.

- Throttling method: Unauthenticated requests by IP address; authenticated requests by user ID
- Default quota: 10,000 requests per 5-minute window
- Reset interval: Quota resets every 5 minutes

### Product-Level Rate Limits

Limits also exist within the matching engine:
- Current limit: 500 operations per second for each product
- Operation counting: Each order is one operation (batch of 50 orders = 50 ops)
- Error response: Requests may fail with HTTP 429 even if REST API limit isn’t exceeded

### WebSocket Connection Limits

- Note: Specific connection limits vary. If you see 429 errors on connect, back off for 5–10 minutes and retry.
- Idle timeout: You will be disconnected if there is no activity within 60 seconds after connection.

## General Information

### Definitions

- **Contract**: A derivative product (futures, options, perpetual)
- **Symbol**: Unique identifier for a trading product (e.g., "BTCUSD", "C-BTC-50000-310325")
- **Product ID**: Numeric identifier for a trading product
- **Mark Price**: Fair value price used for liquidation calculations
- **Spot Price**: Current market price of the underlying asset

### Symbology

Delta Exchange India uses a standardized symbology across product types.

#### Perpetual Futures
Format: `{UNDERLYING}{QUOTE}`
Examples: `BTCUSD`, `ETHUSD`

#### Futures (Dated)
Format: `{UNDERLYING}|{QUOTE}|_|{MATURITY}` with maturity as `DDMMMYY`.
Examples:
- `BTC|USD|_|31JAN24` — Bitcoin futures expiring January 31, 2024
- `ETH|USD|_|28FEB24` — Ethereum futures expiring February 28, 2024

#### Options
Format: `{TYPE}-{UNDERLYING}-{STRIKE}-{EXPIRY}` where:
- TYPE: `C` for calls, `P` for puts
- UNDERLYING: e.g., `BTC`, `ETH`
- STRIKE: Strike price
- EXPIRY: `DDMMYY`

Examples:
- `C-BTC-90000-310125` — BTC call, strike 90,000, expires 31 Jan 2025
- `P-BTC-50000-280224` — BTC put, strike 50,000, expires 28 Feb 2024

#### Price References
1. Mark Price: `MARK:{Contract_Symbol}` (e.g., `MARK:BTCUSD`, `MARK:C-BTC-90000-310125`)
2. Index Price: `.DE{UnderlyingAsset}{QuotingAsset}` (e.g., `.DEBNBXBT`). Special case: BTC/USD index is `.DEXBTUSD`.

### Timestamps

All timestamps in the API are Unix timestamps in microseconds unless otherwise specified.

### Pagination

Many API endpoints that return lists support pagination using the following parameters:

- `page_size`: Number of records per page (default: 100, max: 1000)
- `after`: Cursor for pagination (timestamp or ID)
- `before`: Cursor for pagination (timestamp or ID)

### Data Centers

Delta Exchange operates from multiple data centers:

- **Primary**: Singapore
- **Secondary**: United States, Europe

Low-latency access is available through co-location services.

## Authentication

All private endpoints require authentication using API keys and request signing.

### Creating API Keys

1. Log into your Delta Exchange account
2. Navigate to API Management section
3. Create a new API key pair
4. Configure permissions (read, trade, withdraw)
5. Securely store your API secret

### Request Signing

All authenticated requests must include the following headers:

- `api-key`: Your API key
- `signature`: Request signature
- `timestamp`: Request timestamp
- `User-Agent`: Your language or client (e.g., `python-3.10`, `java`) — required to avoid certain 4XX errors
- `Content-Type`: `application/json`

#### Signature Generation

The signature is generated using HMAC-SHA256:

```
signature = HMAC-SHA256(api_secret, method + timestamp + path + query_string + body)
```

Where:
- `method`: HTTP method (GET, POST, PUT, DELETE)
- `timestamp`: Unix timestamp in seconds
- `path`: Request path (e.g., "/v2/orders")
- `query_string`: URL query parameters (if any)
- `body`: Request body for POST/PUT requests (empty string for GET)

Important:
- When query parameters are present, the query_string must include the leading `?` (i.e., sign `path + '?' + query`), matching server-side verification.
- Signatures older than ~5 seconds may be rejected; ensure clocks are in sync and send promptly.
- Public GET endpoints (e.g., `/v2/products`, `/v2/history/candles`) must not include auth headers.

#### Example Signature Generation (Python)

```python
import hmac, hashlib, time

def generate_signature(secret: str, method: str, path: str, query: str = '', body: str = ''):
  ts = str(int(time.time()))
  # Include leading '?' when query exists
  q = f'?{query}' if query and not query.startswith('?') else (query or '')
  msg = method + ts + path + q + body
  sig = hmac.new(secret.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256).hexdigest()
  return sig, ts

# Example usage
sig, ts = generate_signature('your_api_secret', 'GET', '/v2/orders', query='product_id=1&state=open')
```

#### Example Signature Generation (JavaScript)

```javascript
const crypto = require('crypto');

function generateSignature(secret, method, path, query = '', body = '') {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const q = query ? (query.startsWith('?') ? query : `?${query}`) : '';
  const message = method + timestamp + path + q + body;
    const signature = crypto
        .createHmac('sha256', secret)
        .update(message)
        .digest('hex');
  return { signature, timestamp };
}

// Example usage
const { signature, timestamp } = generateSignature('your_api_secret', 'GET', '/v2/orders', 'product_id=1&state=open');
```

### Updated Code Examples with User-Agent

Include the `User-Agent` header on all authenticated requests.

```python
import hashlib, hmac, requests, time

base_url = 'https://api.india.delta.exchange'
api_key = 'your_api_key'
api_secret = 'your_api_secret'

def generate_signature(secret, message):
  return hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()

# GET open orders
method = 'GET'; path = '/v2/orders'; query = 'product_id=1&state=open'; body = ''
timestamp = str(int(time.time()))
signature_data = method + timestamp + path + '?' + query + body
signature = generate_signature(api_secret, signature_data)

headers = {
  'api-key': api_key,
  'timestamp': timestamp,
  'signature': signature,
  'User-Agent': 'python-rest-client',
  'Content-Type': 'application/json',
}
resp = requests.request(method, f'{base_url}{path}', params={'product_id': 1, 'state': 'open'}, timeout=(3, 27), headers=headers)

# POST place order
method = 'POST'; path = '/v2/orders'; query = ''
body = '{"order_type":"limit_order","size":3,"side":"buy","limit_price":"0.0005","product_id":16}'
timestamp = str(int(time.time()))
signature_data = method + timestamp + path + query + body
signature = generate_signature(api_secret, signature_data)

headers = {
  'api-key': api_key,
  'timestamp': timestamp,
  'signature': signature,
  'User-Agent': 'rest-client',
  'Content-Type': 'application/json',
}
resp = requests.request(method, f'{base_url}{path}', data=body, timeout=(3, 27), headers=headers)
```

### Authentication Errors

Common authentication errors:

- `401 Unauthorized`: Invalid API key or signature
- `403 Forbidden`: Insufficient permissions
- `429 Too Many Requests`: Rate limit exceeded

## Products

### Get All Products

Retrieve a list of all available trading products.

**Endpoint:** `GET /v2/products`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `contract_types` | string | No | Filter by contract types (comma-separated) |
| `states` | string | No | Filter by product states |

**Response:**

```json
{
  "success": true,
  "result": [
    {
      "id": 27,
      "symbol": "BTCUSD",
      "description": "Bitcoin Perpetual",
      "created_at": "2019-06-11T11:20:03Z",
      "updated_at": "2023-12-20T10:30:45Z",
      "settlement_time": null,
      "notional_type": "vanilla",
      "impact_size": 100,
      "initial_margin": 0.05,
      "maintenance_margin": 0.025,
      "contract_value": "0.001",
      "contract_unit_currency": "BTC",
      "tick_size": "0.5",
      "underlying_asset": {
        "id": 1,
        "symbol": "BTC",
        "precision": 8
      },
      "quoting_asset": {
        "id": 3,
        "symbol": "USD",
        "precision": 2
      },
      "settling_asset": {
        "id": 1,
        "symbol": "BTC", 
        "precision": 8
      },
      "spot_index": {
        "id": 1,
        "symbol": "BTC-INDEX"
      },
      "state": "live",
      "trading_status": "operational",
      "max_leverage_notional": "1000000",
      "default_leverage": "3",
      "initial_margin_scaling_factor": "0.0001",
      "maintenance_margin_scaling_factor": "0.00005",
      "taker_commission_rate": "0.0005",
      "maker_commission_rate": "0.0002",
      "liquidation_penalty_factor": "0.0050",
      "contract_type": "perpetual_futures",
      "position_size_limit": 10000000,
      "basis_factor_max_limit": "0.001",
      "is_quanto": false,
      "funding_method": "fixed_rate",
      "annualized_funding": "0.0",
      "price_band": "0.05",
      "minimum_ticket_size": "5",
      "minimum_order_size_short_selling": "5",
      "ui_config": {
        "default_trading_view_candle": "1m",
        "leverage_slider_values": [1, 2, 3, 5, 8, 10, 15, 20, 25],
        "price_clubbing": {
          "rule": "dollar",
          "value": 10
        }
      },
      "турал_funding_rate": "0.0001",
      "funding_rate_symbol": "FUNDING:BTCUSD"
    }
  ]
}
```

### Get Product by Symbol

Retrieve details for a specific product by its symbol.

**Endpoint:** `GET /v2/products/{symbol}`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Product symbol (path parameter) |

**Response:** Same as individual product object from Get All Products

### Get Product Orderbook

Retrieve the current orderbook for a product.

**Endpoint:** `GET /v2/products/{symbol}/orders`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Product symbol (path parameter) |
| `depth` | integer | No | Orderbook depth (default: 20, max: 1000) |

**Response:**

```json
{
  "success": true,
  "result": {
    "buy": [
      {
        "depth": "100",
        "price": "42500.5",
        "size": 1500
      }
    ],
    "sell": [
      {
        "depth": "50", 
        "price": "42501.0",
        "size": 750
      }
    ],
    "last_updated_at": 1640995200000000,
    "symbol": "BTCUSD"
  }
}
```

## Orders

### Place Order

Create a new order.

**Endpoint:** `POST /v2/orders`

**Request Body:**

```json
{
  "product_id": 27,
  "size": 100,
  "side": "buy",
  "order_type": "limit_order",
  "limit_price": "42500",
  "time_in_force": "gtc",
  "post_only": false,
  "reduce_only": false,
  "client_order_id": "my_order_123"
}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `product_id` | integer | Yes | Product ID |
| `size` | integer | Yes | Order size in contracts |
| `side` | string | Yes | "buy" or "sell" |
| `order_type` | string | Yes | Order type |
| `limit_price` | string | No | Required for limit orders |
| `stop_price` | string | No | Required for stop orders |
| `time_in_force` | string | No | "gtc", "ioc", "fok" (default: "gtc") |
| `post_only` | boolean | No | Post-only flag (default: false) |
| `reduce_only` | boolean | No | Reduce-only flag (default: false) |
| `client_order_id` | string | No | Client-provided order ID |

**Order Types:**

- `limit_order`: Standard limit order
- `market_order`: Market order (executed immediately)
- `stop_loss_order`: Stop-loss order
- `take_profit_order`: Take-profit order

**Time in Force:**

- `gtc`: Good Till Cancelled
- `ioc`: Immediate or Cancel
- `fok`: Fill or Kill

**Response:**

```json
{
  "success": true,
  "result": {
    "id": 12345678,
    "user_id": 1234,
    "size": 100,
    "unfilled_size": 100,
    "side": "buy",
    "order_type": "limit_order",
    "limit_price": "42500",
    "stop_price": null,
    "paid_commission": "0",
    "commission": "0.1",
    "product_id": 27,
    "product_symbol": "BTCUSD",
    "created_at": "2023-12-20T10:30:45Z",
    "updated_at": "2023-12-20T10:30:45Z",
    "state": "open",
    "client_order_id": "my_order_123",
    "time_in_force": "gtc",
    "post_only": false,
    "reduce_only": false
  }
}
```

### Get Orders

Retrieve orders for the authenticated user.

**Endpoint:** `GET /v2/orders`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `product_ids` | string | No | Comma-separated product IDs |
| `contract_types` | string | No | Filter by contract types |
| `order_types` | string | No | Filter by order types |
| `start_time` | integer | No | Start time filter (microseconds) |
| `end_time` | integer | No | End time filter (microseconds) |
| `after` | integer | No | Pagination cursor |
| `before` | integer | No | Pagination cursor |
| `page_size` | integer | No | Results per page (max: 1000) |

**Response:**

```json
{
  "success": true,
  "result": [
    {
      "id": 12345678,
      "user_id": 1234,
      "size": 100,
      "unfilled_size": 0,
      "side": "buy",
      "order_type": "limit_order",
      "limit_price": "42500",
      "average_fill_price": "42500",
      "fills": [
        {
          "id": 987654321,
          "size": 100,
          "price": "42500",
          "commission": "0.1",
          "created_at": "2023-12-20T10:35:00Z",
          "role": "taker"
        }
      ],
      "state": "filled",
      "created_at": "2023-12-20T10:30:45Z",
      "updated_at": "2023-12-20T10:35:00Z"
    }
  ],
  "meta": {
    "after": 12345678,
    "before": null
  }
}
```

### Cancel Order

Cancel an existing order.

**Endpoint:** `DELETE /v2/orders/{order_id}`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `order_id` | integer | Yes | Order ID (path parameter) |

**Response:**

```json
{
  "success": true,
  "result": {
    "id": 12345678,
    "state": "cancelled",
    "updated_at": "2023-12-20T10:40:00Z"
  }
}
```

### Cancel All Orders

Cancel all open orders for specified products.

**Endpoint:** `DELETE /v2/orders/all`

**Request Body:**

```json
{
  "product_ids": [27, 139],
  "cancel_limit_orders": true,
  "cancel_stop_orders": true,
  "cancel_reduce_only_orders": false
}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `product_ids` | array | No | Product IDs to cancel (empty = all) |
| `cancel_limit_orders` | boolean | No | Cancel limit orders (default: true) |
| `cancel_stop_orders` | boolean | No | Cancel stop orders (default: true) |
| `cancel_reduce_only_orders` | boolean | No | Cancel reduce-only orders (default: true) |

**Response:**

```json
{
  "success": true,
  "result": {
    "cancelled_orders": 5,
    "message": "All orders cancelled successfully"
  }
}
```

## Account

### Get Account Balance

Retrieve account balance and wallet information.

**Endpoint:** `GET /v2/wallet/balances`

**Response:**

```json
{
  "success": true,
  "result": [
    {
      "asset_id": 1,
      "asset_symbol": "BTC",
      "available_balance": "1.50000000",
      "available_balance_for_robo": "1.50000000",
      "balance": "2.00000000",
      "commission_balance": "0.00010000",
      "cross_asset_liability": "0.00000000",
      "cross_commission_liability": "0.00000000",
      "cross_locked_balance": "0.00000000",
      "cross_order_margin": "0.25000000",
      "cross_position_margin": "0.25000000",
      "id": 123456,
      "interest_credit": "0.00000000",
      "order_margin": "0.25000000",
      "pending_referral_bonus": "0.00000000",
      "pending_trading_fee_credit": "0.00000000",
      "portfolio_margin": "0.25000000",
      "position_margin": "0.25000000",
      "trading_fee_credit": "0.00000000",
      "unvested_amount": "0.00000000",
      "user_id": 1234
    }
  ]
}
```

### Get Positions

Retrieve current positions.

**Endpoint:** `GET /v2/positions`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `product_ids` | string | No | Comma-separated product IDs |
| `contract_types` | string | No | Filter by contract types |

**Response:**

```json
{
  "success": true,
  "result": [
    {
      "user_id": 1234,
      "product_id": 27,
      "product_symbol": "BTCUSD",
      "size": 1000,
      "entry_price": "42000.0",
      "margin": "2.10000000",
      "liquidation_price": "38500.0",
      "bankruptcy_price": "38000.0",
      "adl_level": 2,
      "unrealized_pnl": "500.0",
      "realized_pnl": "0.0"
    }
  ]
}
```

### Change Position Margin

Modify position margin.

**Endpoint:** `POST /v2/positions/change_margin`

**Request Body:**

```json
{
  "product_id": 27,
  "delta_margin": "0.5"
}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `product_id` | integer | Yes | Product ID |
| `delta_margin` | string | Yes | Margin change amount |

**Response:**

```json
{
  "success": true,
  "result": {
    "product_id": 27,
    "new_margin": "2.60000000",
    "new_liquidation_price": "39200.0"
  }
}
```

## Deadman Switch

The Deadman Switch is a safety mechanism that automatically cancels orders or takes other protective actions when a client fails to send heartbeat signals within specified time intervals. This feature is essential for risk management and preventing unwanted positions from accumulating due to client disconnections or failures.

### Overview

The Deadman Switch system consists of several components:

- **Heartbeat Creation**: Clients register a heartbeat with specific configuration
- **Heartbeat Acknowledgment**: Clients periodically send acknowledgments to keep the heartbeat alive
- **Automatic Actions**: When heartbeats expire, the system automatically executes configured actions

### Authentication

All Deadman Switch endpoints require authentication. Include your API key and signature in the request headers as described in the Authentication section.

### Heartbeat Management

#### Create Heartbeat

Creates a new heartbeat with specific configuration for automatic actions.

**Endpoint:** `POST /v2/heartbeat/create`

**Request Body:**

```json
{
  "heartbeat_id": "my_trading_bot_001",
  "impact": "contracts",
  "contract_types": ["perpetual_futures", "call_options"],
  "underlying_assets": ["BTC", "ETH"],
  "product_symbols": ["BTCUSD", "ETHUSD"],
  "config": [
    {
      "action": "cancel_orders",
      "unhealthy_count": 1
    },
    {
      "action": "spreads",
      "unhealthy_count": 3,
      "value": 100
    }
  ]
}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `heartbeat_id` | string | Yes | Unique identifier for the heartbeat |
| `impact` | string | Yes | Impact: `contracts`, `products` |
| `contract_types` | array | Yes | Array of contract types to monitor, required if impact is contracts |
| `underlying_assets` | array | No | Array of underlying assets to monitor |
| `product_symbols` | array | Yes | Array of specific product symbols to monitor, required if impact is products |
| `config` | array | Yes | Array of action configurations |

**Config Actions:**

- `cancel_orders`: Cancels all open orders
- `spreads`: Adds spreads to orders

**Response:**

```json
{
  "success": true,
  "result": {
    "heartbeat_id": "my_trading_bot_001"
  }
}
```

#### Heartbeat Acknowledgment

Sends an acknowledgment to keep the heartbeat active. Set ttl to 0 to disable heartbeat.

**Endpoint:** `POST /v2/heartbeat`

**Request Body:**

```json
{
  "heartbeat_id": "my_trading_bot_001",
  "ttl": 30000
}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `heartbeat_id` | string | Yes | Heartbeat identifier |
| `ttl` | integer/string | Yes | Time to live in milliseconds |

**Response:**

```json
{
  "success": true,
  "result": {
    "heartbeat_timestamp": "1243453435",
    "process_enabled": "true"
  }
}
```

#### Get Heartbeats

Retrieves all active heartbeats for a user.

**Endpoint:** `GET /v2/heartbeat`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `heartbeat_id` | string | No | Specific heartbeat ID to retrieve |

**Response:**

```json
{
  "success": true,
  "result": [
    {
      "user_id": "user_id",
      "heartbeat_id": "my_trading_bot_001",
      "impact": "contracts",
      "contract_types": ["perpetual_futures", "call_options"],
      "underlying_assets": ["BTC", "ETH"],
      "product_symbols": ["BTCUSD", "ETHUSD"],
      "config": [
        {
          "action": "cancel_orders",
          "unhealthy_count": 1
        }
      ]
    }
  ]
}
```

### Implementation Guidelines

#### Best Practices

1. **Regular Heartbeats**: Send heartbeat acknowledgments at regular intervals (recommended: every 30 seconds)
2. **Error Handling**: Implement proper error handling for heartbeat failures
3. **Monitoring**: Monitor heartbeat status and implement alerts for failures
4. **Graceful Shutdown**: Properly disable heartbeats when shutting down trading systems

#### Python Example

```python
import requests
import time
import json

class DeadmanSwitch:
    def __init__(self, api_key, api_secret, base_url):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.heartbeat_id = "trading_bot_" + str(int(time.time()))

    def create_heartbeat(self):
        """Create a new heartbeat"""
        url = f"{self.base_url}/heartbeat/create"
        headers = self._get_auth_headers()

        payload = {
            "heartbeat_id": self.heartbeat_id,
            "impact": "contracts",
            "contract_types": ["perpetual_futures"],
            "config": [
                {
                    "action": "cancel_orders",
                    "unhealthy_count": 1  # if heartbeat missed 1 time than cancel all orders
                }
            ]
        }

        response = requests.post(url, json=payload, headers=headers)
        return response.json()

    def send_heartbeat(self):
        """Send heartbeat acknowledgment"""
        url = f"{self.base_url}/heartbeat"
        headers = self._get_auth_headers()

        payload = {
            "heartbeat_id": self.heartbeat_id,
            "ttl": 30000  # 30 seconds
        }

        response = requests.post(url, json=payload, headers=headers)
        return response.json()

    def start_heartbeat_loop(self):
        """Start continuous heartbeat loop"""
        while True:
            try:
                result = self.send_heartbeat()
                print(f"Heartbeat sent: {result}")
                time.sleep(25)  # Send every 25 seconds (TTL is 30)
            except Exception as e:
                print(f"Heartbeat failed: {e}")
                time.sleep(5)

    def _get_auth_headers(self):
        # Implement authentication headers
        return {
            "Content-Type": "application/json",
            "api-key": self.api_key,
            # Add signature generation logic
        }

# Usage example
deadman = DeadmanSwitch("your_api_key", "your_api_secret", "https://api.delta.exchange")
deadman.create_heartbeat()
deadman.start_heartbeat_loop()
```

#### Node.js Example

```javascript
const axios = require('axios');
const crypto = require('crypto');

class DeadmanSwitch {
    constructor(apiKey, apiSecret, baseUrl) {
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        this.baseUrl = baseUrl;
        this.heartbeatId = `trading_bot_${Date.now()}`;
    }

    async createHeartbeat() {
        const url = `${this.baseUrl}/heartbeat/create`;
        const headers = this.getAuthHeaders();

        const payload = {
            heartbeat_id: this.heartbeatId,
            impact: "contracts",
            contract_types: ["perpetual_futures"],
            config: [
                {
                    action: "cancel_orders",
                    unhealthy_count: 1
                }
            ]
        };

        const response = await axios.post(url, payload, { headers });
        return response.data;
    }

    async sendHeartbeat() {
        const url = `${this.baseUrl}/heartbeat`;
        const headers = this.getAuthHeaders();

        const payload = {
            heartbeat_id: this.heartbeatId,
            ttl: 30000
        };

        const response = await axios.post(url, payload, { headers });
        return response.data;
    }

    startHeartbeatLoop() {
        setInterval(async () => {
            try {
                const result = await this.sendHeartbeat();
                console.log('Heartbeat sent:', result);
            } catch (error) {
                console.error('Heartbeat failed:', error);
            }
        }, 25000); // Send every 25 seconds
    }

    getAuthHeaders() {
        // Implement authentication headers
        return {
            'Content-Type': 'application/json',
            'api-key': this.apiKey,
            // Add signature generation logic
        };
    }
}

// Usage example
const deadman = new DeadmanSwitch('your_api_key', 'your_api_secret', 'https://api.delta.exchange');
deadman.createHeartbeat();
deadman.startHeartbeatLoop();
```

### Security Considerations

1. **API Key Security**: Keep your API keys secure and never expose them in client-side code
2. **Network Security**: Use HTTPS for all API communications
3. **Monitoring**: Implement proper monitoring and alerting for heartbeat failures
4. **Backup Systems**: Consider implementing backup heartbeat mechanisms for critical trading systems

## Settlement Prices

### Get Settlement Prices

Retrieve settlement prices for expired contracts.

**Endpoint:** `GET /v2/settlement_prices`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `product_ids` | string | No | Comma-separated product IDs |
| `start_time` | integer | No | Start time filter (microseconds) |
| `end_time` | integer | No | End time filter (microseconds) |

**Response:**

```json
{
  "success": true,
  "result": [
    {
      "product_id": 123,
      "symbol": "BTC-310325",
      "settlement_price": "42500.0",
      "settlement_time": "2025-03-31T16:00:00Z"
    }
  ]
}
```

## Historical OHLC Data

### Get Historical Candles

Retrieve historical OHLC (Open, High, Low, Close) candlestick data.

**Endpoint:** `GET /v2/history/candles`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Product symbol |
| `resolution` | string | Yes | Time resolution (1m, 5m, 15m, 1h, 4h, 1d, etc.) |
| `start` | integer | Yes | Start time (Unix timestamp) |
| `end` | integer | Yes | End time (Unix timestamp) |

**Supported Resolutions:**
["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "2w", "30d"]

**Response:**

```json
{
  "success": true,
  "result": [
    {
      "time": 1640995200,
      "open": 42000.0,
      "high": 42500.0,
      "low": 41800.0,
      "close": 42300.0,
      "volume": 1500000
    }
  ]
}
```

## Error Handling

### Place Order Errors

This section lists various errors returned by the system while placing orders. The error format looks like this:

```json
{
  "success": false,
  "error": {
    "code": "...",        // error code
    "context": {
      "..."
    }
  }
}
```

Here is a list of error codes and their explanation:

| Error Code | Description |
|------------|-------------|
| `insufficient_margin` | Margin required to place order with selected leverage and quantity is insufficient. |
| `order_size_exceed_available` | The order book doesn't have sufficient liquidity, hence the order couldn't be filled (for ex - ioc orders). |
| `risk_limits_breached` | Orders couldn't be placed as it will breach allowed risk limits. |
| `invalid_contract` | The contract/product either doesn't exist or has already expired. |
| `immediate_liquidation` | Order will cause immediate liquidation. |
| `out_of_bankruptcy` | Order prices are out of position bankruptcy limits. |
| `self_matching_disrupted_post_only` | Self matching is not allowed during auction. |
| `immediate_execution_post_only` | Orders couldn't be placed as it includes post only orders which will be immediately executed. |

### General API Errors

Delta API uses the following error codes:

| Error Code | Meaning |
|------------|---------|
| 400 | Bad Request -- Your request is invalid. |
| 401 | Unauthorized -- Your API key/Signature is wrong. |
| 403 | Forbidden Error -- Request blocked by CDN (e.g., missing User-Agent header or hidden/blocked IP from certain hosted environments). |
| 404 | Not Found -- The specified resource could not be found. |
| 405 | Method Not Allowed -- You tried to access a resource with an invalid method. |
| 406 | Not Acceptable -- You requested a format that isn't json. |
| 429 | Too Many Requests -- You have exhausted your rate limits! Slow down! |
| 500 | Internal Server Error -- We had a problem with our server. Try again later. |
| 503 | Service Unavailable -- We're temporarily offline for maintenance. Please try again later. |

## REST Clients

Delta API conforms to the Swagger spec for REST endpoints. Any Swagger-compatible client can connect to the Delta API and execute commands.

You can find the swagger spec json for Delta Api [here](https://docs.delta.exchange/api/swagger_v2.json)

We also have Rest Api Clients available for the following languages:

- [Nodejs](https://www.npmjs.com/package/delta-rest-client)
- [Python](https://pypi.org/project/delta-rest-client)

### CCXT

CCXT is our authorized SDK provider and you may access our API through CCXT.

For more information, please visit [ccxt website](https://ccxt.trade/).

## WebSocket Feed

WebSocket API can be used for the following use cases:

- Get real time feed of market data, this includes L2 orderbook and recent trades
- Get price feeds - Mark prices of different contracts, price feed of underlying indexes etc.
- Get account specific notifications like fills, liquidations, ADL and PnL updates
- Get account specific updates on orders, positions and wallets

**WebSocket URLs:**

- **Production**: `wss://socket.india.delta.exchange`
- **Testnet**: `wss://socket-ind.testnet.deltaex.org`

**Connection Limits:**
There is a limit of 150 connections every 5 minutes per IP address. A connection attempt that goes beyond the limit will be disconnected with 429 HTTP status error. On receiving this error, wait for 5 to 10 minutes before making new connection requests.

You will be disconnected if there is no activity within **60 seconds** after making connection.

### Subscribing to Channels

#### Subscribe

To begin receiving feed messages, you must first send a subscribe message to the server indicating which channels and contracts to subscribe for.

To specify contracts within each channel, just pass a list of symbols inside the channel payload. Mention **["all"]** in symbols if you want to receive updates across all the contracts. Please note that snapshots are sent only for specified symbols, meaning no snapshots are sent for symbol: **"all"**.

Once a subscribe message is received the server will respond with a subscriptions message that lists all channels you are subscribed to. Subsequent subscribe messages will add to the list of subscriptions.

**Subscription Sample:**

```json
// Request: Subscribe to BTCUSD and ETHUSD with the ticker and orderbook(L2) channels.
{
    "type": "subscribe",
    "payload": {
        "channels": [
            {
                "name": "v2/ticker",
                "symbols": [
                    "BTCUSD",
                    "ETHUSD"
                ]
            },
            {
                "name": "l2_orderbook",
                "symbols": [
                    "BTCUSD"
                ]
            },
            {
                "name": "funding_rate",
                "symbols": [
                    "all"
                ]
            }
        ]
    }
}

// Response: Success
{
    "type": "subscriptions",
    "channels": [
        {
            "name": "l2_orderbook",
            "symbols": [
                "BTCUSD"
            ]
        },
        {
            "name": "v2/ticker",
            "symbols": [
                "BTCUSD",
                "ETHUSD"
            ]
        },
        {
            "name": "funding_rate",
            "symbols": [
                "all"
            ]
        }
    ]
}

// Response: Error 
{
    "type": "subscriptions",
    "channels": [
        {
            "name": "l2_orderbook",
            "symbols": [
                "BTCUSD"
            ]
        },
        {
            "name": "trading_notifications",
            "error": "subscription forbidden on trading_notifications. Unauthorized user"
        }
    ]
}
```

#### Unsubscribe

If you want to unsubscribe from channel/contracts pairs, send an "unsubscribe" message. The structure is equivalent to subscribe messages. If you want to unsubscribe for specific symbols in a channel, you can pass it in the symbol list. As a shorthand you can also provide no symbols for a channel, which will unsubscribe you from the channel entirely.

**Unsubscribe Sample:**

```json
// Request: Unsubscribe from BTCUSD and ETHUSD with the ticker and orderbook(L2) channels.
{
    "type": "unsubscribe",
    "payload": {
        "channels": [
            {
                "name": "v2/ticker",          // unsubscribe from ticker channel only for BTCUSD
                "symbols": [
                    "BTCUSD"
                ]
            },
            {
                "name": "l2_orderbook"      // unsubscribe from all symbols for l2_orderbook channel
            }
        ]
    }
}
```

#### Authenticating a Connection

Authentication allows clients to receive private messages, like trading notifications. Examples of the trading notifications are: fills, liquidations, ADL and PnL updates.

To authenticate, you need to send a signed request of type **'auth'** on your socket connection. Check the authentication section above for more details on how to sign a request using api key and secret.

The payload for the signed request will be **'GET' + timestamp + '/live'**

To subscribe to private channels, the client needs to first send an auth event, providing api-key, and signature.

**Authentication Sample:**

```python
# auth message with signed request
import websocket
import hashlib
import hmac
import time

api_key = 'a207900b7693435a8fa9230a38195d'
api_secret = '7b6f39dcf660ec1c7c664f612c60410a2bd0c258416b498bf0311f94228f'

def generate_signature(secret, message):
    message = bytes(message, 'utf-8')
    secret = bytes(secret, 'utf-8')
    hash = hmac.new(secret, message, hashlib.sha256)
    return hash.hexdigest()

# Get open orders
method = 'GET'
timestamp = str(int(time.time()))
path = '/live'
signature_data = method + timestamp + path
signature = generate_signature(api_secret, signature_data)

ws = websocket.WebSocketApp('wss://socket.india.delta.exchange')
ws.send(json.dumps({
    "type": "auth",
    "payload": {
        "api-key": api_key,
        "signature": signature,
        "timestamp": timestamp
    }
}))
```

To unsubscribe from all private channels, just send a **'unauth'** message on the socket. This will automatically unsubscribe the connection from all authenticated channels.

```python
ws.send(json.dumps({
    "type": 'unauth',
    "payload": {}
}))
```

### Sample Python Code

#### Public Channels

**Summary:** 
The python script connects to the Delta Exchange WebSocket to receive real-time market data.

- It opens a connection
- Subscribes to `v2/ticker`(tickers data) and `candlestick_1m`(1 minute ohlc candlesticks) channels. (**MARK:BTCUSD** - mark price ohlc in candlesticks channel)
- When data arrives, it processes and prints it
- If an error occurs, it prints an error message
- If the connection closes, it notifies the user
- The connection remains open indefinitely to keep receiving updates

```python
import websocket
import json

# production websocket base url
WEBSOCKET_URL = "wss://socket.india.delta.exchange"

def on_error(ws, error):
    print(f"Socket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"Socket closed with status: {close_status_code} and message: {close_msg}")

def on_open(ws):
  print(f"Socket opened")
  # subscribe tickers of perpetual futures - BTCUSD & ETHUSD, call option C-BTC-95200-200225 and put option - P-BTC-95200-200225
  subscribe(ws, "v2/ticker", ["BTCUSD", "ETHUSD", "C-BTC-95200-200225", "P-BTC-95200-200225"])
  # subscribe 1 minute ohlc candlestick of perpetual futures - MARK:BTCUSD(mark price) & ETHUSD(ltp), call option C-BTC-95200-200225(ltp) and put option - P-BTC-95200-200225(ltp).
  subscribe(ws, "candlestick_1m", ["MARK:BTCUSD", "ETHUSD", "C-BTC-95200-200225", "P-BTC-95200-200225"])

def subscribe(ws, channel, symbols):
    payload = {
        "type": "subscribe",
        "payload": {
            "channels": [
                {
                    "name": channel,
                    "symbols": symbols
                }
            ]
        }
    }
    ws.send(json.dumps(payload))

def on_message(ws, message):
    # print json response
    message_json = json.loads(message)
    print(message_json)

if __name__ == "__main__":
  ws = websocket.WebSocketApp(WEBSOCKET_URL, on_message=on_message, on_error=on_error, on_close=on_close)
  ws.on_open = on_open
  ws.run_forever() # runs indefinitely
```

#### Private Channels

**Summary:** 
The python script connects to the Delta Exchange WebSocket to receive real-time market data.

- It opens a connection
- Sends authentication payload over socket with api_key, signature & timestamp
- When authentication update arrives, it checks for success and then sends subscription for `orders` and `positions` channels for all contracts
- Prints all other updates in json format
- If an error occurs, it prints an error message
- If the connection closes, it notifies the user
- The connection remains open indefinitely to keep receiving updates

```python
import websocket
import hashlib
import hmac
import json
import time

# production websocket base url and api keys/secrets
WEBSOCKET_URL = "wss://socket.india.delta.exchange"
API_KEY = 'a207900b7693435a8fa9230a38195d'
API_SECRET = '7b6f39dcf660ec1c7c664f612c60410a2bd0c258416b498bf0311f94228f'

def on_error(ws, error):
    print(f"Socket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"Socket closed with status: {close_status_code} and message: {close_msg}")

def on_open(ws):
    print(f"Socket opened")
    # api key authentication
    send_authentication(ws)

def send_authentication(ws):
    method = 'GET'
    timestamp = str(int(time.time()))
    path = '/live'
    signature_data = method + timestamp + path
    signature = generate_signature(API_SECRET, signature_data)
    ws.send(json.dumps({
        "type": "auth",
        "payload": {
            "api-key": API_KEY,
            "signature": signature,
            "timestamp": timestamp
        }
    }))

def generate_signature(secret, message):
    message = bytes(message, 'utf-8')
    secret = bytes(secret, 'utf-8')
    hash = hmac.new(secret, message, hashlib.sha256)
    return hash.hexdigest()

def on_message(ws, message):
    message_json = json.loads(message)
    # subscribe private channels after successful authentication
    if message_json['type'] == 'success' and message_json['message'] == 'Authenticated':
         # subscribe orders channel for order updates for all contracts
        subscribe(ws, "orders", ["all"])
        # subscribe positions channel for position updates for all contracts
        subscribe(ws, "positions", ["all"])
    else:
      print(message_json)

def subscribe(ws, channel, symbols):
    payload = {
        "type": "subscribe",
        "payload": {
            "channels": [
                {
                    "name": channel,
                    "symbols": symbols
                }
            ]
        }
    }
    ws.send(json.dumps(payload))

if __name__ == "__main__":
  ws = websocket.WebSocketApp(WEBSOCKET_URL, on_message=on_message, on_error=on_error, on_close=on_close)
  ws.on_open = on_open
  ws.run_forever() # runs indefinitely
```

### Detecting Connection Drops

Some client libraries might not detect connection drops properly. We provide two methods for the clients to ensure they are connected and getting subscribed data.

#### Heartbeat (Recommended)

The client can enable heartbeat on the socket. If heartbeat is enabled, the server is expected to periodically send a heartbeat message to the client. Right now, the heartbeat time is set to 30 seconds.

**How to Implement on client side:**

- Enable heartbeat (check sample code) after each successful socket connection
- Set a timer with duration of 35 seconds (We take 5 seconds buffer for heartbeat to arrive)
- When you receive a new heartbeat message, you reset the timer
- If the timer is called, that means the client didn't receive any heartbeat in last 35 seconds. In this case, the client should exit the existing connection and try to reconnect.

```python
// Enable Heartbeat on successful connection
ws.send({
    "type": "enable_heartbeat"
})

// Disable Heartbeat
ws.send({
    "type": "disable_heartbeat"
})

// Sample Heartbeat message received periodically by client
{
    "type": "heartbeat"
}
```

#### Ping/Pong

The client can periodically (~ every 30 seconds) send a ping frame or a raw ping message and the server will respond back with a pong frame or a raw pong response. If the client doesn't receive a pong response in next 5 seconds, the client should exit the existing connection and try to reconnect.

```python
// Ping Request
ws.send({
    "type": "ping"
})

// Pong Response
ws.send({
    "type": "pong"
})
```

### Public Channels

#### v2 ticker

The ticker channel provides **price change data** for the last **24 hrs** (rolling window).  
It is published every **5 seconds**.

To subscribe to the ticker channel, you need to send the list of **symbols** for which you would like to receive updates.

You can also subscribe to ticker updates for a **category of products** by sending a list of category names.  
For example, to receive updates for **put options** and **futures**, use the following format:  
`{"symbols": ["put_options", "futures"]}`

If you would like to subscribe to all listed contracts, pass:  
`{ "symbols": ["all"] }`

**Important:**  
If you subscribe to the ticker channel without specifying a symbols list, you will **not** receive any data.

**Ticker Sample:**

```json
// Subscribe to specific symbol
{
    "type": "subscribe",
    "payload": {
        "channels": [
            {
                "name": "v2/ticker",
                "symbols": [
                    "BTCUSD"
                ]
            }
        ]
    }
}

// Subscribe to all symbols
{
    "type": "subscribe",
    "payload": {
        "channels": [
            {
                "name": "v2/ticker",
                "symbols": [
                    "all"
                ]
            }
        ]
    }
}
```

```json
// Response
{
    "open": 0.00001347, // The price at the beginning of the 24-hour period
    "close": 0.00001327, // The price at the end of the 24-hour period
    "high": 0.00001359, // The highest price during the 24-hour period
    "low": 0.00001323, // The lowest price during the 24-hour period
    "mark_price": "0.00001325", // The current market price
    "mark_change_24h": "-0.1202", // Percentage change in market price over the last 24 hours
    "oi": "812.6100", // Open interest, indicating the total number of outstanding contracts
    "product_id": 27, // The unique identifier for the product
    "quotes": {
        "ask_iv": "0.25", // Implied volatility for the ask price (if available)
        "ask_size": "922", // The size of the ask (the amount available for sale)
        "best_ask": "3171.5", // The best ask price (the lowest price at which the asset is being offered)
        "best_bid": "3171.4", // The best bid price (the highest price a buyer is willing to pay)
        "bid_iv": "0.25", // Implied volatility for the bid price (if available)
        "bid_size": "191", // The size of the bid (the amount a buyer is willing to purchase)
        "impact_mid_price": "61200", // Mid price impact, if available (the price midpoint between the best bid and ask)
        "mark_iv": "0.29418049" // Mark volatility (volatility of the asset used for mark price calculation)
    },
    "greeks": { // Options-related metrics, will be null for Futures and Spot products
        "delta": "0.01939861", // Rate of change of the option price with respect to the underlying asset's price
        "gamma": "0.00006382", // Rate of change of delta with respect to the underlying asset's price
        "rho": "0.00718630", // Rate of change of option price with respect to interest rate
        "spot": "63449.5", // The current spot price of the underlying asset
        "theta": "-81.48397021", // Rate of change of option price with respect to time (time decay)
        "vega": "0.72486575" // Sensitivity of the option price to volatility changes
    },
    "size": 1254631, // Number of contracts traded
    "spot_price": "0.00001326", // Spot price at the time of the ticker
    "symbol": "BTCUSD", // The symbol of the contract
    "timestamp": 1595242187705121, // The timestamp of the data (in microseconds)
    "turnover": 16.805033569999996, // The total turnover in the settling symbol
    "turnover_symbol": "BTC", // The symbol used for settling
    "turnover_usd": 154097.09108233, // The turnover value in USD
    "volume": 1254631 // Total volume, defined as contract value * size
}
```

#### l1_orderbook

**l1_orderbook** channel provides level1 orderbook updates. You need to send the list of symbols for which you would like to subscribe to L1 orderbook. You can also subscribe to orderbook updates for category of products by sending category-names. For example: to receive updates for put options and futures, refer this: `{"symbols": ["put_options", "futures"]}`.  
If you would like to subscribe for all the listed contracts, pass: `{ "symbols": ["all"] }`.  
Please note that if you subscribe to L1 channel without specifying the symbols list, you will not receive any data.  
Publish interval: 100 millisecs  
Max interval (in case of same data): 5 secs

**L1 Orderbook Sample:**

```json
//Subscribe
{
    "type": "subscribe",
    "payload": {
        "channels": [
            {
                "name": "l1_orderbook",
                "symbols": [
                    "ETHUSD"
                ]
            }
        ]
    }
}
```

```json
// l1 orderbook Response
{
  "ask_qty":"839",
  "best_ask":"1211.3",
  "best_bid":"1211.25",
  "bid_qty":"772",
  "last_sequence_no":1671603257645135,
  "last_updated_at":1671603257623000,
  "product_id":176,"symbol":"ETHUSD",
  "timestamp":1671603257645134,
  "type":"l1_orderbook"
}
```

#### l2_orderbook

**l2_orderbook** channel provides the complete level2 orderbook for the specified list of symbols at a pre-determined frequency. The frequency of updates may vary for different symbols. You can only subscribe to upto 20 symbols on a single connection. Unlike L1 orderbook channel, L2 orderbook channel does not accept product category names or "all" as valid symbols.  
Please note that if you subscribe to L2 channel without specifying the symbols list, you will not receive any data.  
Publish interval: 1 sec  
Max interval (in case of same data): 10 secs

**L2 Orderbook Sample:**

```json
//Subscribe
{
    "type": "subscribe",
    "payload": {
        "channels": [
            {
                "name": "l2_orderbook",
                "symbols": [
                    "ETHUSD"
                ]
            }
        ]
    }
}
```

```json
// l2 orderbook Response
{
  "type":"l2_orderbook",
  "symbol":"ETHUSD",
  "product_id": 176,
  "buy": [
    {
        "limit_price":"101.5",
        "size":10,              // For Futures & Options: number of contracts integer. Spot product: Asset token quantity in string.
        "depth":"10"            // total size from best bid
    },
  ],
  "sell": [
    {
        "limit_price":"102.0",
        "size":20,
        "depth":"20"            // total size from best ask
    },
  ],
  "last_sequence_no": 6435634,
  "last_updated_at": 1671600133884000,
  "timestamp":1671600134033215,
}
```

#### l2_updates

**l2_updates** channel provides initial snapshot and then incremental orderbook data. The frequency of updates may vary for different symbols. You can only subscribe to upto 100 symbols on a single connection. l2_updates channel does not accept product category names or "all" as valid symbols.  
Please note that if you subscribe to l2_updates channel without specifying the symbols list, you will not receive any data.  
Publish interval: 100 millisecs  
"action"="update" messages won't be published till there is an orderbook change.

```json
//Subscribe
{
    "type": "subscribe",
    "payload": {
        "channels": [
            {
                "name": "l2_updates",
                "symbols": [
                    "BTCUSD"
                ]
            }
        ]
    }
}

// Initial snapshot response
{
  "action":"snapshot",
  "asks":[["16919.0", "1087"], ["16919.5", "1193"], ["16920.0", "510"]],
  "bids":[["16918.0", "602"], ["16917.5", "1792"], ["16917.0", "2039"]],
  "timestamp":1671140718980723,
  "sequence_no":6199,
  "symbol":"BTCUSD",
  "type":"l2_updates",
  "cs":2178756498
}

// Incremental update response
{
  "action":"update",
  "asks":[["16919.0", "0"], ["16919.5", "710"]],
  "bids":[["16918.5", "304"]],
  "sequence_no":6200,
  "symbol":"BTCUSD",
  "type":"l2_updates",
  "timestamp": 1671140769059031,
  "cs":3409694612
}

// Error response
{
  "action":"error",
  "symbol":"BTCUSD",
  "type":"l2_updates",
  "msg":"Snapshot load failed. Verify if product is live and resubscribe after a few secs."
}
```

##### How to maintain orderbook locally using this channel:

1) When you subscribe to this channel, the first message with "action"= "snapshot" resembles the complete l2_orderbook at this time. "asks" and "bids" are arrays of ["price", "size"]. (size is number of contracts at this price)

2) After the initial snapshot, messages will be with "action" = "update", resembling the difference between current and previous orderbook state. "asks" and "bids" are arrays of ["price", "new size"]. "asks" are sorted in increasing order of price. "bids" are sorted in decreasing order of price. This is true for both "snapshot" and "update" messages.

3) "sequence_no" field must be used to check if any messages were dropped. "sequence_no" must be +1 of the last message.  
e.g. In the snapshot message it is 6199, and the update message has 6200. The next update message must have 6201. In case of sequence_no mismatch, resubscribe to the channel, and start from the beginning.

4) If sequence_no is correct, edit the in-memory orderbook using the "update" message.  
Case 1: price already exists, new size is 0 -> Delete this price level.  
Case 2: price already exists, new size isn't 0 -> Replace the old size with new size.  
Case 3: price doesn't exists -> insert the price level.  
e.g. for the shown snapshot and update messages to create the new orderbook: in the ask side, price level of "16919.0" will be deleted. Size at price level "16919.5" will be changed from "1193" to "710". In the bids side there was no price level of "16918.5", so add a new level of "16918.5" of size "304". Other price levels from the snapshot will remain the same.

5) If "action":"error" message is received, resubscribe this symbol after a few seconds. Can occur in rare cases, e.g. Failed to send "action":"snapshot" message after subscribing due to a race condition, instead an "error" message will be sent.

**Checksum:** Using this, users can verify the accuracy of orderbook data created using l2_updates. checksum is the "cs" key in the message payload.  
Steps to calculate checksum:  
1) Edit the old in-memory orderbook with the "update" message received.  
2) Create asks_string and bids_string as shown below. where priceN = price at Nth level, sizeN = size at Nth level. Asks are sorted in increasing order and bids in decreasing order by price.  
asks_string = price0:size0,price1:size1,…,price9:size9  
bids_string = price0:size0,price1:size1,…,price9:size9  
checksum_string = asks_string + "|" + bids_string  
Only consider the first 10 price levels on both sides. If orderbook as less than 10 levels, use only them.  
e.g. If after applying the update, the new orderbook becomes ->  
asks = [["100.00", "23"], ["100.05", "34"]]  
bids = [["99.04", "87"], ["98.65", "102"], ["98.30", "16"]]  
checksum_string = "100.00:23,100.05:34|99.04:87,98.65:102,98.30:16"  
3) Calculate the CRC32 value (32-bit unsigned integer) of checksum_string. This should be equal to the checksum provided in the "update" message.

#### all_trades

**all_trades** channel provides a real time feed of all trades (fills).  
You need to send the list of symbols for which you would like to subscribe to all trades channel. After subscribing to this channel, you get a snapshot of last 50 trades and then trade data in real time. You can also subscribe to all trades updates for category of products by sending category-names. For example: to receive updates for put options and futures, refer this: `{"symbols": ["put_options", "futures"]}`.  
If you would like to subscribe for all the listed contracts, pass: `{ "symbols": ["all"] }`.  
Please note that if you subscribe to all_trades channel without specifying the symbols list, you will not receive any data.

**All Trades Sample:**

```json
//Subscribe
{
    "type": "subscribe",
    "payload": {
        "channels": [
            {
                "name": "all_trades",
                "symbols": [
                    "BTCUSD"
                ]
            }
        ]
    }
}
```

```json
// All Trades Response Snapshot
{
    "symbol": "BTCUSD",
    "type": "all_trades_snapshot",          // "type" is not "all_trades"
    "trades": [                             // Recent trades list
        {
            "buyer_role": "maker",
            "seller_role": "taker",
            "size": 53,                     // size in contracts
            "price": "25816.5",
            "timestamp": 1686577411879974   // time of the trade.
        },
         // More recent trades.
    ]
}
```

```json
// All Trades Response
{
    "symbol": "BTCUSD",
    "price": "25816.5",
    "size": 100,
    "type": "all_trades",
    "buyer_role": "maker",
    "seller_role": "taker",
    "timestamp": 1686577411879974
}
```

#### mark_price

**mark_price** channel provides mark price updates at a fixed interval. This is the price on which all open positions are marked for liquidation. Please note that the product symbol is prepended with a "MARK:" to subscribe for mark price.  
You need to send the list of symbols for which you would like to subscribe to mark price channel. You can also subscribe to mark price updates for category of products by sending category-names. For example: to receive updates for put options and futures, refer this: `{"symbols": ["put_options", "futures"]}`.  
If you would like to subscribe for all the listed contracts, pass: `{ "symbols": ["all"] }`.  
You can also subscribe to a Options chain, by passing 'Asset-Expiry', e.g. `{"symbols": ["BTC-310524"] }` will subscribe to all BTC Options expiring on 31st May 2024.  
Please note that if you subscribe to mark price channel without specifying the symbols list, you will not receive any data.  
Publish interval: 2 secs.

**Mark Price Sample:**

```json
//Subscribe
{
    "type": "subscribe",
    "payload": {
        "channels": [
            {
                "name": "mark_price",
                "symbols": [
                    "MARK:C-BTC-13000-301222"
                ]
            }
        ]
    }
}
```

```json
// Mark Price Response
{
    "ask_iv": null,
    "ask_qty": null,
    "best_ask": null,
    "best_bid": "9532",
    "bid_iv": "5.000",
    "bid_qty": "896",
    "delta": "0",
    "gamma": "0",
    "implied_volatility": "0",
    "price": "3910.088012",
    "price_band":{"lower_limit":"3463.375340559572217228510815","upper_limit":"4354.489445440427782771489185"},
    "product_id": 39687,
    "rho": "0",
    "symbol": "MARK:C-BTC-13000-301222",
    "timestamp": 1671867039712836,
    "type": "mark_price",
    "vega": "0"
}
```

#### candlesticks

This channel provides last ohlc candle for given time resolution. Traded price candles and Mark Price candles data can be received by sending appropriate symbol string. "product_symbol" gives traded_price candles, and "MARK:product_symbol" gives mark_price candles.  
e.g. symbols: ["BTCUSD"] gives you Traded Price candlestick data for BTCUSD  
symbols: ["MARK:C-BTC-75000-310325"] gives you Mark Price candlestick data for C-BTC-75000-310325

Subscribe to **candlestick_${resolution}** channel for updates.

List of supported resolutions:  
["1m","3m","5m","15m","30m","1h","2h","4h","6h","12h","1d","1w","2w","30d"]

You need to send the list of symbols for which you would like to subscribe to candlesticks channel.  
You can also subscribe to candlesticks updates for category of products by sending category-names. For example: to receive updates for put options and futures, refer this: `{"symbols": ["put_options", "futures"]}`.  
Please note that if you subscribe to candlesticks channel without specifying the symbols list, you will not receive any data.

**OHLC candles update sample:**

```json
Sample Subscribe Request
{
  "name": "candlestick_1m",       // "candlestick_" + resolution
  "symbols": [ "BTCUSD", "MARK:ETHUSD" ]  // gives BTCUSD traded price, ETHUSD mark price candle data.
}

Sample feed response

{
    "candle_start_time": 1596015240000000,
    "close": 9223,
    "high": 9228,
    "low": 9220,
    "open": 9221,
    "resolution": "1m",
    "symbol": "BTCUSD",
    "timestamp": 1596015264287158,
    "type": "candlestick_1m",
    "volume": 2834
}
```

## Schemas

### Product Schema

```json
{
  "id": "integer",
  "symbol": "string",
  "description": "string", 
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "settlement_time": "timestamp|null",
  "notional_type": "string",
  "impact_size": "number",
  "initial_margin": "number",
  "maintenance_margin": "number", 
  "contract_value": "string",
  "contract_unit_currency": "string",
  "tick_size": "string",
  "product_specs": {
    "underlying_asset": {
      "id": "integer",
      "symbol": "string", 
      "precision": "integer"
    },
    "quoting_asset": {
      "id": "integer",
      "symbol": "string",
      "precision": "integer" 
    },
    "settling_asset": {
      "id": "integer",
      "symbol": "string",
      "precision": "integer"
    }
  },
  "state": "string",
  "trading_status": "string",
  "max_leverage_notional": "string",
  "default_leverage": "string", 
  "initial_margin_scaling_factor": "string",
  "maintenance_margin_scaling_factor": "string",
  "taker_commission_rate": "string",
  "maker_commission_rate": "string",
  "liquidation_penalty_factor": "string",
  "contract_type": "string",
  "position_size_limit": "integer",
  "basis_factor_max_limit": "string",
  "is_quanto": "boolean",
  "funding_method": "string",
  "annualized_funding": "string",
  "price_band": "string",
  "minimum_ticket_size": "string",
  "minimum_order_size_short_selling": "string"
}
```

### Order Schema

```json
{
  "id": "integer",
  "user_id": "integer",
  "size": "integer",
  "unfilled_size": "integer",
  "side": "string",
  "order_type": "string",
  "limit_price": "string|null",
  "stop_price": "string|null",
  "paid_commission": "string",
  "commission": "string",
  "product_id": "integer", 
  "product_symbol": "string",
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "state": "string",
  "client_order_id": "string|null",
  "time_in_force": "string",
  "post_only": "boolean",
  "reduce_only": "boolean",
  "average_fill_price": "string|null",
  "fills": [
    {
      "id": "integer",
      "size": "integer", 
      "price": "string",
      "commission": "string",
      "created_at": "timestamp",
      "role": "string"
    }
  ]
}
```

### Position Schema

```json
{
  "user_id": "integer",
  "product_id": "integer",
  "product_symbol": "string",
  "size": "integer",
  "entry_price": "string",
  "margin": "string",
  "liquidation_price": "string",
  "bankruptcy_price": "string", 
  "adl_level": "integer",
  "unrealized_pnl": "string",
  "realized_pnl": "string"
}
```

### Balance Schema

```json
{
  "asset_id": "integer",
  "asset_symbol": "string",
  "available_balance": "string",
  "available_balance_for_robo": "string",
  "balance": "string",
  "commission_balance": "string",
  "cross_asset_liability": "string",
  "cross_commission_liability": "string", 
  "cross_locked_balance": "string",
  "cross_order_margin": "string",
  "cross_position_margin": "string",
  "id": "integer",
  "interest_credit": "string",
  "order_margin": "string",
  "pending_referral_bonus": "string",
  "pending_trading_fee_credit": "string",
  "portfolio_margin": "string", 
  "position_margin": "string",
  "trading_fee_credit": "string",
  "unvested_amount": "string",
  "user_id": "integer"
}
```

### Product Categories

The following product categories are supported for filtering and subscriptions:

- `futures`
- `perpetual_futures` 
- `call_options`
- `put_options`
- `interest_rate_swaps`
- `move_options`
- `spreads`
- `spot`

### Order States

- `open`: Order is active and unfilled
- `pending`: Order is being processed
- `filled`: Order is completely filled
- `cancelled`: Order has been cancelled
- `rejected`: Order was rejected

### Order Types

- `limit_order`: Standard limit order
- `market_order`: Market order for immediate execution
- `stop_loss_order`: Stop loss order
- `take_profit_order`: Take profit order

### Time in Force

- `gtc`: Good Till Cancelled
- `ioc`: Immediate or Cancel  
- `fok`: Fill or Kill

### Trading Status

- `operational`: Normal trading
- `disrupted_cancel_only`: Only cancellations allowed
- `disrupted_post_only`: Only post-only orders allowed
- `halt`: Trading halted

---

This completes the comprehensive Delta Exchange API documentation converted from HTML to Markdown format without missing any content from the original documentation.
