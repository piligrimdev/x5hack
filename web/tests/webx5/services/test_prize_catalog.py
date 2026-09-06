from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from webx5.services.prize_catalog import (
    FixedPrizeCatalog,
    GiftCatalogNotConfiguredError,
    WheelSector,
)


def test_fixed_catalog_four_sectors_sum_100_both_types() -> None:
    user_id = uuid.uuid4()
    category = MagicMock()
    category.id = uuid.uuid4()
    repo = MagicMock()
    repo.get_category_by_name.return_value = category
    catalog = FixedPrizeCatalog(catalog_repo=repo)

    sectors = catalog.get_sectors(MagicMock(), user_id)

    assert len(sectors) == 4
    assert sum(s.probability_percent for s in sectors) == 100
    types = {s.prize_type for s in sectors}
    assert types == {"cashback", "gift"}
    assert {s.code for s in sectors} == {
        "small_cashback",
        "medium_cashback",
        "gift_chocolate",
        "large_cashback",
    }
    gift = next(s for s in sectors if s.prize_type == "gift")
    assert gift.gift_entity_id == category.id
    repo.get_category_by_name.assert_called_once()


def test_fixed_catalog_missing_category_raises() -> None:
    repo = MagicMock()
    repo.get_category_by_name.return_value = None
    catalog = FixedPrizeCatalog(catalog_repo=repo)

    with pytest.raises(GiftCatalogNotConfiguredError):
        catalog.get_sectors(MagicMock(), uuid.uuid4())


def test_get_sectors_accepts_user_id() -> None:
    category = MagicMock()
    category.id = uuid.uuid4()
    repo = MagicMock()
    repo.get_category_by_name.return_value = category
    catalog = FixedPrizeCatalog(catalog_repo=repo)
    first = uuid.uuid4()
    second = uuid.uuid4()
    a = catalog.get_sectors(MagicMock(), first)
    b = catalog.get_sectors(MagicMock(), second)
    assert [s.code for s in a] == [s.code for s in b]
    assert all(isinstance(s, WheelSector) for s in a)
