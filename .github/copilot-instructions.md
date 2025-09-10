## Delta Exchange Bot – AI Agent Guide (v4.1)
Purpose: Give an AI agent just enough project‑specific context to safely extend or debug the trading dashboard without re‑deriving architecture.

### 1. Architecture (why it looks this way)
- FastAPI + HTMX + WebSockets (in `server/main.py`) push pre‑rendered Jinja partials → no full reruns, minimal flicker (Streamlit `app.py` kept only as legacy).
- Data flow: Delta WS (mark, orders, positions) → in‑memory snapshots → render partial templates (`server/templates/_*.html`) → broadcast over topic WS endpoints (`/ws/mark|balances|positions|orders`). Balances lack a private WS channel, so REST polls every ~30s.
- Separation: `src/ws_client.py` handles resilient WS (auth + heartbeat + private subs). `src/delta_client.py` handles signed REST (HMAC, rate limiting, IPv4 force option) and REST fallbacks when WS not yet hydrated.

### 2. Environment & Modes
- `.env` keys: `DELTA_API_KEY`, `DELTA_API_SECRET`, `USE_TESTNET`, `DELTA_BASE_URL`, optional `DELTA_FORCE_IPV4`, `DELTA_DEBUG_AUTH`, `MOCK_DELTA`.
- Mock mode: if `MOCK_DELTA=true` OR no keys → deterministic synthetic price (~60k), 1 long position, 1 open order. Disable for real data before validating numbers.
- Testnet vs prod: set `USE_TESTNET`; URLs auto‑switch; only override if Delta changes CDN endpoints.

### 3. Auth & Request Rules (critical)
- Signature string: `method + timestamp + path + ('?' + query if query) + body` (body = compact JSON used verbatim in request). Public GETs (products, candles, orderbook) must NOT include auth headers.
- WS auth: send `type=auth` with HMAC of `GET + timestamp + /live` before subscribing to private `orders`/`positions`.
- Avoid duplicate WS connections—reuse the singleton `DeltaWSClient` inside `DataService`.

### 4. Update Loop Semantics
- `DataService._real_loop`: every ~1s collects mark/positions/orders from WS; if positions/orders empty (startup gap) it hydrates once via REST. Balances updated when 30s elapsed. Only broadcasts when a diff vs previous snapshot (simple dict compare) to cut chatter.
- PnL in `_positions.html`: computed as `(mark - entry) * size` (size sign conveys long/short). Side inferred from explicit direction or size sign.

### 5. Key Files Cheat Sheet
- `server/main.py`: lifecycle (startup hooks), maker‑only order route, cancel route, WS topic endpoints, mock vs real loop.
- `server/templates/_mark.html`, `_balances.html`, `_positions.html`, `_orders.html`: partials—modify formatting ONLY here; keep business logic in Python.
- `src/delta_client.py`: REST helpers (`get_positions`, `get_orders`, `place_order`, `cancel_order` with multi‑strategy fallbacks, `get_mark_price` via candles `MARK:SYMBOL`). Rate limiting decorator present—respect or extend rather than remove.
- `src/ws_client.py`: Threaded WS client (heartbeat, auth, subscriptions queue). Use `subscribe_mark(["BTCUSD"])` (client prefixes MARK: internally). State getters copy data under a lock.

### 6. Common Pitfalls / Gotchas
- Wrong numbers usually mean mock mode still on—check `MOCK_DELTA` before debugging math.
- Signature mismatches: nearly always missing the `?` before query string in message assembly, or pretty‑printed JSON vs compact when signing.
- IPv6 whitelist errors → set `DELTA_FORCE_IPV4=true` (monkeypatches urllib3 address family).
- Multiple uvicorn reload workers can race the singleton; for debugging real data prefer running without `--reload`.
- Don’t broadcast inside templates; always let `_broadcast_all()` handle rendering.

### 7. Adding Features (examples)
- New symbol support: subscribe in `DataService.start()` via `self.ws_client.subscribe_mark(["BTCUSD","ETHUSD"])`, extend templates to iterate marks, adjust forms.
- Additional REST data (e.g., fills): add REST call inside the loop with its own throttle; only include in snapshot + broadcast when changed.
- Strategy engine (future): build separate module (e.g., `strategy/engine.py`) consuming snapshots and placing orders through `rest_client`; keep side‑effects out of template layer.

### 8. Testing & Debugging
- (Planned) Playwright E2E: run with `MOCK_DELTA=true` to assert deterministic layout & live updates. Install once: `python -m playwright install --with-deps`.
- Quick sanity: disable mock, start server, confirm mark price ≠ 60000 region and positions/orders reflect account.
- Enable auth debug: set `DELTA_DEBUG_AUTH=true` to log the exact signature string.

### 9. Safe Editing Practices
- Preserve rate limiting; wrap new high‑frequency REST calls with `@rate_limit`.
- Avoid blocking calls in async loop—keep REST sync but sparse; heavy logic move to thread/task if needed.
- Keep secrets out of commits (.env is user‑local). Never echo actual keys in logs or docs.

### 10. Contact
Sole maintainer: Saqib Sherwani — GitHub @Saqib12333 — sherwanisaqib@gmail.com

---
If anything here seems stale while coding (e.g., Delta alters channel names), search `docs/Delta-API-Docs.md` then update this guide minimally.
