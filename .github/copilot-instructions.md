# DeltaExchange-Bot Development Instructions

**CRITICAL**: Always follow these instructions first and only fall back to additional search or context gathering if the information here is incomplete or found to be in error.

Delta Exchange Trading Bot is a Python-based cryptocurrency trading automation system featuring a real-time FastAPI + HTMX dashboard and legacy Streamlit interface for Delta Exchange India. The system provides portfolio monitoring, order management, and is designed for future automated trading strategies.

## Working Effectively

### Environment Setup and Dependencies
- **Prerequisites**: Python 3.8+ (tested with Python 3.12.3)
- **Dependency Installation**: `pip install -r requirements.txt` -- takes approximately 60 seconds. NEVER CANCEL.
- **Environment Configuration**: Copy `.env.example` to `.env` and configure API credentials
- **Python Compilation Check**: `python -m py_compile app.py server/main.py src/delta_client.py src/ws_client.py` -- takes 5-10 seconds

### Core Application Startup
- **FastAPI Dashboard**: `python -m uvicorn server.main:app --host 127.0.0.1 --port 8000` -- starts in 5-10 seconds, requires network connectivity for full functionality
- **Legacy Streamlit Interface**: `streamlit run app.py` -- starts in 5-10 seconds, requires network connectivity
- **Access URLs**: 
  - FastAPI: http://127.0.0.1:8000
  - Streamlit: http://localhost:8501

### Network Requirements and Limitations
- **CRITICAL**: Applications require internet connectivity to Delta Exchange APIs
- **API Endpoints**: 
  - Production: https://api.india.delta.exchange
  - Testnet: https://cdn-ind.testnet.deltaex.org
  - WebSocket: wss://socket.india.delta.exchange (production)
- **Timeout Settings**: 30-second request timeouts are configured in the code
- **IPv4 Enforcement**: Set `DELTA_FORCE_IPV4=true` in `.env` to avoid IPv6 whitelist issues

## Validation and Testing

### Manual Validation Scenarios
**CRITICAL**: After making any changes, always execute these validation steps:

1. **Dependency Check**: Verify all Python files compile: `find . -name "*.py" -exec python -m py_compile {} \;`
2. **Import Test**: `python -c "import streamlit; import fastapi; import uvicorn; import pandas; import plotly; print('Dependencies OK')"` -- takes ~1 second
3. **Application Startup**: Start both applications and verify they launch without immediate errors
4. **Dashboard Access**: With valid API keys, verify dashboard loads and displays connection status
5. **Core Functionality**: Test portfolio view, order display, and mark price updates

### Test Infrastructure
- **Playwright Testing**: `python -m playwright install --with-deps` -- takes 2-5 minutes for browser installation. NEVER CANCEL.
- **Test Execution**: `pytest -q tests/test_e2e_playwright.py` (NOTE: Test files referenced in README do not currently exist)
- **Missing Tests**: The repository mentions Playwright tests but the actual test files are not present. Do not assume tests exist without verification.
- **Creating Tests**: To implement the missing test infrastructure:
  ```bash
  mkdir tests
  # Create pytest configuration and test files as needed
  # Refer to Playwright documentation for FastAPI testing patterns
  ```

### Build and Quality Checks
- **No Formal Build Process**: This is a Python application with no compilation step beyond dependency installation
- **No Linting Tools**: No linting packages (flake8, black, pylint) are included in requirements.txt
- **Code Validation**: Use Python's built-in compilation check as the primary validation method

## Project Structure and Key Components

### Repository Layout
```
DeltaExchange-Bot/
├── app.py                    # Legacy Streamlit dashboard
├── server/                   # FastAPI application
│   ├── main.py              # Main FastAPI app with WebSocket support
│   ├── templates/           # Jinja2 templates for HTMX partials
│   └── static/              # CSS and JavaScript assets
├── src/                     # Core business logic
│   ├── delta_client.py      # REST API client with auth and rate limiting
│   └── ws_client.py         # WebSocket client for real-time price feeds
├── requirements.txt         # Python dependencies
├── .env.example            # Environment template
├── AGENTS.md               # Architecture and development patterns
└── docs/                   # API documentation and strategy specs
    ├── Delta-API-Docs.md   # API reference
    └── strategy/           # Trading strategy documentation
```

### Critical Files for Development
- **API Client**: `src/delta_client.py` - Authentication, rate limiting, error handling
- **WebSocket Client**: `src/ws_client.py` - Real-time price feeds and market data
- **FastAPI Routes**: `server/main.py` - Web dashboard, API endpoints, WebSocket handlers
- **Configuration**: `.env` - API keys, debug settings, environment selection
- **Architecture Guide**: `AGENTS.md` - Development patterns and technical details

### Environment Variables
```env
DELTA_API_KEY=your_api_key_here                    # Required for live operation
DELTA_API_SECRET=your_api_secret_here              # Required for live operation
USE_TESTNET=false                                  # Set to true for testnet
DELTA_BASE_URL=https://api.india.delta.exchange    # Production API URL
DELTA_FORCE_IPV4=true                             # Avoid IPv6 whitelist issues
DELTA_DEBUG_AUTH=false                            # Enable signature debugging
MOCK_DELTA=true                                   # Mock mode (legacy, may not work)
```

## Development Workflow

### Making Changes
1. **Validate Environment**: Ensure dependencies are installed and applications can start
2. **Test Compilation**: Run `python -m py_compile` on modified files
3. **Local Testing**: Start applications and verify functionality
4. **Manual Validation**: Execute the validation scenarios above
5. **Integration Testing**: With valid API keys, test against Delta Exchange APIs

### Common Development Tasks
- **Adding New API Endpoints**: Modify `src/delta_client.py` and add rate limiting decorators
- **WebSocket Integration**: Extend `src/ws_client.py` subscription handling
- **UI Changes**: Update Jinja2 templates in `server/templates/` for FastAPI or modify `app.py` for Streamlit
- **Configuration**: Add new environment variables to `.env.example` and document in README

### Debugging and Troubleshooting
- **Authentication Issues**: Set `DELTA_DEBUG_AUTH=true` to log signature generation details
- **Network Problems**: Use `DELTA_FORCE_IPV4=true` and verify API key whitelisting
- **WebSocket Failures**: Check network connectivity and WebSocket endpoint availability
- **Import Errors**: Verify all dependencies are installed with `pip install -r requirements.txt`

## Timing Expectations and Performance

### Command Timing (NEVER CANCEL these operations)
- **Dependency Installation**: 60 seconds for `pip install -r requirements.txt` (fresh install)
- **Dependency Import Test**: 1 second for `python -c "import streamlit; import fastapi; import uvicorn; import pandas; import plotly; print('Dependencies OK')"`
- **Python Compilation**: <1 second per file for `python -m py_compile`
- **Full Compilation Check**: <5 seconds for `find . -name "*.py" -exec python -m py_compile {} \;`
- **Playwright Browser Install**: 2-5 minutes for `python -m playwright install --with-deps`
- **Application Startup**: 5-10 seconds for both FastAPI and Streamlit
- **API Response Times**: 1-30 seconds depending on network and API load
- **WebSocket Connection**: 5-15 seconds for initial connection and subscription

### Network Operation Timeouts
- **API Requests**: 30 seconds (configured in delta_client.py)
- **WebSocket Reconnection**: Continuous with exponential backoff
- **Dashboard Refresh**: 1-second intervals for real-time updates

## Security and API Management

### API Key Requirements
- **Development**: Use testnet API keys for development and testing
- **Production**: Requires production API keys with appropriate permissions
- **IP Whitelisting**: Ensure both IPv4 and IPv6 addresses are whitelisted in Delta Exchange settings
- **Key Rotation**: Regularly rotate API keys for security

### Safe Development Practices
- **Environment Isolation**: Always use testnet for development
- **Error Handling**: Applications include comprehensive error handling for API failures
- **Rate Limiting**: Built-in rate limiting prevents API abuse
- **Credential Security**: Never commit actual API keys to version control

## Known Limitations and Workarounds

### Current Limitations
- **Mock Mode**: References to mock mode in documentation but not implemented in current codebase
- **Test Files**: README mentions Playwright tests that don't exist in the repository
- **Network Dependency**: Full functionality requires internet connectivity to Delta Exchange
- **Limited Offline Testing**: No comprehensive offline testing capability

### Workarounds
- **Offline Development**: Focus on UI and template changes that don't require API connectivity
- **API Testing**: Use testnet environment for safe API testing
- **Error Simulation**: Test error handling by temporarily breaking network connectivity
- **Code Validation**: Use Python compilation and import tests for basic validation

## Integration and Deployment Considerations

### Pre-deployment Checklist
1. **Dependencies**: Verify `pip install -r requirements.txt` succeeds
2. **Configuration**: Ensure `.env` file has correct API credentials for target environment
3. **Network Access**: Verify connectivity to Delta Exchange APIs
4. **API Permissions**: Confirm API keys have appropriate read/trade permissions
5. **Error Handling**: Test application behavior with invalid credentials or network failures

### Monitoring and Maintenance
- **Log Monitoring**: Enable debug logging for troubleshooting
- **API Rate Limits**: Monitor for rate limiting warnings
- **WebSocket Health**: Watch for WebSocket disconnection/reconnection patterns
- **Error Tracking**: Monitor application logs for API authentication failures

---

**Remember**: This application requires live network connectivity to Delta Exchange for full functionality. When working in isolated environments, focus on code quality, compilation validation, and structural changes rather than end-to-end functionality testing.