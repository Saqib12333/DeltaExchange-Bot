## Delta Exchange Bot – AI Agent Guide (v4.3)
Goal: Give just enough project‑specific context for safe, rapid changes (avoid re‑deriving architecture or breaking live data flow).

### Architecture & Data Flow
- FastAPI + HTMX + WebSockets (see `server/main.py`). Jinja renders partials (`server/templates/_*.html`) which are pushed over dedicated WS topics: `/ws/mark`, `/ws/positions`, `/ws/orders`, `/ws/balances`.
- Snapshot model: WS + periodic REST hydrate into an in‑memory snapshot; only broadcast when a shallow dict diff changes (reduces chatter).
- Balances have no private WS → REST every ~30s. Orders / positions primarily WS; single REST hydrate on startup gap.
- Separation: `src/ws_client.py` (auth, heartbeat, resilient reconnect) vs `src/delta_client.py` (signed REST + fallback logic + rate limiting).

### Environment / Modes
- `.env` keys: `DELTA_API_KEY`, `DELTA_API_SECRET`, `USE_TESTNET`, `DELTA_BASE_URL`, `DELTA_FORCE_IPV4`, `DELTA_DEBUG_AUTH`, `MOCK_DELTA`.
- Mock mode (no keys or `MOCK_DELTA=true`): deterministic mark (~60000), one long position, one open order. Turn OFF before validating real numbers.
- Testnet toggled by `USE_TESTNET`; do not hardcode alternate URLs unless API CDN changes.

### Auth & Signing (Critical)
- Signature string EXACT: `method + timestamp + path + ('?' + query if query) + body` (body = compact JSON; never pretty print before signing).
- Public GETs must omit auth headers; private endpoints must include signature & timestamp.
- WS auth: send `type=auth` with HMAC of `GET + timestamp + /live` prior to private channel subs.

### Update Loop Semantics
- `DataService._real_loop`: ~1s ticks, collects WS state; REST fallback if initial WS data absent; balances each 30s. Increments version only when something changed.
- PnL: `(mark - entry) * size` where size sign implies direction.
- Never place heavy logic inside template filters—keep business logic Python‑side.

### Key File Roles
- `server/main.py`: app startup, WS topic endpoints, snapshot broadcast helper, order place/cancel endpoints, mock vs real loop selection.
- `server/templates/_*.html`: STRICTLY presentation (formatting, light arithmetic only). Prefix underscore = partial; imported via render for WS pushes.
- `src/delta_client.py`: `place_order`, `cancel_order`, `get_*` with rate limiting. Cancel now canonical via batch endpoint (`DELETE /v2/orders/batch` with `orders:[{id}]` plus product symbol/id). Path delete retained only as guarded fallback (often 404 in this deployment).
- `src/ws_client.py`: Single reusable connection (avoid additional instances). Provides thread‑safe copies of mark / positions / orders via lock.

### HTMX & WS Patterns
- Each live panel div typically identifies itself by `id` (e.g. `orders`) and receives updates via the corresponding WS channel server pushes (not via polling HTMX).
- For user actions (e.g., cancel): use an `hx-post` button with `hx-vals` for payload, `hx-target="#orders"`, and prefer `hx-swap="innerHTML"` to keep the container (prevents WS reconnection churn). A lightweight toast notifies on successful cancellation.
- Detect HX requests server‑side with `if request.headers.get('hx-request') == 'true'` to return partial HTML instead of redirect.

### Common Pitfalls
- Wrong prices/PnL: mock mode still on.
- Signature mismatch: missing leading `?` before query segment in string OR non‑compact JSON.
- Duplicate WS connections: creating extra `DeltaWSClient` instances instead of reusing the singleton.
- Full page reloads after actions: returning RedirectResponse to an HTMX request instead of partial.
- Unbounded broadcasts: modifying templates to emit messages—never do; only `_broadcast_all()` / explicit endpoint sends.

### Adding / Extending Features
- New symbol: subscribe in `DataService.start()` then extend mark template to iterate multiple marks (structure maps of symbol→price; keep formatting simple; broadcast diff aware).
- New data channel: add WS route + snapshot field + partial template; trigger broadcast only on diff. Follow existing naming `/<topic>` & `_topic.html`.
- Additional REST (e.g., fills/history): throttle with existing rate limiting decorator; cache last result to skip unchanged broadcasts.

### Debug & Dev Workflows
- Run (venv): `& venv/Scripts/python.exe -m uvicorn server.main:app` (avoid `--reload` in production due to singleton race risk).
- Enable signature debug: set `DELTA_DEBUG_AUTH=true` to log raw signature strings.
- Deterministic mock test: set `MOCK_DELTA=true`, verify layout + live WS panel updates.
- Inspect WS churn: watch server logs for repeated accepted connections after each UI action → usually incorrect `hx-swap` wiping container.

### Safe Editing Guidelines
- Do NOT move business logic into templates; keep them idempotent and cheap to re‑render.
- Preserve lock usage around snapshot mutations (avoid races with broadcast loop).
- Maintain rate limiting wrapper on new high‑frequency REST calls.
- Avoid broad structural rewrites of `_real_loop`; extend via clearly bounded blocks.

### Contact / Maintenance
Sole maintainer: Saqib Sherwani (@Saqib12333). If Delta API surface changes, update only minimal impacted sections + this guide version.

---
If a pattern here conflicts with current code (API evolution), search `docs/Delta-API-Docs.md`, adjust the specific section, bump version comment.
