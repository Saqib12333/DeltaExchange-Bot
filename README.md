# 🚀 Delta Exchange Trading Bot

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.0+-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-3.0.2-informational.svg)](#)

A powerful cryptocurrency trading automation system for Delta Exchange India, featuring real-time portfolio monitoring and a planned automated strategy engine.

![Dashboard Preview](https://via.placeholder.com/800x400/1f77b4/ffffff?text=Delta+Exchange+Dashboard)

## ✨ Features

### 📊 Real-Time Portfolio Dashboard — FULLY OPERATIONAL
- **Live Account Balance** - Monitor your wallet balances across all cryptocurrencies
- **Position Tracking** - View open positions with accurate P&L calculations using real mark prices
- **Order Management** - Track all open orders with properly formatted status information
- **BTCUSD Mark Price** - Real-time accurate price monitoring with status indicators
- **1s Auto-Refresh** - Fixed 1-second refresh cadence (no manual controls)
- **WebSocket Mark Price** - Live WS feed for BTCUSD with REST candles as fallback
- **Modern UI** - Beautiful, responsive interface with professional error handling
- **Stable Performance** - Fixed caching issues and crashes

### 🤖 Automated Trading Strategy — IN DEVELOPMENT
- **Haider Strategy** - Advanced averaging and take-profit system (Phase 2)
- **Risk Management** - Built-in position size limits and distance constraints
- **State Tracking** - Intelligent order management with automatic state transitions
- **Testnet Support** - Safe testing environment before live trading

### 🔒 Security & Reliability
- **Fixed Authentication** - HMAC-SHA256 with proper query string formatting
- **Rate Limiting** - Prevents API abuse with intelligent request throttling
- **Environment Isolation** - Separate testnet and production configurations
- **Comprehensive Error Handling** - Safe API calls with graceful degradation
- **Request Timeouts** - 30-second timeouts prevent hanging requests

## 🎉 Recent Critical Fixes (September 2025)

- **API Authentication**: Correct signature generation. When signing, include a '?' between path and query if query params exist. Public GET endpoints skip auth headers.
- **Caching Stability**: Fixed Streamlit cache issues by using underscore-prefixed `_client` params in cached functions and tuned TTLs.
- **WS-first Mark Price**: Added WebSocket mark price for BTCUSD with REST candles fallback using `MARK:BTCUSD`.
- **UI Simplification**: Removed manual refresh controls and redundant tables; card-first UI.
- **Auto-Refresh**: Fixed 1-second auto-refresh with countdown placeholder and safe rerun.
- **Rate Limiting & Timeouts**: Added decorators and consistent 30s request timeouts.

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Delta Exchange account with API access
- Basic knowledge of cryptocurrency trading

### 1. Clone the Repository
```bash
git clone https://github.com/Saqib12333/DeltaExchange-Bot.git
cd DeltaExchange-Bot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Create a `.env` file in the project root:
```env
DELTA_API_KEY=your_api_key_here
DELTA_API_SECRET=your_api_secret_here
USE_TESTNET=true  # Set to false for production
# Optionally override base URLs
DELTA_BASE_URL=https://api.india.delta.exchange
TESTNET_API_URL=https://cdn-ind.testnet.deltaex.org
# Optional: enable verbose auth debug logs
DELTA_DEBUG_AUTH=false
```

### 4. Get Your API Keys
1. Visit [Delta Exchange India API Settings](https://www.delta.exchange/app/account/api)
2. Create a new API key with appropriate permissions:
   - **Phase 1** (Monitoring): Read-only access
   - **Phase 2** (Trading): Read + Trade access
3. **IMPORTANT**: Whitelist both your IPv4 and IPv6 addresses:
   - Get IPv4: `curl https://api.ipify.org` 
   - Get IPv6: `curl https://api6.ipify.org`
4. Copy your API key and secret to the `.env` file

### 5. Run the Application
```bash
# Windows PowerShell (optional venv shown):
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

## 📱 Using the Dashboard

### Connection Status
The dashboard will automatically test your API connection and display the status. Ensure you see a green "Connected" indicator before proceeding.

### Portfolio Overview
- **Account Balance**: View your available and total balances across all assets
- **Positions**: Monitor open positions with real-time P&L calculations using accurate mark prices
- **Orders**: Track pending orders and their current status
- **BTCUSD Mark Price**: Live price feed with status indicators (Live/Loading/Error)

### Refresh Behavior
- Auto-Refresh: Fixed at 1 second for a live experience (no manual controls)
- Optimized: Smart caching for positions/orders; mark price via WebSocket (REST fallback)

### Performance Characteristics
- Low CPU usage in practice with 1s cadence and caching
- Intelligent caching with appropriate TTL values
- Built-in rate limiting to prevent API abuse
- Error resilient: continues working even with transient failures

## 🎯 Trading Strategy: "Haider Strategy"

The bot implements a sophisticated averaging and take-profit system designed for BTCUSD futures trading:

### Strategy Overview
- **Initial Position**: Start with 1 lot (0.001 BTC) in either LONG or SHORT direction
- **Dual Order System**: Always maintain exactly 2 orders (take-profit + averaging)
- **Progressive Scaling**: Scale positions through 1 → 3 → 9 → 27 lots
- **Fixed Distances**: Predetermined price offsets for optimal risk management

### Risk Management
- **Maximum Position**: Capped at 27 lots (0.027 BTC)
- **Take-Profit Levels**: 300 → 200 → 100 → 50 USD offsets
- **Averaging Distances**: 750 USD initial, then 500 USD intervals
- **Immediate Cancellation**: Cancel paired orders upon any fill to maintain strategy integrity

### Strategy States
1. **Seed (1 lot)**: Initial position with TP at ±300 and averaging at ±750
2. **First Average (3 lots)**: TP at ±200, next averaging at -500 from first
3. **Second Average (9 lots)**: TP at ±100, final averaging at -500 from second
4. **Maximum (27 lots)**: Final TP at ±50, no further averaging

## 🔧 Configuration

### Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `DELTA_API_KEY` | Your Delta Exchange API key | Required |
| `DELTA_API_SECRET` | Your Delta Exchange API secret | Required |
| `USE_TESTNET` | Use testnet environment | `true` |
| `DELTA_BASE_URL` | Production API URL | `https://api.india.delta.exchange` |
| `TESTNET_API_URL` | Testnet API URL | `https://cdn-ind.testnet.deltaex.org` |
| `DELTA_DEBUG_AUTH` | Print signature_data for debugging | `false` |

### Testnet vs Production
- **Testnet**: Safe environment for testing strategies without real money
- **Production**: Live trading with real funds (requires extra caution)

Always test your strategy thoroughly on testnet before switching to production!

## 📊 Project Structure

```
DeltaExchange-Bot/
├── app.py               # Main dashboard application
├── delta_client.py      # Delta Exchange API client
├── requirements.txt     # Python dependencies
├── Delta-API-Docs.md    # API reference snapshot
├── Stratergy/
│   └── stratergy.md    # Detailed strategy specification
└── .github/
    └── copilot-instructions.md  # Development guidelines
```

## 🛡️ Security Best Practices

### API Key Management
- Never commit your actual API keys to version control
- Use environment variables for all sensitive data
- Regularly rotate your API keys
- Grant minimum required permissions

### Trading Safety
- Always start with testnet to understand the system
- Set appropriate position size limits
- Monitor your trades regularly
- Have a plan for emergency situations

### Production Checklist
- [ ] API keys configured with correct permissions
- [ ] Strategy parameters validated on testnet
- [ ] Risk management rules understood
- [ ] Monitoring setup in place
- [ ] Emergency stop procedures defined

## 🐛 Troubleshooting

### Common Issues

**"API credentials not found"**
- Verify your `.env` file exists and contains valid API keys
- Check that variable names match exactly: `DELTA_API_KEY`, `DELTA_API_SECRET`

### Recent Critical Fixes (September 2025) ✅
- **API Authentication Fixed**: Resolved signature generation issue with query string formatting
- **UI Formatting Errors**: Fixed all f-string formatting crashes in orders and mark prices display
- **Accurate Mark Prices**: Implemented proper mark price fetching using historical candles endpoint
- **Real-time Updates**: WebSocket mark price first, REST fallback
- **Automatic Refresh**: 1-second default, no manual settings

**"Failed to connect to Delta Exchange API"**
- Verify your API keys are correct and active
- Check your internet connection
- **IMPORTANT**: Ensure both your IPv4 and IPv6 addresses are whitelisted in Delta Exchange API settings
- If using IP whitelisting, get your current IP with: `curl https://api.ipify.org` (IPv4) or `curl https://api6.ipify.org` (IPv6)
- Ensure you're using the correct environment (testnet vs production)

**"Invalid signature"**
- Ensure signature message uses: `method + timestamp + path + ('?' + query_string if present) + body`
- Public GET endpoints should not send auth headers
- Set `DELTA_DEBUG_AUTH=true` to log `signature_data` and verify locally
- Check for extra spaces or wrong secrets in `.env`

**Dashboard not loading**
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check Python version (requires 3.8+)
- Try running `streamlit --version` to verify Streamlit installation

### Getting Help

1. Check the [Issues](https://github.com/Saqib12333/DeltaExchange-Bot/issues) page for known problems
2. Review the detailed strategy documentation in `Stratergy/stratergy.md`
3. Enable debug logging to get more detailed error information
4. Create a new issue with detailed error messages and steps to reproduce

## 🤝 Contributing

We welcome contributions to improve the Delta Exchange Trading Bot! Here's how you can help:

### Development Setup
1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and test thoroughly
4. Run the app: `streamlit run app.py`
5. Submit a pull request with a clear description

### Areas for Contribution
- Additional trading strategies
- Enhanced UI/UX features
- Performance optimizations
- Documentation improvements
- Bug fixes and security enhancements

### Code Standards
- Follow PEP 8 Python style guidelines
- Add docstrings for all functions and classes
- Include unit tests for new features
- Update documentation for any API changes

## 📋 Roadmap

### Phase 1: Portfolio Monitoring ✅
- [x] Real-time dashboard
- [x] API integration
- [x] Position and order tracking
- [x] Mark price monitoring

### Phase 2: Strategy Automation 🚧
- [ ] Automated order placement
- [ ] Strategy state machine implementation
- [x] WebSocket integration for real-time mark price updates
- [ ] Position state persistence

### Phase 3: Advanced Features 📋
- [ ] Multiple strategy support
- [ ] Backtesting capabilities
- [ ] Performance analytics
- [ ] Mobile-responsive design
- [ ] Telegram/Discord notifications

## ⚠️ Disclaimer

**IMPORTANT: This software is for educational and research purposes. Cryptocurrency trading involves significant financial risk.**

- **No Financial Advice**: This bot does not provide financial advice
- **Use at Your Own Risk**: You are responsible for all trading decisions
- **Test Thoroughly**: Always test strategies on testnet first
- **Monitor Actively**: Automated trading requires supervision
- **Risk Management**: Never risk more than you can afford to lose

The developers are not responsible for any financial losses incurred while using this software.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Delta Exchange](https://www.delta.exchange/) for providing the trading platform and API
- [Streamlit](https://streamlit.io/) for the amazing dashboard framework
- [Plotly](https://plotly.com/) for beautiful data visualizations
- The cryptocurrency trading community for strategy insights

---

<div align="center">

**⭐ Star this repository if you find it helpful!**

[Report Bug](https://github.com/Saqib12333/DeltaExchange-Bot/issues) • [Request Feature](https://github.com/Saqib12333/DeltaExchange-Bot/issues) • [Documentation](https://github.com/Saqib12333/DeltaExchange-Bot/wiki)

Made with ❤️ for the crypto trading community

</div>