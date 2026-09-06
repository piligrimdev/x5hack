from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from webx5.tasks.expiration import expire_tasks


def _make_expired_task(loyalty_card_id: uuid.UUID, challenge_slot: str | None) -> MagicMock:
    task = MagicMock()
    task.id = uuid.uuid4()
    task.loyalty_card_id = loyalty_card_id
    task.challenge_slot = challenge_slot
    task.deadline = datetime(2026, 1, 1, tzinfo=timezone.utc)
    task.title = "expired"
    return task


def _run_expire_tasks(expired_tasks):
    mock_session = MagicMock()
    mock_db = MagicMock()
    mock_db.get_sync_session.return_value.__enter__.return_value = mock_session

    mock_task_repo = MagicMock()
    mock_task_repo.expire_overdue.return_value = expired_tasks

    mock_generate_challenges = MagicMock()

    with patch("webx5.core.challenges.task_repo", mock_task_repo), \
         patch("webx5.core.db.db", mock_db), \
         patch("webx5.tasks.generation.generate_challenges", mock_generate_challenges):
        result = expire_tasks()

    return result, mock_generate_challenges


def test_expire_tasks_dispatches_one_combined_call_per_user():
    """generate_batch now fills every currently-missing slot in one shot
    (see ChallengeService.generate_batch's docstring), so one combined call
    per user is enough regardless of how many of their slots expired in
    this sweep."""
    user_id = uuid.uuid4()
    tasks = [
        _make_expired_task(user_id, "llm_habit"),
        _make_expired_task(user_id, "vibe"),
    ]

    result, mock_generate_challenges = _run_expire_tasks(tasks)

    assert result["status"] == "expired"
    assert result["count"] == 2
    assert result["users"] == 1
    mock_generate_challenges.apply_async.assert_called_once()
    args = mock_generate_challenges.apply_async.call_args.kwargs["args"]
    assert args == [str(user_id), 2]


def test_expire_tasks_separates_calls_per_user():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    tasks = [
        _make_expired_task(user_a, "llm_habit"),
        _make_expired_task(user_b, "generic"),
    ]

    result, mock_generate_challenges = _run_expire_tasks(tasks)

    assert result["users"] == 2
    assert mock_generate_challenges.apply_async.call_count == 2
    dispatched_user_ids = {
        call.kwargs["args"][0] for call in mock_generate_challenges.apply_async.call_args_list
    }
    assert dispatched_user_ids == {str(user_a), str(user_b)}


def test_expire_tasks_no_expired_does_not_dispatch_generation():
    result, mock_generate_challenges = _run_expire_tasks([])

    assert result == {"status": "no_expired", "count": 0, "users": 0}
    mock_generate_challenges.apply_async.assert_not_called()
