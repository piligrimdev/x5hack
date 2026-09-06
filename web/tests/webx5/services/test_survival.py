from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock

from webx5.services.survival import SurvivalCurveStore


def test_curves_are_fetched_lazily_and_cached():
    repo = MagicMock()
    repo.fetch_purchase_dates.return_value = {
        "u1": {"молоко": [date(2026, 1, 1), date(2026, 1, 11)]},
    }

    @contextmanager
    def fake_session():
        yield MagicMock()

    db = MagicMock()
    db.get_sync_session.side_effect = fake_session

    store = SurvivalCurveStore(db=db, repo=repo)
    repo.fetch_purchase_dates.assert_not_called()  # not called on construction

    curves = store.curves
    assert "молоко" in curves
    repo.fetch_purchase_dates.assert_called_once()

    store.curves  # noqa: B018 — second access, exercised for the cache-hit side effect
    repo.fetch_purchase_dates.assert_called_once()  # still just once — cached


def test_refresh_refits_curves_from_latest_receipts():
    repo = MagicMock()
    repo.fetch_purchase_dates.side_effect = [
        {"u1": {"молоко": [date(2026, 1, 1)]}},
        {"u1": {"молоко": [date(2026, 1, 1), date(2026, 9, 6)]}},
    ]

    @contextmanager
    def fake_session():
        yield MagicMock()

    db = MagicMock()
    db.get_sync_session.side_effect = fake_session
    store = SurvivalCurveStore(db=db, repo=repo)

    first = store.curves
    second = store.refresh()

    assert repo.fetch_purchase_dates.call_count == 2
    assert first["молоко"] != second["молоко"]
