# Delta Exchange Bot — AI Agent Guide
Version: 3.1.0

## Big picture
- Streamlit dashboard (`app.py`, root) reads from REST + WebSocket clients in `src/` and includes maker-only order placement and per-order cancel.
- REST client: `src/delta_client.py` (HMAC auth fixed; rate-limited; JSON errors preserved).
- WS client: `src/ws_client.py` (public `mark_price` feed; WS-first pricing with REST fallback).
- Docs: `docs/Delta-API-Docs.md`, `docs/strategy/stratergy.md`, `docs/notes/issues.md`.
- Why this layout: keep `app.py` runnable via `streamlit run app.py`; isolate clients under `src/` for reuse.

## Runbook (Windows PowerShell)
- Environment: `.env` in repo root (DELTA_API_KEY/SECRET, USE_TESTNET, DELTA_BASE_URL, TESTNET_API_URL, DELTA_DEBUG_AUTH).
- Install: `pip install -r requirements.txt` (uses `websocket-client`, `streamlit`, etc.).
- Run: `streamlit run app.py` (auto-refresh 1s; no manual toggles). .env is loaded by default; production is the default unless `USE_TESTNET=true`.
- Imports in `app.py` use the new paths: `from src.delta_client import DeltaExchangeClient`, `from src.ws_client import DeltaWSClient`.

## Integration patterns that matter
- Auth signature (fixed): include `?` between path and query when signing if params exist.
  - Message: `method + timestamp + path + ('?' + query if present) + body`.
  - Public GETs (e.g., `/v2/products`, `/v2/history/candles`) must NOT send auth headers.
- Rate limit decorator in REST client wraps key calls (3–5 rps) to stay under API limits.
- Mark price is WS-first: subscribe to `mark_price` channel for `MARK:BTCUSD`; fallback to `/v2/history/candles` with `symbol=MARK:BTCUSD`.
- Streamlit caching: `@st.cache_data(ttl=30)` for balances; `ttl=5` for positions/orders; `@st.cache_resource` for singletons (REST/WS clients). Use underscore param names in cached funcs to avoid unhashable errors.

### Strategy seed-phase (startup invariant)
- On startup, assume one open position of 1 lot at entry price x and exactly two live orders:
  - Same-direction averaging: size 2 at x ∓ 750 (for LONG: x − 750; for SHORT: x + 750).
  - Opposite TP + Flip: size 2 at x ± 300 (for LONG: SHORT 2 at x + 300; for SHORT: BUY 2 at x − 300).
- After any fill: immediately cancel the paired order, update state, and re-place the two orders for the new state.

## Minimal examples from this repo
- Cache WS client singleton and subscribe once:
```python
@st.cache_resource
def get_ws_client(base_url: str):
    use_testnet = 'testnet' in base_url.lower()
    ws = DeltaWSClient(use_testnet=use_testnet)
    ws.connect(); ws.subscribe_mark(["BTCUSD"])
    return ws
```
- WS-first mark price with REST fallback:
```python
ws_price = ws_client.get_latest_mark('BTCUSD')
if not ws_price and client:
    rest = client.get_mark_price('BTCUSD')  # returns {'success': True, 'mark_price': float}
```
- REST signature generation (see `_generate_signature` in `src/delta_client.py`).

## File touchpoints you’ll likely edit
- `app.py`: UI cards/layout, 1s auto-refresh loop, WS-first price display, PnL calc.
- `src/delta_client.py`: Add/adjust REST endpoints; keep auth rules and public-GET exemption.
- `src/ws_client.py`: Subscriptions or additional channels; keep thread-safety and reconnect logic.
- `docs/strategy/stratergy.md`: Strategy spec reference for Phase 2 automation.

## External endpoints and URLs
- REST: prod `https://api.india.delta.exchange`, testnet `https://cdn-ind.testnet.deltaex.org`.
- WS: prod `wss://socket.india.delta.exchange`, testnet `wss://socket-ind.testnet.deltaex.org`.

## Gotchas
- Don’t send auth headers for public GET endpoints.
- When adding GET params, build `url?...` and also include `'?'+query` in signature.
- Keep Streamlit cache params hashable; pass clients via underscore args (e.g., `_client`).
- Avoid multiple WS connections: always go through the cached resource.

## Contact
- Owner: Saqib Sherwani (sole maintainer)
- GitHub: https://github.com/Saqib12333
- Email: sherwanisaqib@gmail.com
- Avatar: https://github.com/Saqib12333.png?size=200
