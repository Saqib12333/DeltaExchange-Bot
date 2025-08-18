from __future__ import annotations
import os
import sys
import json
import argparse
from dataclasses import dataclass
from typing import Optional


@dataclass
class Args:
	symbol: str
	size: int
	side: str  # "buy" or "sell"
	price: Optional[float]
	place: bool  # actually place order
	verbose: bool
	retry: bool
	max_retries: int
	retry_wait: float


def parse_args() -> Args:
	p = argparse.ArgumentParser(description="Delta Exchange starter: connectivity + optional seed order")
	p.add_argument("symbol", nargs="?", default=os.getenv("SYMBOL", "BTCUSD"), help="Product symbol (default: BTCUSD)")
	p.add_argument("--size", type=int, default=1, help="Order size in contracts (default: 1)")
	p.add_argument("--side", choices=["buy", "sell"], default="buy", help="Order side (default: buy)")
	p.add_argument("--price", type=float, default=None, help="Limit price; if omitted, uses mark price with a 1-tick shade for post-only")
	# Single base URL config via env or haider_bot/config.yaml
	p.add_argument("--place", action="store_true", help="Actually place the order (default: dry-run)")
	p.add_argument("--verbose", action="store_true", help="Enable debug logging")
	# Resilience options
	p.add_argument("--retry", action="store_true", help="Keep retrying on transient errors (e.g., 5xx) until success")
	p.add_argument("--max-retries", type=int, default=0, help="Max retries when --retry is set (0 = infinite)")
	p.add_argument("--retry-wait", type=float, default=5.0, help="Seconds to wait between retries (backoff is applied)")

	ns = p.parse_args()
	return Args(symbol=ns.symbol, size=ns.size, side=ns.side, price=ns.price, place=ns.place, verbose=ns.verbose, retry=ns.retry, max_retries=ns.max_retries, retry_wait=ns.retry_wait)


def main() -> int:
	# Lazy import dependencies to provide clearer guidance if not installed
	try:
		from dotenv import load_dotenv
		from loguru import logger
	except ImportError:
		print("Missing dependencies. Activate venv and install requirements:", file=sys.stderr)
		print("  ./venv/Scripts/python.exe -m pip install -r requirements.txt", file=sys.stderr)
		return 10

	try:
		# Local imports
		from haider_bot.adapters.delta_adapter import DeltaAdapter, DeltaAPIError
		from haider_bot.adapters.mock_adapter import MockAdapter
		from haider_bot.utils import round_price
	except ImportError:
		logger.error("Project modules not found or dependencies missing. Ensure you run with the venv Python and install requirements.")
		return 11

	load_dotenv()  # load .env if present

	args = parse_args()

	# Configure logging level
	if args.verbose or os.getenv("LOG_LEVEL"):
		lvl = os.getenv("LOG_LEVEL", "DEBUG" if args.verbose else "INFO")
		logger.remove()
		logger.add(sys.stderr, level=lvl)

	api_key = os.getenv("API_KEY") or ""
	api_secret = os.getenv("API_SECRET") or ""

	# Only require keys if we are going to place an order
	if args.place and (not api_key or not api_secret):
		logger.error("API_KEY/API_SECRET not set. For --place, set keys in .env or environment.")
		return 2

	# Use single base URL approach; select mock when mock:// is configured
	base_url = os.getenv("DELTA_BASE_URL")
	if str(base_url).startswith("mock://"):
		adapter = MockAdapter(api_key=api_key, api_secret=api_secret, base_url=base_url, user_agent="haider-starter/1.1")
	else:
		adapter = DeltaAdapter(api_key=api_key, api_secret=api_secret, base_url=base_url, user_agent="haider-starter/1.1")

	# Public endpoints: fetch ticker and mark
	try:
		ticker = adapter.get_ticker(args.symbol)
		mark = adapter.get_mark_price(args.symbol)
		# Keep log concise
		logger.info(f"Ticker: {json.dumps(ticker)[:500]}...")
		logger.info(f"Mark price: {mark}")
	except Exception as e:
		logger.exception(f"Ticker/mark fetch failed: {e}")
		return 3

	# Product metadata
	try:
		product = adapter.get_product_by_symbol(args.symbol)
		logger.info(
			f"Product: id={product.product_id}, symbol={product.symbol}, tick={product.tick_size}, contract_value={product.contract_value}"
		)
	except Exception as e:
		logger.exception(f"Product lookup failed: {e}")
		return 4

	if not args.place:
		logger.info("Dry-run complete: connection OK. Use --place to send a post-only limit order.")
		return 0

	# Compute price: one tick shade to be maker if not provided
	price: float
	if args.price is not None:
		price = float(args.price)
	else:
		if args.side == "buy":
			price = (mark or 0) - product.tick_size
		else:
			price = (mark or 0) + product.tick_size
		price = round_price(price, product.tick_size)

	# Try to place the order, optionally with retry/backoff when upstream is flaky
	import time as _time
	attempt = 0
	backoff = max(1.0, float(args.retry_wait))
	while True:
		try:
			res = adapter.place_limit_order(
				product_id=product.product_id,
				side=args.side,
				size=args.size,
				limit_price=price,
				post_only=True,
			)
			logger.info(f"Order placed: {json.dumps(res)[:800]}...")
			break
		except Exception as e:
			attempt += 1
			if not args.retry:
				logger.exception(f"Order placement failed: {e}")
				return 6
			max_info = f"/{args.max_retries}" if args.max_retries > 0 else ""
			logger.warning(f"Order placement failed (attempt {attempt}{max_info}): {e}\nWill retry after {backoff:.1f}s…")
			if args.max_retries > 0 and attempt >= args.max_retries:
				logger.error("Reached max retries without success.")
				return 6
			_time.sleep(backoff)
			backoff = min(backoff * 1.6, 60.0)

	return 0


if __name__ == "__main__":
	sys.exit(main())

