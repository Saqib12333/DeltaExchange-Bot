# Delta Exchange Trading Bot - AI Agent Instructions
Version: 3.0.2

## Architecture Overview

This is a **cryptocurrency trading automation system** for Delta Exchange India, consisting of:
- **Streamlit Dashboard** (`app.py`) - Real-time portfolio monitoring with fixed 1s auto-refresh (no manual controls)
- **API Client** (`delta_client.py`) - Delta Exchange REST API wrapper with fixed authentication and rate limiting
- **WebSocket Client** (`ws_client.py`) - Public mark_price channel client backing WS‑first pricing
- **Trading Strategy** (`Stratergy/stratergy.md`) - Formal specification for "Haider Strategy" automation
- **Environment Management** (`.env`) - API credentials and configuration

The system is designed for **two phases**: Phase 1 (read-only monitoring) ✅ COMPLETE and Phase 2 (automated strategy execution) 🚧 IN DEVELOPMENT.

## Key Technical Patterns

### Authentication & API Integration (FIXED ✅)
```python
# FIXED: HMAC-SHA256 signature generation with proper query string formatting
# CRITICAL: include '?' between path and query when signing if params exist
if query_string:
    message = method + timestamp + path + '?' + query_string + body
else:
    message = method + timestamp + path + body
signature = hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
query_string = '&'.join([f"{key}={value}" for key, value in params.items()])
```
- All private endpoints require `api-key`, `signature`, and `timestamp` headers
- **Base URLs**: Production (`https://api.india.delta.exchange`) vs Testnet (`https://cdn-ind.testnet.deltaex.org`)
- **Fixed Issue**: Query string formatting in signature generation corrected (include "?" when query exists)
- Error handling preserves API response structure for debugging
- **Rate Limiting**: Built-in 3-5 calls per second limits with decorator pattern

### Streamlit State Management (ENHANCED ✅)
```python
@st.cache_data(ttl=30)  # Account balance
@st.cache_data(ttl=5)   # Positions
@st.cache_data(ttl=5)   # Orders
@st.cache_resource      # Singleton client instance
```
- **Fixed Auto-Refresh**: 1-second cadence; no manual toggles/buttons
- **Intelligent Caching**: Different TTL values for different data types
- **Fixed Caching Issues**: Using `_client` parameter to prevent unhashable object errors
- **Session State**: Proper state management for user preferences
- Responsive grid layout with custom CSS for financial data visualization

### Mark Price Integration (WS-first ✅)
```python
# WebSocket-first BTCUSD mark price with REST fallback
# Alias retained: get_latest_mark_price -> get_latest_mark
ws_price = ws_client.get_latest_mark('BTCUSD')
if not ws_price and client:
    rest = client.get_mark_price('BTCUSD')
```
- **Focused Display**: Only BTCUSD mark price shown
- **Real-time Updates**: Status indicators (Live WS/REST)
- **Clean UI**: Removed unnecessary charts and multi-crypto complexity
- **Accurate PnL**: Position calculations now use real mark prices
- **Fallback**: Order price estimation if mark price fails

### Data Flow Architecture
1. **Environment** → **DeltaExchangeClient** → **Streamlit Components**
2. Real-time data: positions, orders, balances, **accurate mark prices**
3. **1-second refresh cycle** with automatic rerun (no buttons)
4. State transitions tracked in strategy implementation

## Recent Critical Fixes (September 2025) ✅

### 1. API Authentication Resolution
- **Issue**: Signature mismatch errors for endpoints with query parameters
- **Root Cause**: Signature message formatting was incorrect
- **Solution**: Include `?` between path and query in the signature when query exists; skip auth headers on public GET endpoints
- **Result**: All API endpoints now working correctly (wallet, positions, orders)

### 2. UI Formatting Errors Fixed
- **Issue**: `Invalid format specifier ',.2f if condition else 'text'' for object of type 'float'`
- **Root Cause**: Conditional expressions inside f-string format specifiers
- **Solution**: Pre-format conditional values before f-string usage
- **Files Fixed**: Orders display, mark prices display in `app.py`

### 3. Streamlit Caching Issues Resolved
- **Issue**: `UnhashableParamError: Cannot hash argument 'client'` crashes
- **Root Cause**: Streamlit cache trying to hash DeltaExchangeClient objects containing functions
- **Solution**: Added underscore prefix to client parameters (`_client`) in cached functions
- **Result**: App runs stable without caching crashes

### 4. Mark Price Accuracy Implementation
- **Issue**: Inaccurate price estimates from order approximations
- **Solution**: Implemented proper mark price fetching using `/v2/history/candles` with `MARK:SYMBOL` format
- **Result**: Real-time accurate BTCUSD prices with status indicators

### 5. Auto-Refresh Control Enhancement
- **Change**: Fixed 1s auto-refresh with countdown placeholder and rerun
- **Result**: Smooth UX without manual controls

### 6. Rate Limiting Implementation
- **Issue**: No protection against API abuse
- **Solution**: Added rate limiting decorators (3-5 calls/second) to all API methods
- **Result**: Prevents API bans and ensures stable operation

### 7. Error Handling Enhancement
- **Issue**: App crashes on API errors or network issues
- **Solution**: Implemented `safe_api_call()` wrapper with graceful degradation
- **Result**: App continues working even with temporary API failures

## Strategy Implementation Requirements

The **Haider Strategy** (`Stratergy/stratergy.md`) defines a complex averaging + take-profit system:
- **State Model**: `(side, lots)` where `lots ∈ {1, 3, 9, 27}`
- **Order Types**: Always exactly 2 orders (opposite TP + same-direction averaging) except at 27 lots
- **Price Calculations**: Fixed offsets (300→200→100→50 for TP, 750→500→500 for averaging)
- **Critical Invariant**: Cancel paired order immediately after any fill before placing new orders

## Development Workflows

### Setup & Running
```bash
streamlit run app.py     # Launch dashboard with 1-second auto-refresh
```

### Environment Configuration
```env
DELTA_API_KEY=your_api_key_here
DELTA_API_SECRET=your_api_secret_here
DELTA_BASE_URL=https://api.india.delta.exchange
USE_TESTNET=false  # Toggle production/testnet
```

### Testing Mark Prices
```python
client = DeltaExchangeClient(api_key, api_secret, base_url)
mark_data = client.get_mark_price('BTCUSD')  # Returns real mark price
```

## Critical Files & Responsibilities

- **`delta_client.py`**: API abstraction layer with fixed authentication - modify for new endpoints
- **`ws_client.py`**: Minimal WebSocket client for mark_price; provides `connect()`, `subscribe_mark(["BTCUSD"])`, `get_latest_mark("BTCUSD")`, and `close()`; auto‑reconnect loop with ping
- **`app.py`**: UI components with 1-second auto-refresh - extend for new visualizations  
- **`Stratergy/stratergy.md`**: Strategy specification - reference for automation logic
- **`Delta-API-Docs.md`**: Complete API reference - consult for new integrations
- **`.env`**: Runtime configuration - never commit with real credentials

### WebSocket details
- URLs: prod `wss://socket.india.delta.exchange`, testnet `wss://socket-ind.testnet.deltaex.org`
- Subscription payload uses `MARK:BTCUSD` symbols; helper accepts `"BTCUSD"` and prefixes internally
- Thread-safe latest mark store; alias `get_latest_mark_price()` retained for compatibility
- Use a cached singleton in Streamlit to avoid multiple connections per rerun

Example pattern (matches app):
```python
@st.cache_resource
def get_ws_client(base_url: str):
    use_testnet = 'testnet' in base_url.lower()
    ws = DeltaWSClient(use_testnet=use_testnet)
    ws.connect()
    ws.subscribe_mark(["BTCUSD"])
    return ws
```

## Official Documentation

- **Delta Exchange API Docs**: https://docs.delta.exchange/
- **India Platform**: https://api.india.delta.exchange

## Integration Points & Dependencies

### External APIs
- **Delta Exchange REST API v2** - All trading operations ✅ WORKING
- **WebSocket feed** mark_price channel ✅ IMPLEMENTED
- **Historical Candles Endpoint** - REST fallback for mark price ✅ IMPLEMENTED
- **Rate Limits**: 1-second polling is well within limits

### Data Dependencies
- **Product IDs** vs **Symbols**: API uses both; symbols are human-readable (e.g., "BTCUSD")
- **Mark Price Format**: Use "MARK:SYMBOL" in historical candles for accurate prices
- **Precision**: 1 lot = 0.001 BTC, prices in USD with 0.5 USD tick size
- **Position States**: `size`, `side`, `entry_price` (unrealized_pnl and margin not available in India API)

## Project-Specific Conventions

### Fixed Error Handling Pattern
```python
try:
    response = self._make_request(method, endpoint, params, data)
    return response
except requests.exceptions.RequestException as e:
    self.logger.error(f"API request failed: {e}")
    # Always return API error structure for consistent handling
    return {"success": False, "error": str(e)}
```

### UI Component Structure (Updated)
- **Status Cards**: Color-coded connection/position status
- **Metric Cards**: Financial data with gradient borders and fixed formatting
- **Auto-refresh**: 1-second automatic updates (no manual configuration)
- **Real-time Prices**: Live mark prices with "Live (WS/REST)" status indicators
- **Responsive Layout**: Columns adapt to data availability

### Strategy State Tracking
```python
# Example state representation for automation
state = {
    'side': 'LONG|SHORT', 
    'lots': 1|3|9|27, 
    'entry': price,
    'current_price': mark_price,  # Now accurate from candles endpoint
    'unrealized_pnl': calculated_pnl,  # Calculated from entry vs current
    'first_avg_price': price,  # Track averaging anchors
    'second_avg_price': price
}
```

## Security & Operational Notes

- **API Keys**: Read-only for Phase 1, write access required for Phase 2
- **Environment Isolation**: Testnet for development, production for live trading
- **Real-time Monitoring**: 1-second updates provide immediate trade execution feedback
- **Logging**: All state transitions and API calls logged for audit
- **Failsafe**: Strategy includes position size caps (max 27 lots) and distance constraints

## Current System Status (September 2025)

### ✅ Phase 1: FULLY OPERATIONAL
- **Dashboard**: Running at http://localhost:8501 with fixed 1s auto-refresh
- **API Integration**: All endpoints working correctly with fixed authentication
- **Real-time Data**: Live BTCUSD mark price with accurate P&L calculations
- **Portfolio Monitoring**: Account balance, positions, orders all displaying correctly
- **Error Handling**: No UI crashes, proper error messaging with graceful degradation
- **Performance**: Optimized with caching and rate limiting

### 🚧 Phase 2: Ready for Implementation
- **Strategy Engine**: Can be built on existing stable foundation
- **Order Placement**: API client ready for trading operations with rate limiting
- **State Management**: Framework in place for strategy state tracking
- **Risk Management**: Position limits and price constraints ready to implement

## Extension Points

When implementing Phase 2 automation:
1. Create strategy engine in separate module using existing `delta_client.py`
2. Implement order monitoring loop (REST polling or WebSocket upgrade)
3. Add position state persistence for crash recovery
4. Include risk management overrides for strategy constraints
5. Use real-time mark prices for accurate entry/exit decisions

## Performance Characteristics

- Mark price via WebSocket; REST candles as fallback
- Dashboard refresh: fixed 1-second cadence with caching
- Built-in request throttling and timeouts

## Maintainer and Ownership

<p align="left">
    <img src="https://github.com/Saqib12333.png?size=200" alt="Saqib Sherwani" width="120" height="120" style="border-radius: 50%; margin-right: 12px;" />
</p>

- Name: Saqib Sherwani
- GitHub: https://github.com/Saqib12333
- Email: sherwanisaqib@gmail.com
- Ownership: Sole owner and maintainer of this repository and all included code
