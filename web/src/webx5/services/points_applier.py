from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CappedBy = Literal["none", "balance", "receipt_total"]


@dataclass(frozen=True)
class CashbackResult:
    applied_points: int
    cashback_rub: int
    capped_by: CappedBy


def apply_cashback(
    subtotal_rub: int,
    points_requested: int,
    balance: int,
    rate: int,
) -> CashbackResult:
    if subtotal_rub <= 0 or points_requested <= 0 or balance <= 0 or rate <= 0:
        return CashbackResult(applied_points=0, cashback_rub=0, capped_by="none")

    receipt_cap = subtotal_rub * rate
    raw = min(points_requested, balance, receipt_cap)
    # Round down to multiple of rate — payments only in whole rubles.
    applied = (raw // rate) * rate
    cashback_rub = applied // rate

    if applied == 0:
        return CashbackResult(applied_points=0, cashback_rub=0, capped_by="none")

    if raw == receipt_cap and receipt_cap < min(points_requested, balance):
        capped: CappedBy = "receipt_total"
    elif raw == balance and balance < points_requested:
        capped = "balance"
    else:
        capped = "none"

    return CashbackResult(
        applied_points=applied,
        cashback_rub=cashback_rub,
        capped_by=capped,
    )


def resolve_points_to_spend(raw: int | str | None, balance: int) -> int:
    if raw is None:
        return 0
    if isinstance(raw, str):
        if raw == "all":
            return max(balance, 0)
        raise ValueError(f"invalid points_to_spend string: {raw!r}")
    if isinstance(raw, int):
        if raw < 0:
            raise ValueError("points_to_spend must be non-negative")
        return raw
    raise ValueError(f"invalid points_to_spend type: {type(raw).__name__}")
