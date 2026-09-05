from __future__ import annotations

from datetime import date

from webx5.entities.user import User


def test_user_vibe_columns_default_to_none():
    user = User(phone="+70000000000")
    assert user.vibe_category is None
    assert user.vibe_month is None


def test_user_vibe_columns_are_settable():
    user = User(phone="+70000000001")
    user.vibe_category = "Здоровье и лёгкость"
    user.vibe_month = date(2026, 9, 1)
    assert user.vibe_category == "Здоровье и лёгкость"
    assert user.vibe_month == date(2026, 9, 1)
