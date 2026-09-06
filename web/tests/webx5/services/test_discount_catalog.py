from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from webx5.services.discount_catalog import describe_discount, format_discount_value

MOSCOW = ZoneInfo("Europe/Moscow")


def _discount(**overrides):
    data = {
        "id": uuid.uuid4(),
        "value": Decimal("10"),
        "value_type": "percent",
        "discount_type": SimpleNamespace(name="персональная"),
        "link_type": SimpleNamespace(name="all"),
        "entity_id": None,
        "loyalty_card_id": uuid.uuid4(),
        "valid_from": None,
        "valid_to": datetime(2026, 9, 13, 15, 0, tzinfo=MOSCOW),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_format_percent_strips_trailing_zeros():
    assert format_discount_value(Decimal("10.00"), "percent") == "10%"
    assert format_discount_value(Decimal("7.5"), "percent") == "7.5%"


def test_format_fixed_rub():
    assert format_discount_value(Decimal("50"), "fixed_rub") == "50 ₽"


def test_describe_referral_personal_all():
    out = describe_discount(_discount())
    assert out.title == "Персональная скидка 10%"
    assert "на все покупки" in out.description
    assert "реферальный код" in out.description
    assert "До 13.09.2026" in out.description
    assert out.is_personal is True


def test_describe_category_promo_includes_name():
    out = describe_discount(
        _discount(
            value=Decimal("15"),
            discount_type=SimpleNamespace(name="акция"),
            link_type=SimpleNamespace(name="category"),
            loyalty_card_id=None,
            valid_to=None,
        ),
        entity_name="молочные продукты и яйца",
    )
    assert out.title == "Акция 15%"
    assert "на категорию «молочные продукты и яйца»" in out.description
    assert out.is_personal is False
