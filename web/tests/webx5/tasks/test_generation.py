from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from webx5.tasks.generation import generate_challenges


def _run_generate_challenges(user_id, count, target_slots):
    mock_session = MagicMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = MagicMock()
    mock_db = MagicMock()
    mock_db.get_sync_session.return_value.__enter__.return_value = mock_session

    mock_challenge_service = MagicMock()
    mock_challenge_service.generate_batch.return_value = [uuid.uuid4()]

    with patch("webx5.core.challenges.challenge_service", mock_challenge_service), \
         patch("webx5.core.db.db", mock_db):
        generate_challenges(str(user_id), count, target_slots)

    return mock_challenge_service


def test_generate_challenges_threads_target_slots_as_a_set():
    user_id = uuid.uuid4()
    mock_challenge_service = _run_generate_challenges(user_id, 2, ["llm_habit", "vibe"])

    mock_challenge_service.generate_batch.assert_called_once()
    call = mock_challenge_service.generate_batch.call_args
    assert call.kwargs["target_slots"] == {"llm_habit", "vibe"}


def test_generate_challenges_defaults_target_slots_to_none():
    user_id = uuid.uuid4()
    mock_challenge_service = _run_generate_challenges(user_id, 5, None)

    call = mock_challenge_service.generate_batch.call_args
    assert call.kwargs["target_slots"] is None
