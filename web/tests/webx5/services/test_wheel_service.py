from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from webx5.entities.reward import GiftReward
from webx5.entities.wheel import WheelSpin
from webx5.services.prize_catalog import WheelSector
from webx5.services.wheel import InsufficientCouponsError, WheelService


def _cashback_sector() -> WheelSector:
    return WheelSector(
        code="small_cashback",
        label="Небольшой кешбэк",
        description="10 ₽",
        prize_type="cashback",
        probability_percent=100,
        cashback_rub=10,
    )


def _gift_sector(entity_id: uuid.UUID) -> WheelSector:
    return WheelSector(
        code="gift_chocolate",
        label="Подарок",
        description="1 шт",
        prize_type="gift",
        probability_percent=100,
        gift_criterion_type="category",
        gift_category_name="кондитерка",
        gift_quantity=1,
        gift_entity_id=entity_id,
    )


def _service(coupons, spins, catalog, gifts) -> WheelService:
    return WheelService(
        coupon_service=coupons,
        spin_repo=spins,
        catalog=catalog,
        gift_repo=gifts,
    )


class _PickFirst:
    def choices(self, population, weights, k):
        return [population[0]]


def test_spin_cashback_awards_points() -> None:
    user_id = uuid.uuid4()
    spin = WheelSpin()
    spin.id = uuid.uuid4()
    spin.loyalty_card_id = user_id
    spin.sector_code = "small_cashback"
    spin.prize_type = "cashback"
    spin.prize_label = "Небольшой кешбэк"
    spin.cashback_rub = 10
    spin.created_at = datetime.now(timezone.utc)

    coupons = MagicMock()
    coupons.debit_for_spin.return_value = True
    coupons.get_balance.return_value = 0
    spins = MagicMock()
    spins.create.return_value = spin
    catalog = MagicMock()
    catalog.get_sectors.return_value = [_cashback_sector()]
    gifts = MagicMock()
    service = _service(coupons, spins, catalog, gifts)
    session = MagicMock()
    points = MagicMock()
    points.award_for_spin.return_value = 100

    with patch("webx5.core.points.points_service", points):
        result = service.spin(session, user_id, rng=_PickFirst())

    assert result["prize_type"] == "cashback"
    assert result["points_awarded"] == 100
    assert result["gift_reward_id"] is None
    points.award_for_spin.assert_called_once()
    gifts.create.assert_not_called()


def test_spin_gift_creates_reward() -> None:
    user_id = uuid.uuid4()
    cat_id = uuid.uuid4()
    spin = WheelSpin()
    spin.id = uuid.uuid4()
    spin.loyalty_card_id = user_id
    spin.sector_code = "gift_chocolate"
    spin.prize_type = "gift"
    spin.prize_label = "Подарок"
    spin.cashback_rub = None
    spin.created_at = datetime.now(timezone.utc)
    gift = GiftReward()
    gift.id = uuid.uuid4()

    coupons = MagicMock()
    coupons.debit_for_spin.return_value = True
    coupons.get_balance.return_value = 2
    spins = MagicMock()
    spins.create.return_value = spin
    catalog = MagicMock()
    catalog.get_sectors.return_value = [_gift_sector(cat_id)]
    gifts = MagicMock()
    gifts.create.return_value = gift
    service = _service(coupons, spins, catalog, gifts)

    result = service.spin(MagicMock(), user_id, rng=_PickFirst())

    assert result["prize_type"] == "gift"
    assert result["gift_reward_id"] == gift.id
    gifts.create.assert_called_once()
    spins.set_gift_reward_id.assert_called_once()


def test_spin_denied_when_no_coupons() -> None:
    coupons = MagicMock()
    coupons.debit_for_spin.return_value = False
    spins = MagicMock()
    spins.create.return_value = WheelSpin()
    catalog = MagicMock()
    catalog.get_sectors.return_value = [_cashback_sector()]
    service = _service(coupons, spins, catalog, MagicMock())

    with pytest.raises(InsufficientCouponsError):
        service.spin(MagicMock(), uuid.uuid4(), rng=_PickFirst())


def test_spin_has_no_sector_code_argument() -> None:
    """Client cannot pass a desired sector — spin() has no such parameter."""
    import inspect

    sig = inspect.signature(WheelService.spin)
    assert "sector_code" not in sig.parameters
    assert "prize_id" not in sig.parameters


def test_two_spins_one_coupon_second_denied() -> None:
    user_id = uuid.uuid4()
    coupons = MagicMock()
    coupons.debit_for_spin.side_effect = [True, False]
    coupons.get_balance.return_value = 0
    spin = WheelSpin()
    spin.id = uuid.uuid4()
    spin.sector_code = "small_cashback"
    spin.prize_type = "cashback"
    spin.prize_label = "x"
    spin.cashback_rub = 10
    spin.created_at = datetime.now(timezone.utc)
    spins = MagicMock()
    spins.create.return_value = spin
    catalog = MagicMock()
    catalog.get_sectors.return_value = [_cashback_sector()]
    service = _service(coupons, spins, catalog, MagicMock())
    points = MagicMock()
    points.award_for_spin.return_value = 100

    with patch("webx5.core.points.points_service", points):
        first = service.spin(MagicMock(), user_id, rng=_PickFirst())
        with pytest.raises(InsufficientCouponsError):
            service.spin(MagicMock(), user_id, rng=_PickFirst())

    assert first["spin_id"] == spin.id
