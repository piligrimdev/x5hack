from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

from synth.challenges import VIBE_CATEGORIES
from webx5.services.challenge_adapter import ChallengeAdapter


def _adapter():
    return ChallengeAdapter(task_repo=MagicMock())


def test_resolve_vibe_category_reuses_stored_value_for_current_month():
    adapter = _adapter()
    session = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    user.vibe_category = "Здоровье и лёгкость"
    user.vibe_month = date.today().replace(day=1)

    result = adapter._resolve_vibe_category(session, user)

    assert result == "Здоровье и лёгкость"
    session.flush.assert_not_called()


def test_resolve_vibe_category_assigns_and_persists_when_missing():
    adapter = _adapter()
    session = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    user.vibe_category = None
    user.vibe_month = None

    result = adapter._resolve_vibe_category(session, user)

    assert result in VIBE_CATEGORIES
    assert user.vibe_category == result
    assert user.vibe_month == date.today().replace(day=1)
    session.flush.assert_called_once()


def test_resolve_vibe_category_reassigns_when_month_is_stale():
    adapter = _adapter()
    session = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    user.vibe_category = "Быстро и просто"
    user.vibe_month = date(2020, 1, 1)

    result = adapter._resolve_vibe_category(session, user)

    assert user.vibe_month == date.today().replace(day=1)
    session.flush.assert_called_once()


def test_resolve_vibe_category_is_deterministic_for_the_same_user_and_month():
    adapter = _adapter()
    user_id = uuid.uuid4()

    session_a = MagicMock()
    user_a = MagicMock()
    user_a.id = user_id
    user_a.vibe_category = None
    user_a.vibe_month = None
    result_a = adapter._resolve_vibe_category(session_a, user_a)

    session_b = MagicMock()
    user_b = MagicMock()
    user_b.id = user_id
    user_b.vibe_category = None
    user_b.vibe_month = None
    result_b = adapter._resolve_vibe_category(session_b, user_b)

    assert result_a == result_b
