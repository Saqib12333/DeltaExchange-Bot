import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime
from typing import Dict, List, Any
import os
from dotenv import load_dotenv
from src.delta_client import DeltaExchangeClient
from src.ws_client import DeltaWSClient
import json
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Delta Exchange Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 1s auto-refresh default; no manual controls
st.session_state.auto_refresh = True
st.session_state.refresh_interval = 1

# Custom CSS for modern styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
        background: linear-gradient(90deg, #1f77b4, #ff7f0e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        border-left: 4px solid #1f77b4;
        margin: 0.5rem 0;
    }
    
    .status-card {
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        color: white;
        font-weight: bold;
    }
    
    .status-success {
        background: linear-gradient(45deg, #4CAF50, #45a049);
    }
    
    .status-error {
        background: linear-gradient(45deg, #f44336, #da190b);
    }
    
    .data-table {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    
    .sidebar-section {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=30)  # Reasonable cache time
def get_api_credentials():
    """Get API credentials from environment variables"""
    api_key = os.getenv('DELTA_API_KEY')
    api_secret = os.getenv('DELTA_API_SECRET')
    base_url = os.getenv('DELTA_BASE_URL', 'https://api.india.delta.exchange')
    use_testnet = os.getenv('USE_TESTNET', 'false').lower() == 'true'
    
    if use_testnet:
        # Use documented REST testnet endpoint by default
        base_url = os.getenv('TESTNET_API_URL', 'https://cdn-ind.testnet.deltaex.org')
    
    return api_key, api_secret, base_url

@st.cache_resource
def get_delta_client():
    """Initialize Delta Exchange client. Returns None if credentials missing (read-only mode)."""
    api_key, api_secret, base_url = get_api_credentials()
    if not api_key or not api_secret:
        return None
    return DeltaExchangeClient(api_key, api_secret, base_url)

def safe_api_call(func, *args, **kwargs):
    """Safely execute API call with proper error handling"""
    try:
        result = func(*args, **kwargs)
        if isinstance(result, dict) and not result.get('success', False):
            st.error(f"API Error: {result.get('error', 'Unknown error')}")
            return None
        return result
    except Exception as e:
        logger.error(f"API call failed: {str(e)}")
        st.error(f"Connection Error: {str(e)}")
        return None

def format_currency(amount, currency="USD"):
    """Format currency with proper symbols"""
    if amount is None:
        return "N/A"
    try:
        if currency == "BTC":
            return f"₿{amount:.6f}"
        elif currency == "USD":
            return f"${amount:,.2f}"
        else:
            return f"{amount:.6f} {currency}"
    except (TypeError, ValueError):
        return f"N/A {currency}"

def format_percentage(value):
    """Format percentage with color coding"""
    if value is None:
        return "N/A"
    try:
        color = "green" if value >= 0 else "red"
        return f"<span style='color: {color}; font-weight: bold;'>{value:+.2f}%</span>"
    except (TypeError, ValueError):
        return "N/A"

def display_connection_status(client):
    """Display API connection status"""
    st.markdown("### 🔌 Connection Status")
    if client is None:
        st.markdown("""
        <div class="status-card status-error">
            ⚠️ API credentials not found. Running in read-only mode (public data only).
        </div>
        """, unsafe_allow_html=True)
        return False

    with st.spinner("Testing connection..."):
        result = safe_api_call(client.test_connection)
    
    if result:
        st.markdown("""
        <div class="status-card status-success">
            ✅ Connected to Delta Exchange API
        </div>
        """, unsafe_allow_html=True)
        return True
    else:
        st.markdown("""
        <div class="status-card status-error">
            ❌ Failed to connect to Delta Exchange API
        </div>
        """, unsafe_allow_html=True)
        return False

@st.cache_data(ttl=30)  # Cache balance for 30 seconds
def get_cached_balance(_client):
    """Get cached account balance"""
    return safe_api_call(_client.get_account_balance)

def display_account_balance(client):
    """Display account balance information"""
    st.markdown("### 💰 Account Balance")
    
    balance_data = get_cached_balance(client)
    
    if balance_data and balance_data.get('success'):
        balances = balance_data.get('result', [])
        
        if balances:
            balance_cards = []
            
            for balance in balances:
                asset_symbol = balance.get('asset_symbol', 'Unknown')
                available = float(balance.get('available_balance', 0))
                total = float(balance.get('balance', 0))
                
                if total > 0:  # Only show non-zero balances
                    balance_cards.append({
                        'Asset': asset_symbol,
                        'Available': available,
                        'Total': total,
                        'Locked': total - available
                    })
            
            if balance_cards:
                df_balance = pd.DataFrame(balance_cards)
                
                # Display balance cards
                cols = st.columns(len(balance_cards))
                for i, (_, row) in enumerate(df_balance.iterrows()):
                    with cols[i]:
                        st.markdown(f"""
                        <div class="metric-card">
                            <h4>{row['Asset']}</h4>
                            <p><strong>Available:</strong> {format_currency(row['Available'], row['Asset'])}</p>
                            <p><strong>Total:</strong> {format_currency(row['Total'], row['Asset'])}</p>
                            <p><strong>Locked:</strong> {format_currency(row['Locked'], row['Asset'])}</p>
                        </div>
                        """, unsafe_allow_html=True)
                
                # Table removed to avoid redundancy per issues.md
            else:
                st.info("No balances found.")
        else:
            st.info("No balance data available.")
    else:
        st.warning("Unable to fetch balance data.")

def calculate_position_pnl(entry_price, current_price, size, contract_value=0.001):
    """Calculate unrealized PnL for a position"""
    if not current_price or current_price <= 0 or not entry_price or entry_price <= 0:
        return 0.0
    
    try:
        # For perpetual futures: PnL = (current_price - entry_price) * size * contract_value
        if size > 0:  # Long position
            pnl = (current_price - entry_price) * size * contract_value
        else:  # Short position  
            pnl = (entry_price - current_price) * abs(size) * contract_value
        
        return pnl
    except (TypeError, ValueError):
        return 0.0

def get_btc_mark_price_rest(_client):
    """Get BTCUSD mark price via REST (fallback)"""
    return safe_api_call(_client.get_mark_price, 'BTCUSD')

@st.cache_resource
def get_ws_client(base_url: str):
    """Create and return a singleton WS client subscribed to MARK:BTCUSD."""
    use_testnet = 'testnet' in base_url.lower()
    ws = DeltaWSClient(use_testnet=use_testnet)
    ws.connect()
    ws.subscribe_mark(["BTCUSD"])
    return ws

def display_btc_mark_price(client, ws_client):
    """Display BTCUSD mark price only"""
    st.markdown("### ₿ BTCUSD Mark Price")
    # Try WS first
    ws_entry_price = ws_client.get_latest_mark('BTCUSD') if ws_client else None
    current_price = None
    status = 'Loading...'
    if ws_entry_price:
        current_price = ws_entry_price
        status = 'Live (WS)'
    else:
        # Fallback to REST if client is available
        if client is not None:
            price_data = get_btc_mark_price_rest(client)
            if price_data and price_data.get('success'):
                current_price = price_data.get('mark_price')
                status = 'Live (REST)' if current_price else 'Loading...'
            else:
                status = 'Error'
        else:
            status = 'WS only (no API)'
    
    # Display price card
    is_live = isinstance(status, str) and status.startswith('Live')
    status_color = "#4CAF50" if is_live else "#ff9800" if status == 'Loading...' else "#f44336"
    price_display = f"${current_price:,.2f}" if current_price and current_price > 0 else status
    
    st.markdown(f"""
    <div class="metric-card" style="border-left-color: {status_color}; text-align: center;">
        <h2>BTCUSD</h2>
        <p style="font-size: 2.5em; font-weight: bold; margin: 1rem 0;">
            {price_display}
        </p>
        <p><strong>Status:</strong> {status}</p>
        <p><small>Last updated: {datetime.now().strftime('%H:%M:%S')}</small></p>
    </div>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=5)  # Cache positions for more real-time updates
def get_cached_positions(_client):
    """Get cached positions"""
    return safe_api_call(_client.get_positions)

def display_positions(client, ws_client=None):
    """Display current positions"""
    st.markdown("### 📊 Current Positions")
    
    positions_data = get_cached_positions(client)
    
    if positions_data and positions_data.get('success'):
        positions = positions_data.get('result', [])
        
        if positions:
            position_cards = []
            
            for position in positions:
                size = float(position.get('size', 0))
                if size != 0:  # Only show non-zero positions
                    symbol = position.get('product_symbol', 'Unknown')
                    entry_price = float(position.get('entry_price', 0))
                    
                    # Get current mark price for PnL calculation (only for BTCUSD)
                    current_price = None
                    if symbol == 'BTCUSD':
                        # Prefer WS price
                        ws_entry_price = ws_client.get_latest_mark('BTCUSD') if ws_client else None
                        if ws_entry_price:
                            current_price = ws_entry_price
                        else:
                            price_data = get_btc_mark_price_rest(client)
                            if price_data and price_data.get('success'):
                                current_price = price_data.get('mark_price')
                    
                    # Calculate unrealized PnL if we have current price
                    unrealized_pnl = 0.0
                    pnl_percentage = 0.0
                    if current_price:
                        unrealized_pnl = calculate_position_pnl(entry_price, current_price, size)
                        if entry_price > 0:
                            pnl_percentage = (unrealized_pnl / (entry_price * abs(size) * 0.001)) * 100
                    
                    position_cards.append({
                        'Symbol': symbol,
                        'Size': size,
                        'Side': 'LONG' if size > 0 else 'SHORT',
                        'Entry Price': entry_price,
                        'Current Price': current_price or 0,
                        'Unrealized PnL': unrealized_pnl,
                        'PnL %': pnl_percentage
                    })
            
            if position_cards:
                df_positions = pd.DataFrame(position_cards)
                
                # Display position cards
                for _, row in df_positions.iterrows():
                    pnl_color = "green" if row['Unrealized PnL'] >= 0 else "red"
                    side_color = "#4CAF50" if row['Side'] == 'LONG' else "#f44336"
                    
                    current_price_display = f"${row['Current Price']:,.2f}" if row['Current Price'] > 0 else 'N/A'
                    
                    st.markdown(f"""
                    <div class="metric-card" style="border-left-color: {side_color};">
                        <h4>{row['Symbol']} - {row['Side']}</h4>
                        <div style="display: flex; justify-content: space-between;">
                            <div>
                                <p><strong>Size:</strong> {row['Size']:.3f}</p>
                                <p><strong>Entry:</strong> ${row['Entry Price']:,.2f}</p>
                                <p><strong>Current:</strong> {current_price_display}</p>
                            </div>
                            <div style="text-align: right;">
                                <p style="color: {pnl_color}; font-weight: bold; font-size: 1.2em;">
                                    PnL: {format_currency(row['Unrealized PnL'])}
                                </p>
                                <p style="color: {pnl_color}; font-weight: bold;">
                                    {row['PnL %']:+.2f}%
                                </p>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Table removed to avoid redundancy per issues.md
            else:
                st.info("No open positions found.")
        else:
            st.info("No positions data available.")
    else:
        st.warning("Unable to fetch positions data.")

@st.cache_data(ttl=5)  # Cache orders for 5 seconds
def get_cached_orders(_client):
    """Get cached orders"""
    return safe_api_call(_client.get_orders)

def display_orders(client):
    """Display current orders"""
    st.markdown("### 📋 Open Orders")
    
    orders_data = get_cached_orders(client)
    
    if orders_data and orders_data.get('success'):
        orders = orders_data.get('result', [])
        
        # Filter for open orders
        open_orders = [order for order in orders if order.get('state') == 'open']
        
        if open_orders:
            order_cards = []
            
            for order in open_orders:
                symbol = order.get('product_symbol', 'Unknown')
                size = float(order.get('size', 0))
                unfilled_size = float(order.get('unfilled_size', 0))
                side = order.get('side', 'Unknown').upper()
                order_type = order.get('order_type', 'Unknown')
                limit_price = order.get('limit_price')
                created_at = order.get('created_at', '')
                order_id = order.get('id', '')
                
                order_cards.append({
                    'ID': order_id,
                    'Symbol': symbol,
                    'Side': side,
                    'Type': order_type.replace('_', ' ').title(),
                    'Size': size,
                    'Unfilled': unfilled_size,
                    'Limit Price': float(limit_price) if limit_price else None,
                    'Created': created_at[:19] if created_at else 'Unknown'
                })
            
            df_orders = pd.DataFrame(order_cards)
            
            # Display order cards
            for _, row in df_orders.iterrows():
                side_color = "#4CAF50" if row['Side'] == 'BUY' else "#f44336"
                price_display = f"${row['Limit Price']:,.2f}" if row['Limit Price'] else 'Market'
                
                st.markdown(f"""
                <div class="metric-card" style="border-left-color: {side_color};">
                    <h4>{row['Symbol']} - {row['Side']} {row['Type']}</h4>
                    <div style="display: flex; justify-content: space-between;">
                        <div>
                            <p><strong>Size:</strong> {row['Size']:.3f}</p>
                            <p><strong>Unfilled:</strong> {row['Unfilled']:.3f}</p>
                            <p><strong>Order ID:</strong> {row['ID']}</p>
                        </div>
                        <div style="text-align: right;">
                            <p><strong>Price:</strong> {price_display}</p>
                            <p><strong>Created:</strong> {row['Created']}</p>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Table removed to avoid redundancy per issues.md
        else:
            st.info("No open orders found.")
    else:
        st.warning("Unable to fetch orders data.")

def main():
    """Main application"""
    # Header
    st.markdown('<h1 class="main-header">📈 Delta Exchange Dashboard</h1>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
        st.markdown("## ⚙️ Dashboard Settings")
        st.info("Auto-refresh: 1s (fixed)")
        st.markdown('</div>', unsafe_allow_html=True)

        # API Status
        st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
        client = get_delta_client()
        is_connected = display_connection_status(client)
        st.markdown('</div>', unsafe_allow_html=True)

        # Environment info
        st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
        st.markdown("### 🌐 Environment")
        _, _, base_url = get_api_credentials()
        env_type = "🧪 Testnet" if "testnet" in base_url.lower() else "🚀 Production"
        st.markdown(f"**Environment:** {env_type}")
        st.markdown(f"**API URL:** {base_url}")
        st.markdown(f"**Auto-Refresh:** Every {st.session_state.refresh_interval} seconds")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Main content
    if is_connected:
        # Account Balance
        display_account_balance(client)
        
        st.markdown("---")
        
        # Positions and Orders in columns
        col1, col2 = st.columns(2)
        
        with col1:
            display_positions(client, ws_client=get_ws_client(base_url))
        
        with col2:
            display_orders(client)
    
    st.markdown("---")
    
    # BTCUSD Mark Price only (WS preferred) - available even in read-only mode
    _, _, base_url = get_api_credentials()
    ws_client = get_ws_client(base_url)
    display_btc_mark_price(client if is_connected else None, ws_client)

    # Improved auto-refresh: countdown then refresh
    refresh_placeholder = st.empty()
    for i in range(st.session_state.refresh_interval, 0, -1):
        refresh_placeholder.info(f"🔄 Auto-refreshing in {i} seconds...")
        time.sleep(1)
    refresh_placeholder.empty()
    st.cache_data.clear()
    st.rerun()
    
    # Footer
    st.markdown("---")
    refresh_status = f"Auto-refreshes every {st.session_state.refresh_interval} seconds" if st.session_state.auto_refresh else "Manual refresh only"
    st.markdown(
        f"<div style='text-align: center; color: #666; margin-top: 2rem;'>"
        f"Delta Exchange Dashboard | Built with ❤️ using Streamlit | {refresh_status}"
        f"</div>", 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
