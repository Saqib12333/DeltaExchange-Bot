# Delta Exchange Trading Bot - AI Agent Instructions

## Architecture Overview

This is a **cryptocurrency trading automation system** for Delta Exchange India, consisting of:
- **Streamlit Dashboard** (`app.py`) - Real-time portfolio monitoring with modern UI
- **API Client** (`delta_client.py`) - Delta Exchange REST API wrapper with HMAC-SHA256 authentication
- **Trading Strategy** (`Stratergy/stratergy.md`) - Formal specification for "Haider Strategy" automation
- **Environment Management** (`.env`) - API credentials and configuration

The system is designed for **two phases**: Phase 1 (read-only monitoring) and Phase 2 (automated strategy execution).

## Key Technical Patterns

### Authentication & API Integration
```python
# HMAC-SHA256 signature generation pattern used throughout
signature = hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
message = method + timestamp + path + query_string + body
```
- All private endpoints require `api-key`, `signature`, and `timestamp` headers
- Base URLs: Production (`https://api.delta.exchange`) vs Testnet (`https://testnet-api.deltaex.org`)
- Error handling preserves API response structure for debugging

### Streamlit State Management
```python
@st.cache_data(ttl=30)  # 30-second cache for API calls
@st.cache_resource      # Singleton client instance
```
- Heavy use of caching to prevent API rate limiting
- Auto-refresh capability with configurable intervals
- Responsive grid layout with custom CSS for financial data visualization

### Data Flow Architecture
1. **Environment** → **DeltaExchangeClient** → **Streamlit Components**
2. Real-time data: positions, orders, balances, mark prices
3. State transitions tracked in strategy implementation

## Strategy Implementation Requirements

The **Haider Strategy** (`Stratergy/stratergy.md`) defines a complex averaging + take-profit system:
- **State Model**: `(side, lots)` where `lots ∈ {1, 3, 9, 27}`
- **Order Types**: Always exactly 2 orders (opposite TP + same-direction averaging) except at 27 lots
- **Price Calculations**: Fixed offsets (300→200→100→50 for TP, 750→500→500 for averaging)
- **Critical Invariant**: Cancel paired order immediately after any fill before placing new orders

## Development Workflows

### Setup & Running
```bash
streamlit run app.py     # Launch dashboard
```

### Environment Configuration
```env
DELTA_API_KEY=your_api_key_here
DELTA_API_SECRET=your_api_secret_here
USE_TESTNET=true  # Toggle production/testnet
```

### Testing Connection
```python
client = DeltaExchangeClient(api_key, api_secret, base_url)
is_connected = client.test_connection()  # Returns boolean
```

## Critical Files & Responsibilities

- **`delta_client.py`**: API abstraction layer - modify for new endpoints
- **`app.py`**: UI components - extend for new visualizations  
- **`Stratergy/stratergy.md`**: Strategy specification - reference for automation logic
- **`Delta-API-Docs.md`**: Complete API reference - consult for new integrations
- **`.env`**: Runtime configuration - never commit with real credentials

## Official Documentation

- **Delta Exchange API Docs**: https://docs.delta.exchange/
- **India Platform**: https://api.india.delta.exchange

## Integration Points & Dependencies

### External APIs
- **Delta Exchange REST API v2** - All trading operations
- **WebSocket feed** (documented but not implemented) - Real-time market data
- **Rate Limits**: Varies by endpoint, implement exponential backoff

### Data Dependencies
- **Product IDs** vs **Symbols**: API uses both; symbols are human-readable (e.g., "BTCUSD")
- **Precision**: 1 lot = 0.001 BTC, prices in USD with 1 USD tick assumption
- **Position States**: `size`, `side`, `entry_price`, `unrealized_pnl`, `liquidation_price`

## Project-Specific Conventions

### Error Handling Pattern
```python
try:
    response = self._make_request(method, endpoint, params, data)
    return response
except requests.exceptions.RequestException as e:
    self.logger.error(f"API request failed: {e}")
    # Always return API error structure for consistent handling
    return error_data
```

### UI Component Structure
- **Status Cards**: Color-coded connection/position status
- **Metric Cards**: Financial data with gradient borders
- **Auto-refresh**: Configurable intervals with manual override
- **Responsive Layout**: Columns adapt to data availability

### Strategy State Tracking
```python
# Example state representation for automation
state = {
    'side': 'LONG|SHORT', 
    'lots': 1|3|9|27, 
    'entry': price,
    'first_avg_price': price,  # Track averaging anchors
    'second_avg_price': price
}
```

## Security & Operational Notes

- **API Keys**: Read-only for Phase 1, write access required for Phase 2
- **Environment Isolation**: Testnet for development, production for live trading
- **Logging**: All state transitions and API calls logged for audit
- **Failsafe**: Strategy includes position size caps (max 27 lots) and distance constraints

## Extension Points

When implementing Phase 2 automation:
1. Create strategy engine in separate module
2. Implement order monitoring loop with WebSocket
3. Add position state persistence for crash recovery
4. Include risk management overrides for strategy constraints