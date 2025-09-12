# AGENTS.md

Agent-focused guide for the Delta Exchange Bot (FastAPI + HTMX + WebSockets trading dashboard + planned strategy engine). Keep changes minimal, safe, and aligned with snapshot & diff-based broadcast design.

## Project Overview
- Purpose: Real‑time Delta Exchange portfolio + order management dashboard (Phase 1) with future automated strategy engine (Phase 2+).
- Core Pattern: Server renders Jinja partials -> pushes over dedicated WebSocket topics -> HTMX (ws extension) swaps section DOM without full page reload.
- State Model: Single in‑memory snapshot (marks, balances, positions, orders, version). Broadcast only on shallow dict diff to reduce network noise.

## Key Components
| Area | File(s) | Notes |
|------|---------|-------|
| App entry | `server/main.py` | FastAPI app, startup hook, DataService loop, WS routes, order endpoints |
| REST client | `src/delta_client.py` | Auth signing, rate limiting decorator, fallback logic, mark price via candles / product ref |
| WebSocket client | `src/ws_client.py` | Resilient singleton (auth, heartbeat, subs). Reuse—do not duplicate connections |
| Templates | `server/templates/_*.html` | Presentation only; keep logic thin (formatting, simple arithmetic) |
| Static assets | `server/static/` | `styles.css`, `app.js` (minimal JS) |
| Legacy | `app.py` | Streamlit version (do not extend unless porting patterns) |
| Docs | `docs/Delta-API-Docs.md` | Reference for endpoint shapes (update if API changes) |

## Environment & Modes
- `.env`: `DELTA_API_KEY`, `DELTA_API_SECRET`, `USE_TESTNET`, `DELTA_BASE_URL`, `DELTA_FORCE_IPV4`, `DELTA_DEBUG_AUTH`, `MOCK_DELTA`.
- Mock: missing keys or `MOCK_DELTA=true` → deterministic mark (~60000), 1 position, 1 order.
- Testnet switching via `USE_TESTNET` (avoid hardcoded alt URLs unless upstream changes CDN).

## Auth & Signing
- Signature string EXACT: `method + timestamp + path + ('?' + query if query) + body` (body = compact JSON; no pretty spaces or reordered keys before signing).
- Public GETs (products, candles) must omit auth headers.
- WS auth: send message with HMAC of `GET + timestamp + /live` before private subs.

## Data Update Loop
- Interval ~1s: gather mark/positions/orders from WS snapshot; hydrate once via REST if initial WS gap.
- Balances: REST every ~30s (no private WS channel).
- Broadcast only when any section changed (simple dict comparison). Increment `version` only on diff.
- PnL formula: `(mark - entry) * size`. Size sign implies direction if explicit side absent.

## HTMX + WS Patterns
- Each section panel has stable `id` (e.g. `orders`) and a matching WS endpoint (`/ws/orders`).
- For user actions (place/cancel): HTMX POST returning updated partial. Use `hx-swap="innerHTML"` to preserve container and WS bindings.
- Detect HTMX via `request.headers.get('hx-request') == 'true'`; return partial instead of redirect.

## Order Cancel Workflow (Current)
1. HTMX (or fetch fallback) posts `{order_id}` to `/orders/cancel`.
2. Endpoint: optimistic removal from snapshot then calls REST client `cancel_order`.
3. REST client uses canonical batch endpoint: `DELETE /v2/orders/batch` with payload `{orders:[{id}], product_symbol}` (or `product_id`).
4. If batch fails (rare) a single path fallback `DELETE /v2/orders/{id}` is attempted (observed to 404 on this deployment but retained for forward compatibility).
5. Orders list re-fetched; broadcast updates others; initiating client swaps partial and now shows a toast “Order cancelled”.

Note: Direct `DELETE /v2/orders/{id}` returned 404 despite valid IDs in this environment; batch endpoint is therefore treated as authoritative here. Update docs if upstream behavior changes.

## Safe Change Guidelines
- Do NOT move domain logic into templates; keep them render‑idempotent and cheap.
- Preserve locking (`async with service._lock`) around snapshot mutation.
- Keep rate limiting decorator on new REST high-frequency calls; clone existing pattern.
- Avoid spawning additional WS clients—extend subscriptions on singleton.
- Don’t introduce blocking I/O in `_real_loop`; if heavy, schedule thread/task.

## Extending Functionality
- New symbol: add subscribe call in `DataService.start()`, store price in snapshot (map symbol→price), expand `_mark.html` to iterate; maintain diff broadcast.
- New data stream: add snapshot field + template + WS route; broadcast only when changed.
- Strategy module: build separate `strategy/` package consuming snapshot (read‑only) and issuing orders via `rest_client`; keep side effects out of rendering/broadcast path.

## Run / Dev Commands
```powershell
# Create & activate venv (Windows PowerShell)
python -m venv venv
& venv/Scripts/Activate.ps1
pip install -r requirements.txt

# Start server (avoid --reload for production singleton stability)
& venv/Scripts/python.exe -m uvicorn server.main:app --port 8000

# (Optional) Legacy Streamlit
streamlit run app.py
```

## Debugging Tips
- Set `DELTA_DEBUG_AUTH=true` → logs raw signature string (`signature_data`).
- Unexpected mark=60000 → mock mode still active.
- Repeated WS connection logs after each action → wrong `hx-swap` replaced container; use `innerHTML`.
- Signature failures: verify leading `?` on query in signed string & compact JSON body.
- IPv6 whitelist issues → set `DELTA_FORCE_IPV4=true`.

## Testing (Lightweight)
- Manual smoke: mock mode, confirm all four panels populate & live updates occur.
- (Future) Playwright E2E: run in mock mode to assert deterministic HTML for sections.

## Security / Safety
- Never log real secrets or embed keys in code.
- Keep cancellation and order placement logic idempotent (safe retry: duplicate cancel attempts swallowed).
- Validate numeric inputs server‑side before passing to REST client.

## When Updating This File
- Increment version in `.github/copilot-instructions.md` if architecture meaningfully changes.
- Remove temporary debug (e.g., header dumps) after resolving issues.
- Keep <50 lines per section; add new sections only when patterns become stable.

## Contact
Maintainer: Saqib Sherwani (@Saqib12333) — sherwanisaqib@gmail.com

---
Agents: adhere strictly to snapshot diff pattern & auth rules. Ask (or emit a warning) before structural rewrites of loop, auth signing, or WS client lifecycle.
