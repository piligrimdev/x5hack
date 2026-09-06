from __future__ import annotations

import uuid
from datetime import UTC, datetime
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


def test_build_profile_reads_full_history_and_computes_category_last_purchase():
    adapter = ChallengeAdapter(task_repo=MagicMock(), basket_repo=MagicMock())
    user_id = uuid.uuid4()

    user = MagicMock(id=user_id, vibe_type=None)

    receipt_old = MagicMock(id=uuid.uuid4(), purchase_date=datetime(2020, 1, 1, tzinfo=UTC), channel="offline")
    receipt_recent = MagicMock(id=uuid.uuid4(), purchase_date=datetime(2026, 8, 1, tzinfo=UTC), channel="offline")

    product = MagicMock()
    product.name = "Молоко 3.2%"
    category = MagicMock()
    category.name = "молочные продукты и яйца"

    def make_item():
        item = MagicMock()
        item.base_price_at_purchase = "80.00"
        item.paid_price = "80.00"
        item.quantity = 1
        item.discount_id = None
        return item

    query_results = iter([
        [receipt_old, receipt_recent],
        [(make_item(), product, category)],
        [(make_item(), product, category)],
    ])

    def execute(stmt):
        rows = next(query_results)
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        result.all.return_value = rows
        return result

    session = MagicMock()
    session.get.return_value = user
    session.execute.side_effect = execute

    adapter.task_repo.count_tasks_for_slot.return_value = 0
    adapter.basket_repo.suggest_items.return_value = []

    config = MagicMock(category_economics=[])
    profile = adapter.build_profile(session, user_id, config)

    assert profile["category_last_purchase"] == {"молочные продукты и яйца": "2026-08-01"}
    assert len(profile["receipts"]) == 2  # spans >90 days — the cutoff is gone


def test_persist_challenge_uses_deadline_days_when_present():
    adapter = ChallengeAdapter(task_repo=MagicMock(), basket_repo=MagicMock())
    adapter.task_repo.create.return_value = MagicMock(id=uuid.uuid4())
    adapter.task_item_repo = MagicMock()
    session = MagicMock()

    with patch.object(adapter, "resolve_criterion", return_value=("category", uuid.uuid4())):
        adapter.persist_challenge(
            session, uuid.uuid4(),
            {"challenge_title": "T", "reward_rub": 10, "deadline_days": 14, "challenge_slot": "llm_habit"},
        )

    _, kwargs = adapter.task_repo.create.call_args
    assert kwargs["deadline"] is not None
    assert 13 <= (kwargs["deadline"] - datetime.now(UTC)).days <= 14


def test_persist_challenge_leaves_deadline_none_when_absent():
    adapter = ChallengeAdapter(task_repo=MagicMock(), basket_repo=MagicMock())
    adapter.task_repo.create.return_value = MagicMock(id=uuid.uuid4())
    adapter.task_item_repo = MagicMock()
    session = MagicMock()

    with patch.object(adapter, "resolve_criterion", return_value=("category", uuid.uuid4())):
        adapter.persist_challenge(session, uuid.uuid4(), {"challenge_title": "T", "reward_rub": 10})

    _, kwargs = adapter.task_repo.create.call_args
    assert kwargs["deadline"] is None
