import os
import time
from typing import Optional, Dict, Any, List

import streamlit as st
from dotenv import load_dotenv

# Reuse existing REST client (no changes to it)
from src.delta_client import DeltaExchangeClient


st.set_page_config(page_title="Maker-Only Order Tester", layout="centered")

# Load environment variables from .env at startup
load_dotenv()


@st.cache_resource(show_spinner=False)
def get_client(api_key: str, api_secret: str, base_url: str) -> DeltaExchangeClient:
    client = DeltaExchangeClient(api_key=api_key, api_secret=api_secret, base_url=base_url)
    # Best-effort add a User-Agent to avoid rare 403s from CDN
    try:
        client.session.headers.update({"User-Agent": "streamlit-mkt-maker/1.0"})
    except Exception:
        pass
    return client


def get_product_id(client: DeltaExchangeClient, symbol: str) -> Optional[int]:
    data = client.get_product_by_symbol(symbol)
    if isinstance(data, dict) and data.get("success") and data.get("result"):
        result = data["result"]
        # result can be object or list depending on API; support both
        if isinstance(result, dict):
            return result.get("id")
        if isinstance(result, list) and result:
            return result[0].get("id")
    return None


def list_open_orders_for_product(client: DeltaExchangeClient, product_id: int) -> List[Dict[str, Any]]:
    resp = client.get_orders(product_ids=[product_id], state="open")
    if isinstance(resp, dict) and resp.get("success"):
        return resp.get("result", []) or []
    return []


def main():
    st.title("Maker-Only Limit Order Tester")
    st.caption("Quick utility to place post-only (maker) limit orders and cancel existing ones.")

    # Sidebar: connection settings
    st.sidebar.header("Connection")
    # Default environment is LIVE (prod). If USE_TESTNET=true is set, preselect testnet.
    use_testnet_env = os.getenv("USE_TESTNET", "").lower() in ("1", "true", "yes")
    default_base = os.getenv("DELTA_BASE_URL", "https://api.india.delta.exchange")
    base_url = st.sidebar.selectbox(
        "Environment",
        options=["https://api.india.delta.exchange", "https://cdn-ind.testnet.deltaex.org"],
        index=(1 if use_testnet_env else 0),
    )
    # Prefer credentials from .env; fall back to manual input only if missing
    env_api_key = os.getenv("DELTA_API_KEY", "")
    env_api_secret = os.getenv("DELTA_API_SECRET", "")
    api_key = env_api_key
    api_secret = env_api_secret

    if env_api_key and env_api_secret:
        with st.sidebar:
            st.success("Using API credentials from .env")
    else:
        api_key = st.sidebar.text_input("API Key", value=env_api_key)
        api_secret = st.sidebar.text_input("API Secret", value=env_api_secret, type="password")

    if not api_key or not api_secret:
        st.warning("Enter API Key and Secret in the sidebar (or set environment variables).")
        return

    client = get_client(api_key, api_secret, base_url)

    # Show active environment for clarity
    st.info(f"Active environment: {base_url}")

    # Top: simple ping
    col_ping, _ = st.columns([1, 3])
    with col_ping:
        if st.button("Test Connection", use_container_width=True):
            ok = client.test_connection()
            if ok:
                st.success("Connected ✔")
            else:
                st.error("Connection failed. Check keys, URL, or network.")

    st.divider()

    # Inputs for order placement
    st.subheader("Place Maker-Only Limit Order")
    symbol = st.text_input("Symbol", value="BTCUSD", help="Trading symbol (e.g., BTCUSD)")
    side = st.segmented_control("Side", options=["buy", "sell"], default="buy") or "buy"
    lots = st.number_input("Lots (integer)", min_value=1, max_value=100000, value=1, step=1)
    price = st.number_input("Limit Price (USD)", min_value=1.0, value=100000.0, step=1.0, format="%0.0f")

    place_col, _ = st.columns([1, 3])
    with place_col:
        if st.button("Place Maker-Only Order", type="primary", use_container_width=True):
            with st.spinner("Submitting order…"):
                product_id = get_product_id(client, symbol)
                if not product_id:
                    st.error(f"Couldn't resolve product ID for {symbol}.")
                else:
                    resp = client.place_order(
                        product_id=product_id,
                        size=int(lots),
                        side=side,
                        order_type="limit_order",
                        limit_price=str(int(price)),
                        time_in_force="gtc",
                        post_only=True,
                        reduce_only=False,
                        client_order_id=f"maker_test_{int(time.time())}"
                    )
                    if isinstance(resp, dict) and resp.get("success"):
                        st.success("Order placed (post-only).")
                    else:
                        st.error("Order failed.")
                        st.code(resp, language="json")

    st.divider()

    # Open orders and cancel controls
    st.subheader("Open Orders for Symbol")
    product_id = get_product_id(client, symbol) if symbol else None
    if product_id:
        refresh = st.button("Refresh orders", key="refresh_orders")
        orders = list_open_orders_for_product(client, product_id)
        if not orders:
            st.info("No open orders for this symbol.")
        else:
            for o in orders:
                oid = o.get("id")
                side_txt = o.get("side")
                sz = o.get("size")
                px = o.get("limit_price") or o.get("price")
                created = o.get("created_at") or o.get("created_time")
                with st.container(border=True):
                    st.write(f"Order ID: {oid} | {side_txt} {sz} @ {px}")
                    cols = st.columns(2)
                    with cols[0]:
                        if st.button(f"Cancel {oid}", key=f"cancel_{oid}"):
                            # Re-validate that the order still exists and is open
                            current = list_open_orders_for_product(client, product_id)
                            still_open = any(str(x.get("id")) == str(oid) for x in current)
                            if not still_open:
                                st.warning("This order is no longer open (likely filled or already canceled).")
                            else:
                                r = None  # type: ignore[assignment]
                                if oid is None:
                                    st.error("Missing order id; please refresh and try again.")
                                else:
                                    r = client.cancel_order(int(oid), product_id=product_id)
                                    if isinstance(r, dict) and r.get("success"):
                                        note = r.get("note")
                                        st.success(f"Canceled {oid}{' (' + note + ')' if note else ''}")
                                    else:
                                        st.error(f"Cancel failed: {r}")
                    with cols[1]:
                        st.caption(str(created))

            st.divider()
            if st.button("Cancel ALL open orders for this symbol", use_container_width=True, key="cancel_all"):
                r = client.cancel_all_orders(product_ids=[product_id])
                if isinstance(r, dict) and r.get("success"):
                    st.success("All open orders canceled for symbol.")
                else:
                    st.error(f"Cancel-all failed: {r}")
    else:
        st.info("Enter a valid symbol to view/cancel orders.")


if __name__ == "__main__":
    main()
