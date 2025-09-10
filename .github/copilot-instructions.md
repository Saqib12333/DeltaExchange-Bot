# Delta Exchange Bot — AI Agent Guide
Version: 3.3.0

## Big picture
- Primary UI: FastAPI + HTMX server (`server/main.py`) with server-push over WebSockets for mark, balances, positions, and orders. Zero full-page reruns, minimal flicker.
- Legacy UI: Streamlit dashboard (`app.py`) remains available but is no longer primary.
- REST client: `src/delta_client.py` (HMAC auth with `?` for query; IPv4 toggle via `DELTA_FORCE_IPV4`; rate-limited).
- WS client: `src/ws_client.py` (`DeltaWSClient`) supporting public mark and private channels (if configured) used by the server.
- Docs: `docs/Delta-API-Docs.md`, `docs/strategy/stratergy.md`, `docs/notes/issues.md`.

## Runbook (Windows PowerShell)
- Environment: `.env` in repo root (DELTA_API_KEY/SECRET, USE_TESTNET, DELTA_BASE_URL, TESTNET_API_URL, DELTA_DEBUG_AUTH, optional DELTA_FORCE_IPV4). For local demos set `MOCK_DELTA=true` to use synthetic data without keys.
- Install: `pip install -r requirements.txt`.
- Run server: `python -m uvicorn server.main:app --reload --host 127.0.0.1 --port 8000` then open http://127.0.0.1:8000.
- Run legacy UI: `streamlit run app.py`.

## Integration patterns that matter
- Auth signature: `method + timestamp + path + ('?' + query if present) + body`; never auth public GETs.
- Server publishes partial HTML (Jinja templates) to HTMX WS endpoints: `/ws/mark`, `/ws/balances`, `/ws/positions`, `/ws/orders`.
- Balances fetched via REST on a slower cadence; orders/positions/marks come from WS snapshots.

## File touchpoints you’ll likely edit
- `server/main.py`: WS topics, broadcast cadence, mock mode, order routes.
- `server/templates/*`: Templates for partial sections.
- `src/delta_client.py`: REST surfaces for orders/balances/products.
- `src/ws_client.py`: Private channel handling and getters.

## External endpoints and URLs
- REST: prod `https://api.india.delta.exchange`, testnet `https://cdn-ind.testnet.deltaex.org`.
- WS: prod `wss://socket.india.delta.exchange`, testnet `wss://socket-ind.testnet.deltaex.org`.

## Gotchas
- Avoid sending auth headers on public GETs; when adding GET params, include `'?'+query` in the signature. If you see IPv6 whitelist errors, set `DELTA_FORCE_IPV4=true`.
- Avoid multiple WS connections; reuse the singleton in the server.

## Tests
- Playwright E2E: first run `python -m playwright install --with-deps`, then `pytest -q tests/test_e2e_playwright.py`. This uses `MOCK_DELTA=true` and asserts live updates.

## Contact
- Owner: Saqib Sherwani (sole maintainer)
- GitHub: https://github.com/Saqib12333
- Email: sherwanisaqib@gmail.com
- Avatar: https://github.com/Saqib12333.png?size=200
