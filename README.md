# Haider Grid Trading Bot — Delta Exchange (MVP)

Deterministic, limit-only bot that implements the "Haider" pyramid/flip strategy on Delta Exchange. The MVP ships with a 24/7 runner CLI and order-sync logic. Start on Demo (testnet) before Live.

## Quick Start

1) Python & virtualenv

```powershell
py -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt
```

2) Configure environment

- Copy `.env.example` to `.env` and fill in your demo keys:

```
API_KEY=your_demo_key
API_SECRET=your_demo_secret
DELTA_MODE=demo
```

- Ensure your API key has Trading permission and (if required) your machine's IP is whitelisted on Delta.

3) Connectivity smoke test (no orders)

```powershell
./venv/Scripts/python.exe starter.py BTCUSD --mode demo
```

4) Place a tiny seed order on demo (post-only, 1 contract)

```powershell
./venv/Scripts/python.exe starter.py BTCUSD --mode demo --place --side buy --size 1
```

If this succeeds, your keys/network/time are set up correctly.

5) Run the bot (MVP runtime)

```powershell
./venv/Scripts/python.exe -m haider_bot.main status --config haider_bot/config.yaml
# then start the loop (Ctrl+C to stop)
./venv/Scripts/python.exe -m haider_bot.main run --config haider_bot/config.yaml
```

## Project Layout

- `haider_bot/adapters/delta_adapter.py` — Thin REST adapter with HMAC auth.
- `haider_bot/core/strategy.py` — Pure functions for seed/TP/AVG intents.
- `haider_bot/main.py` — CLI and 24/7 runner (status/run/cancel-all).
- `haider_bot/utils.py` — Time, ID generation, rounding.
- `starter.py` — Connectivity/order sanity check script for demo.
- `.github/instructions/AGENT.instructions.md` — Engineering guide for devs and AI agents.

Upcoming modules (planned):

- `oms.py`, `state_machine.py`, `persistence.py`, `main.py` CLI, and tests.

## Configuration

Primary runtime config lives in `haider_bot/config.yaml` and environment variables in `.env`.

- Mode: `exchange.mode` (or `DELTA_MODE`) controls base URLs.
- Symbol: `exchange.symbol` (default BTCUSD for demo).
- Polling and execution: `exchange.poll_interval_ms`, `exchange.use_post_only`, `exchange.price_shade_ticks`.
- Leverage: `sizing.leverage` is set via API at startup.

## Safety Notes

- No stop-loss by design. Strategy can accumulate large unrealized drawdowns.
- Use Demo (testnet) until you fully validate behavior and risk.
- Never commit secrets. `.env` and variants are ignored via `.gitignore`.

## Troubleshooting

- 404 on product endpoint: ensure adapter uses `GET /v2/products/{symbol}` and you used a valid symbol (e.g., `BTCUSD`).
- SignatureExpired: keep system time in sync; Delta requires timestamp within ~5 seconds.
- UnauthorizedApiAccess: check API key permissions (Read/Trading) and IP whitelist.
- Rate limited (429): back off and retry; reduce request frequency.

## License

For internal/demo use. No warranty. Use at your own risk.
