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
from typing import Optional
from streamlit.components.v1 import html

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

# Auto-refresh defaults; softened to reduce flicker
st.session_state.auto_refresh = True
if 'refresh_interval' not in st.session_state:
    # 3 seconds is a good balance for UX vs freshness
    st.session_state.refresh_interval = 3

# Initialize UI session state containers
if 'dismissed_orders' not in st.session_state:
    # Track order IDs we should temporarily hide after a cancel
    st.session_state.dismissed_orders = []

# One-time CSS injection guard
# Custom CSS for modern styling (one-time injection)
if not st.session_state.get('_css_injected'):
    st.session_state['_css_injected'] = True
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
    
    /* Card defaults (light theme) */
    .metric-card {
        background: #ffffff;
        color: #111827; /* slate-900 */
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        border-left: 4px solid #1f77b4;
        margin: 0.5rem 0;
    }
    /* Dark theme cards */
    body[data-theme="dark"] .metric-card {
        background: #1f2937; /* slate-800 */
        color: #e5e7eb;      /* slate-200 */
        border-left-color: #60a5fa; /* lighter blue for contrast */
        box-shadow: 0 2px 12px rgba(0,0,0,0.35);
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
    /* Dark theme sidebar background */
    body[data-theme="dark"] .sidebar-section {
        background: #111827; /* slate-900 */
        color: #e5e7eb;
        box-shadow: 0 1px 6px rgba(0,0,0,0.3);
    }

    /* Tweak sidebar spacing; do not hide inputs globally to avoid UI glitches */
    [data-testid="stSidebar"] .block-container{
        padding-top: 1rem;
    }

    /* Reduce motion and disable transition animations that cause ghost elements */
    *, *::before, *::after {
        animation: none !important;
        transition: none !important;
    }
    /* Ensure Streamlit element containers never linger translucent during reruns */
    [data-testid="stElementContainer"],
    [data-testid="stCaptionContainer"],
    [data-testid="stVerticalBlock"] {
        opacity: 1 !important;
        transform: none !important;
    }
    /* Hide any Streamlit containers that are in the middle of fade-out (ghosts) */
    [data-testid="stElementContainer"][style*="opacity: 0."] { display: none !important; }
    [data-testid="stCaptionContainer"][style*="opacity: 0."] { display: none !important; }
    [data-testid="stVerticalBlock"][style*="opacity: 0."] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# Inject a small MutationObserver once to hide transient low-opacity ghost containers on reruns
if not st.session_state.get('_anti_ghost_js'):
        st.session_state['_anti_ghost_js'] = True
        html(
                """
                <script>
                (function(){
                    const THRESH = 0.99;
                    function hideGhosts(){
                        const nodes = document.querySelectorAll('[data-testid="stElementContainer"], [data-testid="stCaptionContainer"], [data-testid="stVerticalBlock"]');
                        nodes.forEach(el => {
                            const s = window.getComputedStyle(el);
                            const op = parseFloat(s.opacity || '1');
                            if (op < THRESH) {
                                el.style.display = 'none';
                            }
                        });
                    }
                    hideGhosts();
                    const mo = new MutationObserver(() => hideGhosts());
                    mo.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['style','class'] });
                })();
                </script>
                """,
                height=0,
        )

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

def _get_product_id(client: DeltaExchangeClient, symbol: str) -> Optional[int]:
    """Resolve product id for a given symbol via REST."""
    data = safe_api_call(client.get_product_by_symbol, symbol)
    if isinstance(data, dict) and data.get("success") and data.get("result"):
        result = data["result"]
        if isinstance(result, dict):
            return result.get("id")
        if isinstance(result, list) and result:
            return result[0].get("id")
    return None

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
def get_ws_client(base_url: str, api_key: Optional[str] = None, api_secret: Optional[str] = None):
    """Create and return a singleton WS client. Auth if creds provided, subscribe to BTCUSD mark."""
    use_testnet = 'testnet' in base_url.lower()
    ws = DeltaWSClient(use_testnet=use_testnet)
    # Provide creds for private channels when available
    if api_key and api_secret:
        ws.configure_auth(api_key, api_secret)
    ws.connect()
    ws.subscribe_mark(["BTCUSD"])  # public mark price
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

    # Slimmed card to better match balance card height: remove extra rows, tighter spacing
    st.markdown(f"""
    <div class="metric-card" style="border-left-color: {status_color}; text-align: center; padding-top: 0.25rem; padding-bottom: 0.25rem;">
        <h3 style="margin: 0.1rem 0;">BTCUSD{' · WS' if status == 'Live (WS)' else (' · REST' if status == 'Live (REST)' else '')}</h3>
        <p style="font-size: 2.0em; font-weight: bold; margin: 0.2rem 0; line-height: 1.1;">
            {price_display}
        </p>
    </div>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=5)  # Cache positions for more real-time updates
def get_cached_positions(_client):
    """Get cached positions"""
    return safe_api_call(_client.get_positions)

def _get_positions_ws_first(client, ws_client=None):
    """Return list of positions, preferring WS snapshot when available; fallback to REST."""
    positions: list[dict] = []
    try:
        if ws_client and getattr(ws_client, 'is_authenticated', False):
            snap = ws_client.get_positions()  # dict symbol->position
            if isinstance(snap, dict) and snap:
                positions = list(snap.values())
                return positions
    except Exception:
        pass
    # Fallback to REST
    data = get_cached_positions(client)
    if data and data.get('success'):
        return data.get('result', []) or []
    return []

def display_positions(client, ws_client=None):
    """Display current positions"""
    st.markdown("### 📊 Current Positions")
    positions = _get_positions_ws_first(client, ws_client)
    
    if positions:
        
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
                    
                    # Calculate unrealized PnL and percent
                    unrealized_pnl = 0.0
                    pnl_percentage = 0.0
                    # Prefer API-provided unrealized_pnl when available
                    api_upnl = position.get('unrealized_pnl')
                    if api_upnl is not None:
                        try:
                            unrealized_pnl = float(api_upnl)
                        except Exception:
                            unrealized_pnl = 0.0
                    elif current_price:
                        unrealized_pnl = calculate_position_pnl(entry_price, current_price, size)

                    # Compute PnL% as underlying move % times effective leverage
                    if entry_price > 0 and size != 0:
                        # Underlying move percent (signed by position side)
                        underlying_move = ((current_price or entry_price) - entry_price) / entry_price
                        if size < 0:
                            underlying_move = -underlying_move
                        base_pct = underlying_move * 100.0

                        # Determine leverage: prefer DEFAULT_LEVERAGE from .env, else explicit fields, else derive, else 10
                        leverage = None
                        # 1) .env override/preference
                        try:
                            env_lev_raw = os.getenv('DEFAULT_LEVERAGE')
                            if env_lev_raw:
                                env_lev = float(str(env_lev_raw).lower().replace('x', '').strip())
                                if env_lev >= 1:
                                    leverage = env_lev
                        except Exception:
                            pass
                        # 2) Explicit API fields if not set by env
                        if leverage is None:
                            for key in (
                                "leverage", "effective_leverage", "initial_leverage", "actual_leverage",
                                "user_leverage", "selected_leverage", "current_leverage"
                            ):
                                val = position.get(key)
                                if val is not None:
                                    try:
                                        sval = str(val).lower().replace('x', '').strip()
                                        f = float(sval)
                                        if f >= 1:
                                            leverage = f
                                            break
                                    except Exception:
                                        pass

                        if leverage is None:
                            # Try derive from notional / margin
                            try:
                                notional = entry_price * abs(size) * 0.001
                                margin_candidates = []
                                for mkey in (
                                    "position_initial_margin", "initial_margin", "isolated_margin",
                                    "used_margin", "entry_margin", "position_margin", "margin"
                                ):
                                    val_raw = position.get(mkey)
                                    if val_raw is not None:
                                        try:
                                            valf = float(val_raw)
                                            if valf > 0:
                                                margin_candidates.append(valf)
                                        except Exception:
                                            pass
                                if margin_candidates and notional > 0:
                                    leverage = max(notional / min(margin_candidates), 1.0)
                            except Exception:
                                pass
                        if leverage is None:
                            # Sensible default when leverage not provided by API
                            try:
                                leverage = float(os.getenv('DEFAULT_LEVERAGE', '10'))
                            except Exception:
                                leverage = 10.0

                        pnl_percentage = base_pct * leverage
                    
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

@st.cache_data(ttl=2)  # Cache orders briefly to minimize ghost cards after cancel
def get_cached_orders(_client):
    """Get cached orders"""
    # Fetch only open orders to avoid stale/uncancelable IDs
    return safe_api_call(_client.get_orders, state='open')

def _get_orders_ws_first(client, ws_client=None):
    """Return list of open orders, preferring WS snapshot when available; fallback to REST."""
    # WS map keyed by order id -> order dict
    try:
        if ws_client and getattr(ws_client, 'is_authenticated', False):
            omap = ws_client.get_orders()
            if isinstance(omap, dict) and omap:
                # Only include orders that are not in terminal state
                res = []
                for od in omap.values():
                    state = str(od.get('state') or '').lower()
                    if state not in {'cancelled', 'filled', 'closed'}:
                        res.append(od)
                return res
    except Exception:
        pass
    # REST fallback
    data = get_cached_orders(client)
    if data and data.get('success'):
        return data.get('result', []) or []
    return []

def display_orders(client, ws_client=None):
    """Display current open orders with per-order cancel buttons."""
    st.markdown("### 📋 Open Orders")

    open_orders = _get_orders_ws_first(client, ws_client)
    if not open_orders:
        st.info("No open orders found.")
        return
    # Filter out orders that were just canceled in this session to avoid transient ghost cards
    try:
        dismissed = set(st.session_state.get('dismissed_orders', []) or [])
        if dismissed:
            open_orders = [o for o in open_orders if str(o.get('id')) not in {str(x) for x in dismissed}]
    except Exception:
        pass
    # If still empty after filtering, show info
    if not open_orders:
        st.info("No open orders found.")
        return

    for order in open_orders:
        symbol = order.get('product_symbol', 'Unknown')
        size = float(order.get('size', 0))
        unfilled_size = float(order.get('unfilled_size', 0))
        side = (order.get('side') or 'unknown').upper()
        order_type = (order.get('order_type') or 'unknown').replace('_', ' ').title()
        limit_price = order.get('limit_price')
        created_at = order.get('created_at') or ''
        order_id = order.get('id')
        product_id = order.get('product_id')

        side_color = "#4CAF50" if side == 'BUY' else "#f44336"
        price_display = f"${float(limit_price):,.2f}" if limit_price else 'Market'

        # Keyed container prevents Streamlit from reusing/sticking duplicate elements across reruns
        with st.container(key=f"order_card_{order_id}"):
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: {side_color};">
                <h4>{symbol} - {side} {order_type}</h4>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <p><strong>Size:</strong> {size:.3f}</p>
                        <p><strong>Unfilled:</strong> {unfilled_size:.3f}</p>
                        <p><strong>Order ID:</strong> {order_id}</p>
                    </div>
                    <div style="text-align: right;">
                        <p><strong>Price:</strong> {price_display}</p>
                        <p><strong>Created:</strong> {created_at[:19] if created_at else 'Unknown'}</p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            cols = st.columns(2)
            with cols[0]:
                if st.button(f"Cancel {order_id}", key=f"cancel_{order_id}"):
                    resp = client.cancel_order(int(order_id), product_id=product_id, product_symbol=symbol)
                    if isinstance(resp, dict) and resp.get('success'):
                        note = resp.get('note')
                        st.success(f"Canceled {order_id}{' (' + note + ')' if note else ''}")
                        # Remember this order id to hide it immediately in this session
                        try:
                            oid_str = str(order_id)
                            if oid_str not in st.session_state.dismissed_orders:
                                st.session_state.dismissed_orders.append(oid_str)
                        except Exception:
                            pass
                        # Immediately refresh orders to prevent ghost/duplicate cards
                        try:
                            st.cache_data.clear()
                        except Exception:
                            pass
                        st.rerun()
                    else:
                        st.error(f"Cancel failed: {resp}")
            with cols[1]:
                st.caption(created_at or '')

def place_maker_only_order_ui(client):
    """UI to place a maker-only limit order."""
    st.markdown("### 🧩 Place Maker-Only Limit Order")
    cols = st.columns(4)
    with cols[0]:
        symbol = st.text_input("Symbol", value="BTCUSD")
    with cols[1]:
        side = st.segmented_control("Side", options=["buy", "sell"], default="buy") or "buy"
    with cols[2]:
        lots = st.number_input("Lots", min_value=1, max_value=100000, value=1, step=1)
    with cols[3]:
        price = st.number_input("Limit Price (USD)", min_value=1.0, value=100000.0, step=1.0, format="%0.0f")

    if st.button("Place Maker-Only Order", type="primary"):
        pid = _get_product_id(client, symbol)
        if not pid:
            st.error(f"Couldn't resolve product id for {symbol}.")
        else:
            resp = client.place_order(
                product_id=int(pid),
                size=int(lots),
                side=side,
                order_type="limit_order",
                limit_price=str(int(price)),
                time_in_force="gtc",
                post_only=True,
                reduce_only=False,
                client_order_id=f"app_maker_{int(time.time())}"
            )
            if isinstance(resp, dict) and resp.get('success'):
                st.success("Order placed (post-only).")
            else:
                st.error(f"Order failed: {resp}")

def main():
    """Main application"""
    # Header
    st.markdown('<h1 class="main-header">📈 Delta Exchange Dashboard</h1>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        # API Status only
        st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
        client = get_delta_client()
        is_connected = display_connection_status(client)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Main content
    # Prepare WS client once
    api_key, api_secret, base_url = get_api_credentials()
    ws_client = get_ws_client(base_url, api_key, api_secret)

    if is_connected:
        # Top row: Account Balance and Mark Price side-by-side
        top_left, top_right = st.columns(2)
        with top_left:
            with st.container(key="balance_container"):
                display_account_balance(client)
        with top_right:
            with st.container(key="markprice_container"):
                display_btc_mark_price(client, ws_client)

        st.markdown("---")

        # Positions and Orders
        col1, col2 = st.columns(2)
        with col1:
            with st.container(key="positions_container"):
                display_positions(client, ws_client=ws_client)
        with col2:
            with st.container(key="place_order_container"):
                place_maker_only_order_ui(client)
            st.markdown("---")
            with st.container(key="orders_container"):
                display_orders(client, ws_client=ws_client)
    else:
        # Show mark price even in read-only mode
        with st.container(key="markprice_readonly"):
            display_btc_mark_price(None, ws_client)

    # Soft auto-refresh: rerun at a slower cadence without clearing caches (reduces flicker)
    time.sleep(st.session_state.refresh_interval)
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
