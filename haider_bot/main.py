from __future__ import annotations
import os
import sys
import time
import signal
import json
from dataclasses import dataclass
from typing import Optional, List, Tuple, Any
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from .adapters.delta_adapter import DeltaAdapter, DeltaAPIError
from .utils import round_price, gen_client_order_id, gen_target_coid
from .core.strategy import Position, OrderIntent, Config as StratCfg, compute_next_orders

# In-memory guard for last placed targets to avoid duplicate placements when open-orders GET fails
_last_target: dict = {}


@dataclass
class BotConfig:
    symbol: str
    base_url: Optional[str]
    poll_interval_sec: float
    leverage: Optional[int]
    use_post_only: bool
    shade_ticks: int
    follow_threshold_ticks: int
    require_confirmation: bool
    env_label: str
    log_level: str
    log_file: Optional[str]
    strategy: StratCfg
    lot_size_btc: Optional[float]


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
    # Prefer config values; no env fallbacks for these keys
    symbol = str(ex.get("symbol", "BTCUSD"))
    base_url = str(ex.get("base_url", "https://cdn-ind.testnet.deltaex.org"))
    poll_ms = float(ex.get("poll_interval_ms", 1000))
    leverage = data.get("sizing", {}).get("leverage")
    lot_size_btc = data.get("sizing", {}).get("lot_size_btc")
    use_post_only = bool(ex.get("use_post_only", True))
    shade_ticks = int(ex.get("price_shade_ticks", 1))
    follow_threshold_ticks = int(ex.get("price_follow_threshold_ticks", 2))
    require_confirmation = bool(ex.get("require_confirmation", False))
    env_label = str(ex.get("env_label", "LIVE"))
    log_level = str(logging.get("level", "INFO"))
    log_file = logging.get("file")
    return BotConfig(
        symbol=symbol,
        base_url=base_url,
        poll_interval_sec=max(0.2, poll_ms / 1000.0),
        leverage=leverage,
        use_post_only=use_post_only,
        shade_ticks=shade_ticks,
    follow_threshold_ticks=follow_threshold_ticks,
    require_confirmation=require_confirmation,
    env_label=env_label,
        log_level=log_level,
        log_file=log_file,
        strategy=strat,
    lot_size_btc=lot_size_btc,
    )


def parse_position(adapter: Any, product_id: int) -> Position:
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


def ensure_leverage(adapter: Any, product_id: int, leverage: Optional[int]) -> None:
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
    adapter: Any,
    env: str,
    product_id: int,
    tick: float,
    intents: List[OrderIntent],
    use_post_only: bool,
    shade_ticks: int,
    follow_threshold_ticks: int = 2,
    require_confirmation: bool = False,
    lot_size_btc: Optional[float] = None,
) -> None:
    # Fetch current open orders for this product
    try:
        open_data = adapter.get_open_orders(product_ids=str(product_id))
        open_items = open_data.get("result") or []
    except Exception as e:
        logger.warning(f"Could not fetch open orders: {e}")
        open_items = []

    # Index existing bot orders by client_order_id and by (side, rounded_price)
    existing_coids = {str(od.get("client_order_id")): od for od in open_items if str(od.get("client_order_id", "")).startswith("HAIDER-")}
    existing_by_sig = {}
    for od in open_items:
        coid = str(od.get("client_order_id") or "")
        if not coid.startswith("HAIDER-"):
            continue
        side = str(od.get("side", "")).lower()
        try:
            opx = float(od.get("limit_price") or od.get("price") or 0)
        except Exception:
            opx = 0.0
        opx = round_price(opx, tick)
        existing_by_sig[(side, opx)] = od

    # Build target set and place missing
    target_sigs: List[Tuple[str, float, str]] = []  # (side, price, typ)
    target_coids: List[str] = []
    seq = 1
    for it in intents:
        px = _shade_price(it.price, it.side, tick, shade_ticks)
        target_sigs.append((it.side, px, it.typ))
        # Deterministic COID per target prevents duplicates across cycles
        coid = gen_target_coid(env=env, typ=it.typ, side=it.side, product_id=product_id, price=px, tick_size=tick)
        target_coids.append(coid)
        # Skip placement if identical bot order already exists
        if coid in existing_coids:
            logger.debug(f"Target {it.typ} {it.side}@{px} already placed as {coid}; skipping")
            continue
        # If a bot order exists within follow-threshold ticks, keep it to avoid churn
        keep_existing = False
        for (eside, eprice), eod in existing_by_sig.items():
            if eside == it.side:
                tick_diff = abs((px - eprice) / tick) if tick > 0 else abs(px - eprice)
                if tick_diff <= max(0, follow_threshold_ticks):
                    logger.debug(f"Keeping existing {it.side}@{eprice} (within {tick_diff:.0f} ticks of target {px})")
                    keep_existing = True
                    break
        if keep_existing:
            continue

        # In-memory guard: if we just placed a similar target recently, skip
        key = (product_id, it.side, it.typ)
        last = _last_target.get(key)
        if last is not None:
            last_px, last_ts = last
            tick_diff_mem = abs((px - last_px) / tick) if tick > 0 else abs(px - last_px)
            # 30s TTL window to avoid rapid re-placement during transient API 401s
            if tick_diff_mem <= max(0, follow_threshold_ticks) and (time.time() - last_ts) <= 30:
                logger.debug(f"Skip re-place {it.typ} {it.side}@{px}; last {last_px} within {tick_diff_mem:.0f} ticks and 30s window")
                continue

        # If confirmation is required, ask the user before placing
        if require_confirmation:
            lots = it.qty_lots
            btc = None
            if lot_size_btc is not None:
                try:
                    btc = float(lots) * float(lot_size_btc)
                except Exception:
                    btc = None
            reason = it.typ.upper()
            detail = f"About to place: {reason} {it.side.upper()} {lots} lot(s)"
            if btc is not None:
                detail += f" (~{btc:.6f} BTC)"
            detail += f" at {px} (tick={tick}). COID={coid}. Proceed? [y/N]: "
            try:
                ans = input(detail)
            except Exception:
                ans = "n"
            if not ans or ans.strip().lower() not in ("y", "yes"):
                logger.info(f"User declined: {reason} {it.side}@{px}; skipping")
                continue

        try:
            res = adapter.place_limit_order(
                product_id=product_id,
                side=it.side,
                size=it.qty_lots,
                limit_price=px,
                post_only=use_post_only,
                client_order_id=coid,
            )
            logger.info(f"Placed {it.typ} {it.side} {it.qty_lots}@{px}: {json.dumps(res)[:400]}...")
            # Update in-memory last target on successful placement
            _last_target[key] = (px, time.time())
        except DeltaAPIError as e:
            msg = str(e)
            # Treat duplicate client_order_id as benign (idempotent placement)
            if "duplicate" in msg.lower() and "client_order_id" in msg.lower():
                logger.info(f"Duplicate COID for {it.typ} {it.side}@{px}; treating as already placed: {msg}")
                _last_target[key] = (px, time.time())
            else:
                logger.warning(f"Placement failed for {it.typ} {it.side}@{px}: {e}")

    # Cancel stale HAIDER orders whose COIDs are not in target set and are outside follow-threshold
    target_coids_set = set(target_coids)
    for od in open_items:
        coid = str(od.get("client_order_id") or "")
        if not coid.startswith("HAIDER-"):
            continue  # leave non-bot orders alone
        if coid not in target_coids_set:
            side = str(od.get("side", "")).lower()
            try:
                price = float(od.get("limit_price") or od.get("price") or 0)
            except Exception:
                price = 0.0
            price = round_price(price, tick)
            # If this existing order is close to the target side/price, keep it
            close_to_any = False
            for (s, p, _t) in target_sigs:
                if s == side:
                    tick_diff = abs((p - price) / tick) if tick > 0 else abs(p - price)
                    if tick_diff <= max(0, follow_threshold_ticks):
                        close_to_any = True
                        break
            if close_to_any:
                logger.debug(f"Keeping near-target order {coid} {side}@{price}")
                continue
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
    # Live interlock removed; operate with configured base_url

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

    # Create real adapter
    adapter = DeltaAdapter(api_key=api_key, api_secret=api_secret, base_url=cfg.base_url, user_agent="haider-bot/0.1")

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
        logger.info(f"Starting bot for {cfg.symbol} (product {product.product_id})")
    else:
        logger.info(f"Starting bot for {cfg.symbol}; waiting for product metadata to become available…")
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
                    env=cfg.env_label,
                    product_id=product.product_id,
                    tick=product.tick_size,
                    intents=intents,
                    use_post_only=cfg.use_post_only,
                    shade_ticks=cfg.shade_ticks,
                    follow_threshold_ticks=cfg.follow_threshold_ticks,
                    require_confirmation=cfg.require_confirmation,
                    lot_size_btc=(float(cfg.lot_size_btc) if cfg.lot_size_btc is not None else None),
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
    adapter = DeltaAdapter(api_key=api_key, api_secret=api_secret, base_url=cfg.base_url, user_agent="haider-bot/0.1")
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
