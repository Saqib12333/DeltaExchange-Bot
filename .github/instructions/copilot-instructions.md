applyTo: '*/**'
---
applyTo: '*/**'
---

# Copilot Instructions: Haider Grid Trading Bot — Delta Exchange (Demo)

- Project: Haider Grid Trading Bot — Delta Exchange (demo)
- Audience: AI coding agent or human developer
- Goal: Implement a deterministic, limit-only trading bot that executes the “Haider” pyramid/flip strategy on Delta Exchange demo account (BTCUSD). This document captures everything required to design, implement, test, and operate the bot locally in Python.

## 1. Executive Summary (TL;DR)

Build a single-user Python bot that:

- Trades BTCUSD on Delta Exchange demo environment.
- Uses limit orders only (maker-first). If post_only is unavailable, use 1-tick price-shading to bias maker fills.
- Maintains one net open position at a time (side ∈ {LONG, SHORT}) with sizes only in the set {1, 3, 9, 27} lots. (1 lot = 0.001 BTC)
- Always operates with two concurrent live orders max: one TP (opposite direction) and one Average Add (same direction). When one executes, cancel the other immediately.
- Leverage = 10x.
- Strategy behavior: Seed → Average Add (x2 current open lots at avg ± 750) → Take-Profit Flip (size = open_lots + 1 at avg ± 500) → repeat. Max pyramid depth: 27 lots.
- Operate locally (Python), demo-only.

## 2. Key Design Principles

- Deterministic state machine: Strategy expressed as a state machine so both humans and AIs can reason and test easily.
- Separation of concerns: Strategy, Market Data, Risk, OMS/Execution, Exchange Adapter, Persistence, and Monitoring are cleanly separated.
- Idempotency & auditability: Client-generated order IDs and append-only event audit log.
- Maker-first: Post-only if supported; otherwise price-shade by one tick. Never market-take intentionally.
- Fail-safe: Hard caps on lots and an emergency `flatten_and_disarm` operation.
- Live-first (demo): Backtest is optional; integration tests against demo/testnet required.

## 3. Required Tech Stack & Dependencies

- Language: Python 3.10+
- Primary SDK: `delta-rest-client` (pip) — or use direct REST via `requests` as a thin, testable adapter.
- Must-have libraries:
  - `python-dotenv` (env)
  - `pydantic` (config validation)
  - `requests` (if needed) / `httpx`
  - `sqlalchemy` or builtin `sqlite3` (persistence)
  - `tenacity` or custom retry/backoff (recommended)
  - `pytest` (tests)
  - `loguru` or `structlog` (structured logging)
- Dev tooling: `black`, `ruff`, `mypy` (optional but recommended)

Example install:

```bash
pip install delta-rest-client python-dotenv pydantic tenacity sqlalchemy pytest loguru
```

Base URLs (REST/WebSocket):

- Production REST: https://api.india.delta.exchange
- Testnet (Demo) REST: https://cdn-ind.testnet.deltaex.org
- Production WS: wss://socket.india.delta.exchange
- Testnet (Demo) WS: wss://socket-ind.testnet.deltaex.org

## 4. Environment & Configuration

`.env` (already present; ensure values):

```ini
API_KEY=xxx
API_SECRET=yyy
DELTA_MODE=demo   # demo|live
```

Notes:

- Trading keys may require IP whitelisting on Delta. Ensure your machine's IPs (IPv4/IPv6) are whitelisted for keys with Trading permission.
- Keep system time in sync. Authenticated REST requests require the timestamp to be within ~5 seconds (SignatureExpired otherwise).

`config.yaml` (canonical - add to repo):

```yaml
exchange:
  mode: demo                 # demo|live
  symbol: BTCUSD             # contract to trade
  poll_interval_ms: 750      # market data cadence
  use_post_only: true        # try post-only, else fallback to price-shade
  price_shade_ticks: 1       # ticks to move away from aggressive price

sizing:
  lot_size_btc: 0.001
  leverage: 10

grid:
  seed_offset_usd: 50        # seed at mark +/- 50
  tp_step_usd: 500           # TP = avg +/- 500
  avg_step_usd: 750          # add at avg +/- 750
  avg_multiplier: 2          # add-size = 2 * current_open_lots
  keep_one_on_flip: true     # TP size = open_lots + 1

risk:
  max_total_lots: 27
  max_averages_per_cycle: 3
  min_liq_buffer_pct: 25
  max_margin_utilization_pct: 60
  halt_on_error_burst: true

persistence:
  sqlite_db: ./data/haider_bot.db
logging:
  level: INFO
  file: ./logs/haider_bot.log
```

## 5. Data Model & Persistence

Use SQLite (simple first) with tables (minimum):

- positions: `id`, `side` (LONG/SHORT), `open_lots`, `avg_price`, `last_update_ts`
- orders: `client_id`, `exchange_order_id`, `type` (seed|avg|tp), `side`, `price`, `qty_lots`, `qty_btc`, `status`, `created_ts`, `filled_ts`, `filled_qty`, `raw_response`
- fills: `id`, `order_client_id`, `side`, `qty_btc`, `price`, `ts`
- events (audit log): `id`, `ts`, `level`, `tag`, `payload_json` — append-only for post-mortems
- config_versions (optional)
- metrics (optional)

Client Order ID format (idempotency & traceability):

```
HAIDER-{ENV}-{TS_ISO}-{TYPE}-{SIDE}-{SEQ}
e.g. HAIDER-DEMO-20250815T091223Z-SEED-LONG-01
```

## 6. Exchange Adapter (Responsibilities)

 Provide a thin, testable wrapper around `delta-rest-client` (or direct REST using `requests`):

- `get_instrument_info(symbol)` → tick_size, step_size, min_qty, lot_size, contract_value
- `get_mark_price(symbol)` → mark price deterministic for strategy
- `get_positions()` → positions and margin
- `get_open_orders()` → open orders
- `place_limit_order(client_id, side, price, qty_lots, post_only=True)` → order object
- `cancel_order(client_id or exchange_order_id)`
- `get_order_status(client_id or exchange_order_id)`

Error translation into: `TransientError`, `RateLimited`, `PermanentError`, `OrderRejected`.

Adapter must:

- Detect post_only support; fallback to price-shade logic.
- Enforce rounding to tick/qty step using instrument metadata.
- Interpret 429 Retry-After and surface to OMS for backoff.
- Include `User-Agent` header on authenticated HTTP requests (required by Delta docs).
- Use correct endpoints:
  - Get product by symbol: `GET /v2/products/{symbol}`
  - Get ticker for product: `GET /v2/tickers/{symbol}`

## 7. Core Modules & File Layout (suggested)

```
/haider_bot
  /adapters
    delta_adapter.py
  /core
    strategy.py            # pure logic, stateless functions
    state_machine.py       # orchestrates states
    risk.py                # pre-trade checks
    oms.py                 # order lifecycle, idempotency
    persistence.py         # sqlite models & helpers
    utils.py               # rounding, id generation, time helpers
  /tests
    test_strategy.py
    test_state_machine.py
  main.py                  # CLI entry: arm/disarm/flatten/run
  config.yaml
  .env
  README.md
```

## 8. Strategy Logic (deterministic pseudocode)

Constants:

- `LOT_BTC = 0.001`
- `SEED_OFFSET = 50 USD`
- `AVG_STEP = 750 USD`
- `TP_STEP = 500 USD`
- `AVG_MULT = 2`
- `MAX_LOTS = 27`

State fields:

- `position.side ∈ {NONE, LONG, SHORT}`
- `position.open_lots ∈ {0,1,3,9,27}`
- `position.avg_price` (BTCUSD)
- `open_orders` list (max length = 2)

Primary flows:

- Idle → Seed
  - If position is NONE: place a seed limit at mark ± SEED_OFFSET sized 1 lot.
  - After seed placed, update orders and state to SeedPlaced.
  - Arm a TP for the same side? No; TP only when position becomes open (after seed fills).
- On Seed Fill → PositionOpen (1 lot)
  - Set `avg_price = fill_price`, `open_lots = 1`, `side = fill_side`.
  - Place two orders:
    - TP (opposite side) at `avg ± TP_STEP`, `qty = open_lots + 1` (closes current and opens 1 opposite).
    - AVG_ADD (same side) at `avg ∓ AVG_STEP`, `qty_lots = open_lots * AVG_MULT`.
  - Note: Only two live orders maximum; both must be present immediately after seed fills.
- On AVG_ADD Fill
  - Update `open_lots = open_lots + qty_added` (e.g., 1 + 2 → 3).
  - Recompute avg_price weighted by qty.
  - Cancel outstanding TP and re-arm new TP at `new_avg ± TP_STEP` sized `open_lots + 1`.
  - Cancel any other redundant orders (enforce 2-order invariant).
- On TP Fill (flip)
  - Fill closes `open_lots` and opens 1 lot opposite if `TP size = open_lots + 1`.
  - Update position to `side = opposite`, `open_lots = 1`, `avg_price = residual_fill_price` (if partial fills, compute weighted).
  - Cancel outstanding AVG_ADD.
  - Place new AVG_ADD at avg_step from new avg and new TP at `avg ± TP_STEP` (re-arm).

Invariants & housekeeping:

- At any time there must be at most one open position (net).
- At any time there must be at most two live orders (one TP opposite, one AVG same).
- On any order execution event, cancel the other live order immediately.
- Respect MAX_LOTS — refuse any average add that would push `open_lots > 27`.
- If attempted add would breach MAX_LOTS, log and do not place; optionally raise alert and disarm.

Example numeric workflow (Long):

- Seed Long @ Mark − 50 for 1 lot → filled at 10000 → `open_lots = 1`, `avg = 10000`.
- Place TP Short @ `10000 + 500 = 10500`, `qty = open_lots + 1 = 2`.
- Place AVG Long @ `10000 − 750 = 9250`, `qty = 2 × 1 = 2`.
- If AVG fills at 9250: `open_lots = 1 + 2 = 3`, `new_avg = weighted_price = (110000 + 29250)/3 = 9500`.
- Cancel prior TP at 10500; place new TP Short @ `9500 + 500 = 10000`, `qty = open_lots + 1 = 4`.
- Place new AVG Long @ `9500 − 750 = 8750`, `qty = 2 × 3 = 6`.
- Continue until `open_lots = 27` (1→3→9→27) or a TP executes.

## 9. Order Lifecycle & OMS

Order placement rules:

- Always send `post_only=True` if supported. If rejected (or unsupported), place at a price adjusted by `price_shade_ticks` away from mid to reduce taker risk.
- Use client-generated IDs (format above) to avoid duplicates.
- Round price to nearest tick, qty to the allowed step; convert lot counts → `qty_btc = lots × 0.001`.

On partial fills:

- Update state incrementally. If partially filled, do not assume full fill; keep remaining portion tracked.
- If partial fill occurs for either TP or AVG, and the other order remains, cancel the remaining order immediately and follow invariant logic.

On order fill event:

- Persist fill to `fills` table, update positions, recompute `avg_price`, and recalc new orders.

On order rejection:

- If permanent (e.g., insufficient margin): log, alert, disarm.
- If transient (rate limit or network): retry with exponential backoff and jitter. Follow Retry-After if provided.

Rate limiting:

- Implement token-bucket per instrument and a global concurrency cap. Respect 429 + Retry-After.

## 10. Risk Management (enforced rules)

Hard caps:

- `max_total_lots = 27` (block any order that would exceed)
- `max_averages_per_cycle = 3` (configurable)
- No stop-loss per your instruction. Note: the bot will not close at loss; it waits for price to revert.

Margin checks:

- Before sending order, check `get_positions()` + margin to ensure `max_margin_utilization_pct` not exceeded.
- If margin utilization > configured threshold → reject order and alert. Optionally reduce order size.

Emergency controls:

- `flatten_and_disarm()` should immediately cancel open orders and place market-close (or best-effort limit with aggressive price) to exit position if requested. (Although strategy avoids SL, flatten must be available for emergency.)
- `halt_on_error_burst` — after N consecutive transient errors or repeated adapter failures, automatically disarm.

## 11. Observability, Logging & Alerts

- Structured logs for every decision: include `trace_id`, `client_order_id`, `state_snapshot`, `market_snapshot` (price/tick/ts).
- Metrics to export (simple Prometheus or CSV): `orders_placed_total`, `orders_filled_total`, `fill_rate`, `avg_slippage` (vs mark), `open_lots`, `error_rate`.

Alerting:

- Alert on: suspected taker fills, attempted order that breaches MAX_LOTS, margin utilization breach, adapter auth failure, 429 flood.
- Audit CSV: every state transition and fill must append to `audit.csv` for post-mortem.

## 12. Testing & Validation

Unit tests:

- Strategy module: test avg calc, lot transitions 1→3→9→27, order creation logic.
- OMS adapter mocks: assert correct rounding, post-only fallback, client_id uniqueness.

Integration tests (demo):

- Dry-run mode: adapter returns simulated order acks from a stubbed demo; assert state machine transitions and invariants.
- Live demo test: run against Delta demo/testnet with a sandbox account and validate an expected sequence of fills (use small ticks).

Safety tests:

- Test emergency flatten works.
- Test behavior when avg_add would exceed MAX_LOTS.
- Test reaction to 429 and network faults.

Manual checklist before running locally:

- `.env` present with demo API keys.
- `config.yaml` validated and `mode=demo`.
- Database initialized: `python -m haider_bot.persistence init-db`.
- Start in dry-run first: `python main.py --dry-run`.
- Start live-demo: `python main.py --mode demo`.

Quick smoke test (starter):

- Run the connectivity starter to fetch ticker/product and optionally place a tiny post-only seed order on demo:
  - `python starter.py BTCUSD --mode demo` (does not place orders)
  - `python starter.py BTCUSD --mode demo --place --side buy --size 1`

## 13. Operational Commands (CLI)

```bash
python main.py run           # Run the live demo bot loop
python main.py arm           # Arm trading (enable sending orders)
python main.py disarm        # Disarm trading (cancel open orders; do not place new ones)
python main.py flatten       # Cancel orders and attempt to flatten position (emergency)
python main.py status        # Print current position, open orders, margins
python main.py audit-export  # Dump events and fills to CSV for review
python starter.py SYMBOL     # Quick connectivity/order smoke test (demo by default)
```

## 14. Implementation Guidance (developer notes)

- Strategy = pure functions: `compute_next_orders(position, market_snapshot, config) -> [OrderIntent]`.
- State machine orchestrator: applies risk checks, calls OMS to send/cancel orders, persists events, and schedules retries.
- Idempotency: before placing an order, check DB for `client_id` existence. If present with `status=OPEN`, do not re-place.
- Time & scheduling: single-threaded event loop with async IO or a small scheduler. Keep the critical path simple: read market, decide, act, sleep.
- Concurrency model: serialize decision-execution per instrument to enforce rate-limits and invariants.
- Error handling strategy:
  - Transient: retry with exponential backoff + jitter (max attempts configurable).
  - Rate-limited: respect Retry-After.
  - Permanent: log, disarm automatically.
- Precision & rounding: always fetch instrument `tick_size` and `min_qty` on startup; factor contract size conversions into qty calculation.
- Testing hooks: inject a mock adapter for unit tests; make market snapshot pluggable.

## 15. Edge Cases & Clarifications

- Partial fills: treat as fills and update state incrementally; cancel other order.
- TP sizing: TP size is `open_lots + 1`. This closes current exposure and opens a net of 1 opposite lot when filled (ensure arithmetic and handling of partial fills align with this).
- Order re-pricing: if an order is about to be marketable (risk of taker fill) and post_only is not guaranteed, cancel and re-place with 1-tick safer price. Implement retry cap.
- Simultaneous fills: if both orders fill (rare), handle the earliest fill first per persisted timestamp; reconcile resulting net position and run cleanup/cancels immediately.
- No SL: by design, no stop-loss. Highlight the risk in README and runbook: this strategy can produce large unrealized drawdowns.

## 16. Deliverables Checklist

- `config.yaml` schema + validation via Pydantic.
- `delta_adapter.py` with full API surface.
- `strategy.py` (pure functions) + unit tests.
- `state_machine.py` + integration tests (mock adapter).
- `oms.py` with idempotent order placement, post-only fallback, rounding utilities.
- `persistence.py` with DB migrations/init and ORM or direct SQL helpers.
- `main.py` CLI with commands: run/arm/disarm/flatten/status.
- `starter.py` for connectivity + initial order placement sanity on demo.
- Logging + audit CSV exporter.
- Runbook `RUNBOOK.md` (how to start/stop/flatten, contact, known issues).
- `tests/` coverage for invariants: max 2 open orders, single net position, 1→3→9→27 transitions.
- README with quickstart, env setup, config explanation, and safety considerations.

## 17. Runbook (quick)

1) Validate `.env` & `config.yaml`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py --mode demo --dry-run   # sanity
python main.py arm                     # enable trading
```

Monitor logs and `python main.py status` frequently.

If something looks wrong:

```bash
python main.py flatten
python main.py disarm
```

## 18. README Safety Warning (prominent)

WARNING: This bot does not implement stop-losses by design. It can accumulate large unrealized exposure. Run only on demo/test accounts until you fully understand the P&L behavior. The author and maintainers accept no responsibility for financial losses.

Operational hygiene: Never commit secrets. `.env` and variants are ignored via `.gitignore`. Use demo keys first and verify with `starter.py` before arming the full bot.

## 19. Acceptance Criteria (definition of done)

- Bot runs locally, connects to Delta demo with keys in `.env`, and successfully places seed limit order.
- After a simulated or real seed fill, the bot creates the two expected live orders (TP and AVG) and enforces the 2-order invariant.
- On AVG fills and TP fills, state transitions match the rules and DB contains accurate audit trail.
- Max lots are enforced and the bot refuses to exceed 27 lots.
- Emergency flatten and disarm work as intended.
- Unit tests and integration tests pass.

## 20. Appendix: Example Order Generation (concrete)

Assume mark = 10000 USD, long flow:

- Seed: Long @ 9950, `qty = 1` lot → AUTOGENERATE `client_id = HAIDER-DEMO-<TS>-SEED-LONG-01`.
- On seed fill (`avg=9950`, `open_lots=1`):
  - TP Short @ `9950 + 500 = 10450`, `qty_lots = 2`.
  - AVG Long @ `9950 − 750 = 9200`, `qty_lots = 2`.
- After AVG filled at 9200 (`open_lots = 3`, `avg ≈ (19950 + 29200)/3 = 9450`):
  - Cancel old TP (10450).
  - New TP Short @ `9450 + 500 = 9950`, `qty = 4`.
  - New AVG Long @ `9450 − 750 = 8700`, `qty = 6`.

## 21. Final Notes to Developer / AI Agent

- Be explicit in code comments about why the TP/AVG sizing is `open_lots + 1` and `2 × open_lots` respectively.
- Keep the strategy implementation pure so it is trivially testable.
- Use `client_order_id` & DB as the single source of truth for whether an intent has been placed.
- Favor clarity over micro-optimizations on first pass. Once stable in demo, iterate on heuristics: maker success rate, price_shade tuning, and retry/backoff tuning.
- Document every non-trivial decision in `RUNBOOK.md` for future maintainers.

## 22. Git Hygiene & Sensitive Files

- `.env`, `.env.*`, logs/, data/ (db, csv), IDE folders, and local overrides must be excluded via `.gitignore`.
- Exclude the `Stratergy/` folder from VCS if it contains sensitive proprietary docs.

## 23. API Specifics & Pitfalls

- Auth headers require: `api-key`, `signature`, `timestamp`, and `User-Agent`.
- Ensure the method + timestamp + path + query + body are used for HMAC SHA256 signing per docs.
- Time sync matters: if you see `SignatureExpired`, sync your clock and retry.
- Use `GET /v2/products/{symbol}` for product metadata; avoid outdated paths.
- Respect rate limits; treat HTTP 429 as transient and honor Retry-After when present.

## 24. Starter Script (Connectivity & Seed Order)

- Purpose: verify `.env`, base URLs, and adapter before running the full bot.
- Usage examples:
  - `python starter.py BTCUSD --mode demo` → Fetch ticker + product only.
  - `python starter.py BTCUSD --mode demo --place --side buy --size 1` → Place a 1-contract post-only order shaded by 1 tick from mark.
- The script rounds price to tick size and shades one tick towards maker side when `--price` is omitted.

## 25. Demo vs Live Considerations

- Start with `DELTA_MODE=demo` and separate demo keys.
- For live, rotate keys, ensure IP whitelist, and lower rate limits and order frequency until behavior is proven.