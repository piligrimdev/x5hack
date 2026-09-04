from __future__ import annotations

import pytest

from webx5.services.points_applier import (
    apply_cashback,
    resolve_points_to_spend,
)


# ---------- apply_cashback ----------

def test_normal_spend_within_all_limits():
    # subtotal=500 rub, requested=500 pts, balance=1000, rate=10
    result = apply_cashback(500, 500, 1000, 10)
    assert result.applied_points == 500
    assert result.cashback_rub == 50
    assert result.capped_by == "none"


def test_capped_by_balance_when_balance_smallest():
    # balance is the tightest limit
    result = apply_cashback(500, 5000, 300, 10)
    assert result.applied_points == 300
    assert result.cashback_rub == 30
    assert result.capped_by == "balance"


def test_capped_by_receipt_total_when_receipt_cap_smallest():
    # subtotal * rate = 500*10 = 5000; balance and request are bigger
    result = apply_cashback(500, 8000, 10000, 10)
    assert result.applied_points == 5000
    assert result.cashback_rub == 500
    assert result.capped_by == "receipt_total"


def test_all_wants_spend_all_balance():
    # points_requested = balance exactly
    result = apply_cashback(500, 1000, 1000, 10)
    assert result.applied_points == 1000
    assert result.cashback_rub == 100
    assert result.capped_by == "none"


def test_rounded_down_to_multiple_of_rate():
    # requested 105 → round down to 100 at rate 10
    result = apply_cashback(500, 105, 500, 10)
    assert result.applied_points == 100
    assert result.cashback_rub == 10


def test_zero_balance_yields_zero():
    result = apply_cashback(500, 500, 0, 10)
    assert result.applied_points == 0
    assert result.cashback_rub == 0
    assert result.capped_by == "none"


def test_zero_subtotal_yields_zero():
    result = apply_cashback(0, 500, 500, 10)
    assert result.applied_points == 0
    assert result.capped_by == "none"


def test_zero_points_requested_yields_zero():
    result = apply_cashback(500, 0, 500, 10)
    assert result.applied_points == 0


def test_below_rate_rounds_to_zero():
    # requested 5, rate 10 → floor to 0
    result = apply_cashback(500, 5, 500, 10)
    assert result.applied_points == 0
    assert result.cashback_rub == 0


# ---------- resolve_points_to_spend ----------

def test_resolve_none_is_zero():
    assert resolve_points_to_spend(None, 1000) == 0


def test_resolve_zero_is_zero():
    assert resolve_points_to_spend(0, 1000) == 0


def test_resolve_all_returns_balance():
    assert resolve_points_to_spend("all", 1000) == 1000


def test_resolve_all_with_zero_balance():
    assert resolve_points_to_spend("all", 0) == 0


def test_resolve_int_passes_through():
    assert resolve_points_to_spend(500, 1000) == 500


def test_resolve_negative_raises():
    with pytest.raises(ValueError):
        resolve_points_to_spend(-1, 1000)


def test_resolve_bad_string_raises():
    with pytest.raises(ValueError):
        resolve_points_to_spend("half", 1000)
