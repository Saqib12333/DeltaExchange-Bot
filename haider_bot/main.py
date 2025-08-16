from __future__ import annotations
import os
import sys
import time
import signal
import json
from dataclasses import dataclass
from typing import Optional, List, Tuple
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from .adapters.delta_adapter import DeltaAdapter, DeltaAPIError
from .utils import round_price, gen_client_order_id
from .core.strategy import Position, OrderIntent, Config as StratCfg, compute_next_orders


@dataclass
class BotConfig:
    symbol: str
    mode: str
    poll_interval_sec: float
    leverage: Optional[int]
    use_post_only: bool
    shade_ticks: int
    log_level: str
    log_file: Optional[str]
    strategy: StratCfg


def load_config(path: str) -> BotConfig:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    ex = data.get("exchange", {})
    grid = data.get("grid", {})
    risk = data.get("risk", {})
    logging = data.get("logging", {})
    # Map to our StrategyConfig expectations
    strat = StratCfg(
        seed_offset_usd=float(grid.get("seed_offset_usd", 5.0)),
        tp_step_usd=float(grid.get("tp_step_usd", 20.0)),
        avg_step_usd=float(grid.get("avg_step_usd", 20.0)),
        avg_multiplier=int(grid.get("avg_multiplier", 1)),
        max_total_lots=int(risk.get("max_total_lots", 10)),
    )
    symbol = str(ex.get("symbol", os.getenv("SYMBOL", "BTCUSD")))
    mode = str(ex.get("mode", os.getenv("DELTA_MODE", "demo")))
    poll_ms = float(ex.get("poll_interval_ms", 1000))
    leverage = data.get("sizing", {}).get("leverage")
    use_post_only = bool(ex.get("use_post_only", True))
    shade_ticks = int(ex.get("price_shade_ticks", 1))
    log_level = str(logging.get("level", os.getenv("LOG_LEVEL", "INFO")))
    log_file = logging.get("file")
    return BotConfig(
        symbol=symbol,
        mode=mode,
        poll_interval_sec=max(0.2, poll_ms / 1000.0),
        leverage=leverage,
        use_post_only=use_post_only,
        shade_ticks=shade_ticks,
        log_level=log_level,
        log_file=log_file,
        strategy=strat,
    )


def parse_position(adapter: DeltaAdapter, product_id: int) -> Position:
    try:
        pos_data = adapter.get_positions(product_id=product_id)
    except Exception:
        return Position()
    # Delta may return a list in result OR a dict containing a list
    result = pos_data.get("result")
    items = []
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        # Common patterns
        if isinstance(result.get("positions"), list):
            items = result.get("positions") or []
        elif str(product_id) in result and isinstance(result.get(str(product_id)), dict):
            items = [result.get(str(product_id))]
        elif isinstance(result.get("position"), dict):
            items = [result.get("position")]
    if not items:
        return Position()
    p = items[0] if items else None
    if not isinstance(p, dict):
        return Position()
    side_raw = p.get("side") or "none"
    side = "NONE"
    if side_raw.lower() == "buy":
        side = "LONG"
    elif side_raw.lower() == "sell":
        side = "SHORT"
    open_lots = int(float(p.get("size", 0)))
    avg_price = float(p.get("entry_price") or p.get("avg_entry_price") or 0) or None
    return Position(side=side, open_lots=open_lots, avg_price=avg_price)


def ensure_leverage(adapter: DeltaAdapter, product_id: int, leverage: Optional[int]) -> None:
    if not leverage:
        return
    try:
        adapter.set_order_leverage(product_id, int(leverage))
    except Exception as e:
        logger.warning(f"Failed to set leverage: {e}")

def _shade_price(base_px: float, side: str, tick: float, shade_ticks: int) -> float:
    if shade_ticks <= 0:
        return round_price(base_px, tick)
    adj = tick * shade_ticks
    px = base_px - adj if side == "buy" else base_px + adj
    return round_price(px, tick)


def sync_intents(
    adapter: DeltaAdapter,
    env: str,
    product_id: int,
    tick: float,
    intents: List[OrderIntent],
    use_post_only: bool,
    shade_ticks: int,
) -> None:
    # Fetch current open orders for this product
    try:
        open_data = adapter.get_open_orders(product_ids=str(product_id))
        open_items = open_data.get("result") or []
    except Exception as e:
        logger.warning(f"Could not fetch open orders: {e}")
        open_items = []

    # Build target set and place missing
    target_sigs: List[Tuple[str, float, str]] = []  # (side, price, typ)
    seq = 1
    for it in intents:
        px = _shade_price(it.price, it.side, tick, shade_ticks)
        target_sigs.append((it.side, px, it.typ))
        try:
            coid = gen_client_order_id(env=env, typ=it.typ, side=it.side, seq=seq)
            seq += 1
            res = adapter.place_limit_order(
                product_id=product_id,
                side=it.side,
                size=it.qty_lots,
                limit_price=px,
                post_only=use_post_only,
                client_order_id=coid,
            )
            logger.info(f"Placed {it.typ} {it.side} {it.qty_lots}@{px}: {json.dumps(res)[:400]}...")
        except DeltaAPIError as e:
            logger.warning(f"Placement failed for {it.typ} {it.side}@{px}: {e}")

    # Cancel stale HAIDER orders that do not match current targets
    target_set = {(s, p) for (s, p, _t) in target_sigs}
    for od in open_items:
        coid = str(od.get("client_order_id") or "")
        if not coid.startswith("HAIDER-"):
            continue  # leave non-bot orders alone
        side = str(od.get("side", "")).lower()
        try:
            price = float(od.get("limit_price") or od.get("price") or 0)
        except Exception:
            price = 0.0
        price = round_price(price, tick)
        if (side, price) not in target_set:
            try:
                adapter.cancel_order(client_order_id=coid, product_id=product_id)
                logger.info(f"Canceled stale order {coid} {side}@{price}")
            except Exception as e:
                logger.warning(f"Failed to cancel stale order {coid}: {e}")


_stop = False


def _handle_sig(signum, frame):
    global _stop
    _stop = True


def run_bot(config_path: str = "haider_bot/config.yaml") -> int:
    load_dotenv()
    from loguru import logger as _logger

    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    if not api_key or not api_secret:
        _logger.error("API_KEY/API_SECRET not set. Aborting run.")
        return 2

    cfg = load_config(config_path)

    # Configure logging to file if specified
    try:
        logger.remove()
        logger.add(sys.stderr, level=cfg.log_level)
        if cfg.log_file:
            log_path = Path(cfg.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            logger.add(str(log_path), level=cfg.log_level, rotation="10 MB", retention="14 days", enqueue=True)
    except Exception:
        pass

    adapter = DeltaAdapter(api_key=api_key, api_secret=api_secret, mode=cfg.mode, user_agent="haider-bot/0.1")

    # Resolve product & setup (retry-friendly)
    product = None
    boot_attempts = 0
    while not _stop and product is None and boot_attempts < 5:
        try:
            product = adapter.get_product_by_symbol(cfg.symbol)
        except Exception as e:
            boot_attempts += 1
            logger.warning(f"Product lookup failed (attempt {boot_attempts}/5): {e}")
            time.sleep(1.5 * boot_attempts)
    if product is None:
        logger.error("Unable to resolve product after retries. The bot will keep retrying in-loop.")
    else:
        ensure_leverage(adapter, product.product_id, cfg.leverage)

    # Install signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_sig)
        except Exception:
            pass

    if product is not None:
        logger.info(f"Starting bot on {cfg.mode.upper()} for {cfg.symbol} (product {product.product_id})")
    else:
        logger.info(f"Starting bot on {cfg.mode.upper()} for {cfg.symbol}; waiting for product metadata to become available…")
    while not _stop:
        try:
            # Resolve product lazily if not yet available
            if product is None:
                try:
                    product = adapter.get_product_by_symbol(cfg.symbol)
                    ensure_leverage(adapter, product.product_id, cfg.leverage)
                    logger.info(f"Product ready: id={product.product_id}, tick={product.tick_size}")
                except Exception as e:
                    logger.warning(f"Product still unavailable: {e}")
                    time.sleep(cfg.poll_interval_sec)
                    continue

            mark = adapter.get_mark_price(cfg.symbol)
            pos = parse_position(adapter, product.product_id)
            intents = compute_next_orders(pos, mark, cfg.strategy)
            if intents:
                sync_intents(
                    adapter=adapter,
                    env=cfg.mode,
                    product_id=product.product_id,
                    tick=product.tick_size,
                    intents=intents,
                    use_post_only=cfg.use_post_only,
                    shade_ticks=cfg.shade_ticks,
                )
            else:
                logger.debug("No intents this cycle")
        except DeltaAPIError as e:
            logger.warning(f"Cycle error: {e}")
        except Exception as e:
            logger.exception(f"Unexpected loop error: {e}")
        time.sleep(cfg.poll_interval_sec)

    logger.info("Bot stopped.")
    return 0


def cli():
    import argparse
    p = argparse.ArgumentParser(prog="haider-bot", description="Haider Strategy Bot")
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run the bot 24/7")
    run_p.add_argument("--config", default="haider_bot/config.yaml")

    ca_p = sub.add_parser("cancel-all", help="Cancel all open orders for the configured symbol")
    ca_p.add_argument("--config", default="haider_bot/config.yaml")

    st_p = sub.add_parser("status", help="Show basic status")
    st_p.add_argument("--config", default="haider_bot/config.yaml")

    ns = p.parse_args()

    load_dotenv()
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    if not api_key or not api_secret:
        logger.error("API_KEY/API_SECRET not set.")
        return 2

    cfg = load_config(getattr(ns, "config"))
    adapter = DeltaAdapter(api_key=api_key, api_secret=api_secret, mode=cfg.mode, user_agent="haider-bot/0.1")
    product = adapter.get_product_by_symbol(cfg.symbol)

    if ns.cmd == "run":
        return run_bot(getattr(ns, "config"))
    elif ns.cmd == "cancel-all":
        res = adapter.cancel_all(product.product_id)
        logger.info(f"Cancel-all: {json.dumps(res)[:400]}...")
        return 0
    elif ns.cmd == "status":
        mark = adapter.get_mark_price(cfg.symbol)
        pos = parse_position(adapter, product.product_id)
        logger.info(f"Symbol={cfg.symbol} mark={mark} pos={pos}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(cli())
