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
from delta_client import DeltaExchangeClient
import json

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Delta Exchange Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    
    .refresh-button {
        background: linear-gradient(45deg, #1f77b4, #17a2b8);
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        cursor: pointer;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=30)  # Cache for 30 seconds
def get_api_credentials():
    """Get API credentials from environment variables"""
    api_key = os.getenv('DELTA_API_KEY')
    api_secret = os.getenv('DELTA_API_SECRET')
    base_url = os.getenv('DELTA_BASE_URL', 'https://api.delta.exchange')
    use_testnet = os.getenv('USE_TESTNET', 'false').lower() == 'true'
    
    if use_testnet:
        base_url = os.getenv('TESTNET_API_URL', 'https://testnet-api.deltaex.org')
    
    return api_key, api_secret, base_url

@st.cache_resource
def get_delta_client():
    """Initialize Delta Exchange client"""
    api_key, api_secret, base_url = get_api_credentials()
    
    if not api_key or not api_secret:
        st.error("❌ API credentials not found. Please check your .env file.")
        st.stop()
    
    return DeltaExchangeClient(api_key, api_secret, base_url)

def format_currency(amount, currency="USD"):
    """Format currency with proper symbols"""
    if currency == "BTC":
        return f"₿{amount:.6f}"
    elif currency == "USD":
        return f"${amount:,.2f}"
    else:
        return f"{amount:.6f} {currency}"

def format_percentage(value):
    """Format percentage with color coding"""
    color = "green" if value >= 0 else "red"
    return f"<span style='color: {color}; font-weight: bold;'>{value:+.2f}%</span>"

def display_connection_status(client):
    """Display API connection status"""
    st.markdown("### 🔌 Connection Status")
    
    with st.spinner("Testing connection..."):
        is_connected = client.test_connection()
    
    if is_connected:
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
        st.error("Please check your API credentials and network connection.")
        return False

def display_account_balance(client):
    """Display account balance information"""
    st.markdown("### 💰 Account Balance")
    
    try:
        balance_data = client.get_account_balance()
        
        if balance_data.get('success'):
            balances = balance_data.get('result', [])
            
            if balances:
                # Create balance summary
                total_balance_usd = 0
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
                    
                    # Display detailed table
                    st.markdown("#### Detailed Balance")
                    st.dataframe(df_balance, use_container_width=True)
                else:
                    st.info("No balances found.")
            else:
                st.info("No balance data available.")
        else:
            st.error(f"Failed to fetch balance: {balance_data.get('error', 'Unknown error')}")
    
    except Exception as e:
        st.error(f"Error fetching balance: {str(e)}")

def display_positions(client):
    """Display current positions"""
    st.markdown("### 📊 Current Positions")
    
    try:
        positions_data = client.get_positions()
        
        if positions_data.get('success'):
            positions = positions_data.get('result', [])
            
            if positions:
                position_cards = []
                
                for position in positions:
                    if float(position.get('size', 0)) != 0:  # Only show non-zero positions
                        symbol = position.get('product_symbol', 'Unknown')
                        size = float(position.get('size', 0))
                        entry_price = float(position.get('entry_price', 0))
                        unrealized_pnl = float(position.get('unrealized_pnl', 0))
                        liquidation_price = float(position.get('liquidation_price', 0))
                        margin = float(position.get('margin', 0))
                        
                        position_cards.append({
                            'Symbol': symbol,
                            'Size': size,
                            'Side': 'LONG' if size > 0 else 'SHORT',
                            'Entry Price': entry_price,
                            'Unrealized PnL': unrealized_pnl,
                            'Liquidation Price': liquidation_price,
                            'Margin': margin
                        })
                
                if position_cards:
                    df_positions = pd.DataFrame(position_cards)
                    
                    # Display position cards
                    for _, row in df_positions.iterrows():
                        pnl_color = "green" if row['Unrealized PnL'] >= 0 else "red"
                        side_color = "#4CAF50" if row['Side'] == 'LONG' else "#f44336"
                        
                        st.markdown(f"""
                        <div class="metric-card" style="border-left-color: {side_color};">
                            <h4>{row['Symbol']} - {row['Side']}</h4>
                            <div style="display: flex; justify-content: space-between;">
                                <div>
                                    <p><strong>Size:</strong> {row['Size']:.3f}</p>
                                    <p><strong>Entry:</strong> ${row['Entry Price']:,.2f}</p>
                                    <p><strong>Margin:</strong> {format_currency(row['Margin'])}</p>
                                </div>
                                <div style="text-align: right;">
                                    <p style="color: {pnl_color}; font-weight: bold; font-size: 1.2em;">
                                        PnL: {format_currency(row['Unrealized PnL'])}
                                    </p>
                                    <p><strong>Liq. Price:</strong> ${row['Liquidation Price']:,.2f}</p>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Display detailed table
                    st.markdown("#### Position Details")
                    st.dataframe(df_positions, use_container_width=True)
                    
                    # PnL Chart
                    fig = px.bar(
                        df_positions, 
                        x='Symbol', 
                        y='Unrealized PnL',
                        color='Unrealized PnL',
                        color_continuous_scale=['red', 'yellow', 'green'],
                        title="Unrealized PnL by Position"
                    )
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No open positions found.")
            else:
                st.info("No positions data available.")
        else:
            st.error(f"Failed to fetch positions: {positions_data.get('error', 'Unknown error')}")
    
    except Exception as e:
        st.error(f"Error fetching positions: {str(e)}")

def display_orders(client):
    """Display current orders"""
    st.markdown("### 📋 Open Orders")
    
    try:
        orders_data = client.get_orders()
        
        if orders_data.get('success'):
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
                    limit_price = float(order.get('limit_price', 0)) if order.get('limit_price') else None
                    created_at = order.get('created_at', '')
                    order_id = order.get('id', '')
                    
                    order_cards.append({
                        'ID': order_id,
                        'Symbol': symbol,
                        'Side': side,
                        'Type': order_type.replace('_', ' ').title(),
                        'Size': size,
                        'Unfilled': unfilled_size,
                        'Limit Price': limit_price,
                        'Created': created_at[:19] if created_at else 'Unknown'
                    })
                
                df_orders = pd.DataFrame(order_cards)
                
                # Display order cards
                for _, row in df_orders.iterrows():
                    side_color = "#4CAF50" if row['Side'] == 'BUY' else "#f44336"
                    
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
                                <p><strong>Price:</strong> ${row['Limit Price']:,.2f if row['Limit Price'] else 'Market'}</p>
                                <p><strong>Created:</strong> {row['Created']}</p>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Display detailed table
                st.markdown("#### Order Details")
                st.dataframe(df_orders, use_container_width=True)
                
                # Orders by side chart
                side_counts = df_orders['Side'].value_counts()
                fig = px.pie(
                    values=side_counts.values,
                    names=side_counts.index,
                    title="Orders by Side",
                    color_discrete_map={'BUY': '#4CAF50', 'SELL': '#f44336'}
                )
                st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.info("No open orders found.")
        else:
            st.error(f"Failed to fetch orders: {orders_data.get('error', 'Unknown error')}")
    
    except Exception as e:
        st.error(f"Error fetching orders: {str(e)}")

def display_mark_prices(client):
    """Display mark prices for key products"""
    st.markdown("### 📈 Mark Prices")
    
    # Key symbols to monitor
    key_symbols = ['BTCUSD', 'ETHUSD', 'SOLUSD', 'ADAUSD']
    
    try:
        mark_price_data = []
        
        for symbol in key_symbols:
            try:
                product_data = client.get_product_by_symbol(symbol)
                if product_data.get('success'):
                    product = product_data.get('result', {})
                    mark_price = product.get('mark_price')
                    if mark_price:
                        mark_price_data.append({
                            'Symbol': symbol,
                            'Mark Price': float(mark_price),
                            'Status': 'Live'
                        })
                    else:
                        mark_price_data.append({
                            'Symbol': symbol,
                            'Mark Price': 0,
                            'Status': 'No Data'
                        })
            except:
                mark_price_data.append({
                    'Symbol': symbol,
                    'Mark Price': 0,
                    'Status': 'Error'
                })
        
        if mark_price_data:
            df_prices = pd.DataFrame(mark_price_data)
            
            # Display price cards
            cols = st.columns(len(key_symbols))
            for i, (_, row) in enumerate(df_prices.iterrows()):
                with cols[i]:
                    status_color = "#4CAF50" if row['Status'] == 'Live' else "#f44336"
                    st.markdown(f"""
                    <div class="metric-card" style="border-left-color: {status_color};">
                        <h4>{row['Symbol']}</h4>
                        <p style="font-size: 1.5em; font-weight: bold;">
                            ${row['Mark Price']:,.2f if row['Mark Price'] > 0 else 'N/A'}
                        </p>
                        <p><strong>Status:</strong> {row['Status']}</p>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Mark prices chart
            valid_prices = df_prices[df_prices['Mark Price'] > 0]
            if not valid_prices.empty:
                fig = px.bar(
                    valid_prices,
                    x='Symbol',
                    y='Mark Price',
                    title="Current Mark Prices",
                    color='Mark Price',
                    color_continuous_scale='viridis'
                )
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
    
    except Exception as e:
        st.error(f"Error fetching mark prices: {str(e)}")

def main():
    """Main application"""
    # Header
    st.markdown('<h1 class="main-header">📈 Delta Exchange Dashboard</h1>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
        st.markdown("## ⚙️ Settings")
        
        # Auto-refresh settings
        auto_refresh = st.checkbox("Auto Refresh", value=False)
        refresh_interval = st.slider("Refresh Interval (seconds)", 10, 300, 30)
        
        # Manual refresh button
        if st.button("🔄 Refresh Now", type="primary"):
            st.cache_data.clear()
            st.experimental_rerun()
        
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
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Main content
    if is_connected:
        # Account Balance
        display_account_balance(client)
        
        st.markdown("---")
        
        # Positions and Orders in columns
        col1, col2 = st.columns(2)
        
        with col1:
            display_positions(client)
        
        with col2:
            display_orders(client)
        
        st.markdown("---")
        
        # Mark Prices
        display_mark_prices(client)
        
        # Auto-refresh functionality
        if auto_refresh:
            time.sleep(refresh_interval)
            st.experimental_rerun()
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666; margin-top: 2rem;'>"
        "Delta Exchange Dashboard | Built with ❤️ using Streamlit"
        "</div>", 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
