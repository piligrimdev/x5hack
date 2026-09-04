"""Feature 007 US5: GET /receipts/economy total_saved includes cashback_applied_rub.

Verifies at the repository level: economy summary aggregates both discount savings
AND cashback amounts across all user receipts.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

from webx5.crud.receipt import ReceiptRepository


def _mock_row(total_saved_discounts: str, total_paid_before: str):
    m = MagicMock()
    m.total_saved_discounts = Decimal(total_saved_discounts)
    m.total_paid_before_cashback = Decimal(total_paid_before)
    return m


def _mock_cashback(total: str):
    m = MagicMock()
    m.total_cashback = Decimal(total)
    return m


def test_economy_includes_cashback_in_total_saved():
    session = MagicMock()
    # First .execute() returns items row; second returns cashback row.
    session.execute.side_effect = [
        MagicMock(one=lambda: _mock_row("100", "500")),
        MagicMock(one=lambda: _mock_cashback("30")),
    ]
    session.scalar.return_value = 2

    repo = ReceiptRepository()
    summary = repo.get_economy_summary(session, uuid.uuid4())

    # total_saved = discount_savings 100 + cashback 30 = 130
    assert summary["total_saved"] == Decimal("130")
    # total_paid = 500 - 30 = 470 (cashback reduces actual paid)
    assert summary["total_paid"] == Decimal("470")
    assert summary["receipts_count"] == 2


def test_economy_zero_cashback_matches_original_behavior():
    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(one=lambda: _mock_row("100", "500")),
        MagicMock(one=lambda: _mock_cashback("0")),
    ]
    session.scalar.return_value = 1

    repo = ReceiptRepository()
    summary = repo.get_economy_summary(session, uuid.uuid4())

    assert summary["total_saved"] == Decimal("100")
    assert summary["total_paid"] == Decimal("500")


def test_economy_paid_never_negative_even_if_cashback_exceeds():
    # Should never happen in practice (validated by receipt-service), but guard.
    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(one=lambda: _mock_row("50", "100")),
        MagicMock(one=lambda: _mock_cashback("200")),
    ]
    session.scalar.return_value = 1

    repo = ReceiptRepository()
    summary = repo.get_economy_summary(session, uuid.uuid4())

    assert summary["total_paid"] == Decimal("0")
