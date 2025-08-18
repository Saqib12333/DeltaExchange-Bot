from __future__ import annotations
import time
import uuid
from datetime import datetime, timezone


def now_ts() -> int:
    """UTC microseconds since epoch (int)."""
    return int(time.time() * 1_000_000)


def iso_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def gen_client_order_id(env: str, typ: str, side: str, seq: int) -> str:
    # HAIDER-{ENV}-{TS_ISO}-{TYPE}-{SIDE}-{SEQ}
    return f"HAIDER-{env.upper()}-{iso_ts()}-{typ.upper()}-{side.upper()}-{seq:02d}"


def gen_target_coid(env: str, typ: str, side: str, product_id: int, price: float, tick_size: float) -> str:
    """Deterministic client_order_id for a given target.

    Format: HAIDER-{ENV}-{TYPE}-{SIDE}-P{product_id}-T{ticks}
    where ticks = int(round(price / tick_size)). This makes placements idempotent across cycles.
    """
    try:
        ticks = int(round(price / tick_size)) if tick_size > 0 else int(round(price))
    except Exception:
        ticks = int(round(price))
    return f"HAIDER-{env.upper()}-{typ.upper()}-{side.upper()}-P{product_id}-T{ticks}"


def clamp_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    n = round(value / step)
    return n * step


def round_price(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return price
    return float(f"{(round(price / tick_size) * tick_size):.10f}")


def round_qty(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    # floor to step to avoid exceeding
    n = int(qty / step)
    return float(f"{(n * step):.10f}")
