from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from webx5.crud.survival import SurvivalRepository


def test_fetch_purchase_dates_groups_by_user_and_category_deduped():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    rows = [
        (user_a, "молочные продукты и яйца", datetime(2026, 1, 1, tzinfo=UTC)),
        (user_a, "молочные продукты и яйца", datetime(2026, 1, 1, tzinfo=UTC)),  # same-day dup
        (user_a, "молочные продукты и яйца", datetime(2026, 1, 11, tzinfo=UTC)),
        (user_b, "овощи", datetime(2026, 1, 5, tzinfo=UTC)),
    ]
    session = MagicMock()
    session.execute.return_value.all.return_value = rows

    result = SurvivalRepository().fetch_purchase_dates(session)

    assert result[str(user_a)]["молочные продукты и яйца"] == [
        datetime(2026, 1, 1, tzinfo=UTC).date(),
        datetime(2026, 1, 11, tzinfo=UTC).date(),
    ]
    assert result[str(user_b)]["овощи"] == [datetime(2026, 1, 5, tzinfo=UTC).date()]


def test_fetch_purchase_dates_returns_empty_dict_for_no_rows():
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    assert SurvivalRepository().fetch_purchase_dates(session) == {}
