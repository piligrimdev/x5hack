from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from synth.challenges import VIBE_CATEGORIES
from webx5.services.challenge_adapter import ChallengeAdapter


def _adapter():
    return ChallengeAdapter(task_repo=MagicMock(), basket_repo=MagicMock())


def test_resolve_vibe_category_returns_vibe_type_name_when_set():
    adapter = _adapter()
    session = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    user.vibe_type = MagicMock()
    user.vibe_type.name = "Здоровье и лёгкость"
    user.vibe_type_id = uuid.uuid4()

    result = adapter._resolve_vibe_category(session, user)

    assert result == "Здоровье и лёгкость"


def test_resolve_vibe_category_falls_back_to_pick_when_vibe_type_is_none():
    adapter = _adapter()
    session = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    user.vibe_type = None
    user.vibe_type_id = None

    result = adapter._resolve_vibe_category(session, user)

    assert result in VIBE_CATEGORIES


def test_resolve_vibe_category_is_deterministic_for_same_user_and_month():
    adapter = _adapter()
    user_id = uuid.uuid4()

    user_a = MagicMock()
    user_a.id = user_id
    user_a.vibe_type = None
    result_a = adapter._resolve_vibe_category(MagicMock(), user_a)

    user_b = MagicMock()
    user_b.id = user_id
    user_b.vibe_type = None
    result_b = adapter._resolve_vibe_category(MagicMock(), user_b)

    assert result_a == result_b


def test_suggested_basket_items_converts_product_quantity_pairs_to_plain_dicts():
    adapter = _adapter()
    session = MagicMock()
    category_id = uuid.uuid4()
    product = MagicMock()
    product.name = "Молоко 3.2%"
    product.category_id = category_id
    adapter.basket_repo.suggest_items.return_value = [(product, 2)]
    session.execute.return_value.all.return_value = [(category_id, "молочные продукты и яйца")]

    result = adapter._suggested_basket_items(session, uuid.uuid4())

    assert result == [{"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2}]


def test_suggested_basket_items_empty_when_no_suggestions():
    adapter = _adapter()
    session = MagicMock()
    adapter.basket_repo.suggest_items.return_value = []

    result = adapter._suggested_basket_items(session, uuid.uuid4())

    assert result == []
    session.execute.assert_not_called()
