---
applyTo: '**/*'
---
# Engineering & Agent Guide (Haider Bot MVP)

This guide steers both human devs and AI coding agents while making changes to the Haider Delta Exchange bot. Follow it to keep the code safe, consistent, and deployable.

## Core principles

- Safety first: default to Demo (testnet) and only switch to Live when explicitly requested.
- Idempotent & deterministic: same inputs → same intents; use client_order_id to avoid duplicate orders.
- Maker-first: post-only orders with configurable tick shading to avoid taker fills.
- Small changes: focused commits with clear messages and tests for behavior changes.
- Always use the project venv for commands (`venv\\Scripts\\activate`).

## Repo layout (runtime files)

- `haider_bot/adapters/delta_adapter.py` — REST adapter with signing and essential endpoints.
- `haider_bot/core/strategy.py` — Pure strategy functions: compute intents from position + mark.
- `haider_bot/main.py` — CLI and 24/7 runner loop that places/cancels orders per intents.
- `haider_bot/config.yaml` — Bot configuration (mode, symbol, polling, shading, grid/risk, logging).
- `haider_bot/utils.py` — Helpers: rounding, client_order_id, timestamps.
- `starter.py` — Connectivity smoke test (not used for MVP runtime).

## Configuration

Environment (`.env`):
- `API_KEY`, `API_SECRET` — required for trading.
- `DELTA_MODE` — `demo` (default) or `live`.
- Optional: `LOG_LEVEL` — console verbosity.

Config file (`haider_bot/config.yaml`):
- exchange:
	- `mode`, `symbol`, `poll_interval_ms`, `use_post_only`, `price_shade_ticks`.
- sizing:
	- `leverage` (set at startup).
- grid:
	- `seed_offset_usd`, `tp_step_usd`, `avg_step_usd`, `avg_multiplier`.
- risk:
	- `max_total_lots` cap to avoid over-averaging.
- logging:
	- `level`, `file` (optional rotating file log).

## Strategy rules (MVP)

- Flat (NONE): place SEED buy at `mark - seed_offset_usd`.
- LONG: TP sell at `avg + tp_step` size `open_lots + 1`; AVG buy at `avg - avg_step` size `open_lots * avg_multiplier` if total ≤ `max_total_lots`.
- SHORT: symmetric (TP buy; AVG sell).

Notes:
- Intents are pure; placement policies (post-only, shading, rounding) are applied in the runner.

## Order management

- Place intents as post-only limit orders with tick rounding and `price_shade_ticks` toward maker side.
- Use `gen_client_order_id` to set `client_order_id` like `HAIDER-{ENV}-{TS}-{TYPE}-{SIDE}-{SEQ}`.
- Each loop cycle: compute intents, place them, fetch open orders, cancel stale HAIDER orders not matching current targets. Leave non-bot orders.

## CLI usage (PowerShell)

- Status (safe):
	`./venv/Scripts/python.exe -m haider_bot.main status --config haider_bot/config.yaml`
- Run the bot (24/7):
	`./venv/Scripts/python.exe -m haider_bot.main run --config haider_bot/config.yaml`
- Cancel all bot orders:
	`./venv/Scripts/python.exe -m haider_bot.main cancel-all --config haider_bot/config.yaml`

## Operational notes

- REST base URLs: Live `https://api.india.delta.exchange`, Demo `https://cdn-ind.testnet.deltaex.org`.
- Keep system time accurate; include `User-Agent` header; ensure API key has trading permission and IP whitelist if required.

## Testing & quality gates

- Add unit tests for strategy outputs, rounding, and order-sync cancellation (using a mock adapter).
- Smoke tests:
	- `status` shows mark and parsed position.
	- `run` places/cancels as per current intents and maintains only target orders.

## Do/Don’t

- Do: Use venv terminal; keep secrets out of git; keep changes focused.
- Don’t: Create a new runtime script for MVP. Use `haider_bot.main` CLI; keep `starter.py` only for connectivity checks.


