from __future__ import annotations
from dataclasses import dataclass
from typing import List, Literal, Optional

Side = Literal["buy", "sell"]


@dataclass
class Position:
    side: Literal["NONE", "LONG", "SHORT"] = "NONE"
    open_lots: int = 0
    avg_price: Optional[float] = None


@dataclass
class OrderIntent:
    side: Side
    qty_lots: int
    price: float
    typ: Literal["TP", "AVG", "SEED"]


@dataclass
class Config:
    seed_offset_usd: float
    tp_step_usd: float
    avg_step_usd: float
    avg_multiplier: int
    max_total_lots: int


def compute_next_orders(position: Position, mark_price: float, cfg: Config) -> List[OrderIntent]:
    intents: List[OrderIntent] = []
    if position.side == "NONE":
        # Seed both ways? Spec says single seed on either side; choose LONG by default.
        intents.append(OrderIntent(side="buy", qty_lots=1, price=mark_price - cfg.seed_offset_usd, typ="SEED"))
        return intents

    # Determine direction-specific constants
    is_long = position.side == "LONG"
    avg = position.avg_price or mark_price

    # TP opposite side
    tp_side: Side = "sell" if is_long else "buy"
    tp_price = avg + cfg.tp_step_usd if is_long else avg - cfg.tp_step_usd
    tp_qty = position.open_lots + 1  # flip with one extra

    # AVG same side
    avg_side: Side = "buy" if is_long else "sell"
    avg_price = avg - cfg.avg_step_usd if is_long else avg + cfg.avg_step_usd
    avg_qty = position.open_lots * cfg.avg_multiplier

    if position.open_lots + avg_qty <= cfg.max_total_lots:
        intents.append(OrderIntent(side=avg_side, qty_lots=avg_qty, price=avg_price, typ="AVG"))
    # Always place TP
    intents.append(OrderIntent(side=tp_side, qty_lots=tp_qty, price=tp_price, typ="TP"))

    return intents
