from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from webx5.tasks.receipt import process_receipt


def _make_task(challenge_slot: str | None) -> MagicMock:
    task = MagicMock()
    task.id = uuid.uuid4()
    task.challenge_slot = challenge_slot
    task.criterion_type = "product"
    task.quantity_current = 2
    task.quantity_target = 2
    return task


def _run_process_receipt(active_tasks, completed_task_ids, user_id, receipt_id):
    fake_receipt = MagicMock()
    fake_receipt.id = receipt_id
    fake_receipt.loyalty_card_id = user_id
    fake_receipt.store_id = uuid.uuid4()
    fake_receipt.purchase_date = None

    mock_session = MagicMock()
    mock_session.get.return_value = fake_receipt
    mock_session.execute.return_value.scalar_one.return_value = MagicMock()
    mock_db = MagicMock()
    mock_db.get_sync_session.return_value.__enter__.return_value = mock_session

    mock_task_repo = MagicMock()
    mock_task_repo.get_active_for_user.return_value = active_tasks

    mock_completion_service = MagicMock()
    mock_completion_service.apply_receipt.side_effect = lambda session, task, receipt: task.id in completed_task_ids

    mock_generate_challenges = MagicMock()

    with patch("webx5.core.challenges.task_completion_service", mock_completion_service), \
         patch("webx5.core.challenges.task_repo", mock_task_repo), \
         patch("webx5.core.db.db", mock_db), \
         patch("webx5.tasks.generation.generate_challenges", mock_generate_challenges):
        result = process_receipt(str(receipt_id))

    return result, mock_generate_challenges


def test_process_receipt_dispatches_one_combined_call_for_all_completions():
    """generate_batch now fills every currently-missing slot in one shot
    (see ChallengeService.generate_batch's docstring), so a single combined
    replacement call is enough regardless of how many tasks completed in
    this receipt — no need to name or count them precisely."""
    user_id = uuid.uuid4()
    receipt_id = uuid.uuid4()
    llm_habit_task = _make_task("llm_habit")
    llm_basket_task = _make_task("llm_basket")
    vibe_task = _make_task("vibe")
    untouched_task = _make_task("llm_discovery")

    result, mock_generate_challenges = _run_process_receipt(
        active_tasks=[llm_habit_task, llm_basket_task, vibe_task, untouched_task],
        completed_task_ids={llm_habit_task.id, llm_basket_task.id, vibe_task.id},
        user_id=user_id,
        receipt_id=receipt_id,
    )

    assert result["completed_count"] == 3
    mock_generate_challenges.apply_async.assert_called_once()
    args = mock_generate_challenges.apply_async.call_args.kwargs["args"]
    assert args == [str(user_id), 3]


def test_process_receipt_no_completions_does_not_dispatch_generation():
    user_id = uuid.uuid4()
    receipt_id = uuid.uuid4()
    open_task = _make_task("llm_habit")

    result, mock_generate_challenges = _run_process_receipt(
        active_tasks=[open_task],
        completed_task_ids=set(),
        user_id=user_id,
        receipt_id=receipt_id,
    )

    assert result["completed_count"] == 0
    mock_generate_challenges.apply_async.assert_not_called()
