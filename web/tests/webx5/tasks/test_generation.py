from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from webx5.tasks.generation import generate_challenges


def test_generate_challenges_passes_count_through_to_generate_batch():
    user_id = uuid.uuid4()

    mock_session = MagicMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = MagicMock()
    mock_db = MagicMock()
    mock_db.get_sync_session.return_value.__enter__.return_value = mock_session

    mock_challenge_service = MagicMock()
    mock_challenge_service.generate_batch.return_value = [uuid.uuid4()]

    with patch("webx5.core.challenges.challenge_service", mock_challenge_service), \
         patch("webx5.core.db.db", mock_db):
        generate_challenges(str(user_id), 2)

    mock_challenge_service.generate_batch.assert_called_once_with(mock_session, user_id, 2)


def test_generate_challenges_no_op_when_user_not_found():
    user_id = uuid.uuid4()

    mock_session = MagicMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_db = MagicMock()
    mock_db.get_sync_session.return_value.__enter__.return_value = mock_session

    mock_challenge_service = MagicMock()

    with patch("webx5.core.challenges.challenge_service", mock_challenge_service), \
         patch("webx5.core.db.db", mock_db):
        result = generate_challenges(str(user_id), 1)

    assert result == {"status": "no_op", "reason": "user_not_found"}
    mock_challenge_service.generate_batch.assert_not_called()
