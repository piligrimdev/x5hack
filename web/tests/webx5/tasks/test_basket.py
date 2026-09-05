from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from webx5.tasks.basket import basket_apply_instruction


def test_basket_apply_instruction_passes_user_id_to_service():
    """The LLM assistant needs `user_id` to fetch the user's shopping/challenge
    context (`BasketService.apply_instruction`'s `user_id` param) — without it,
    the LLM never sees the user's active challenges at all."""
    user_id = uuid.uuid4()
    items_json = json.dumps([{"product_id": str(uuid.uuid4()), "quantity": 1}])

    fake_result = MagicMock()
    fake_result.applied = True
    fake_result.items = []
    fake_result.model_dump.return_value = {}

    mock_service = MagicMock()
    mock_service.apply_instruction.return_value = fake_result
    mock_session = MagicMock()
    mock_db = MagicMock()
    mock_db.get_sync_session.return_value.__enter__.return_value = mock_session

    with patch("webx5.core.basket.basket_service", mock_service), \
         patch("webx5.core.db.db", mock_db):
        basket_apply_instruction(str(user_id), items_json, "Собери все товары из заданий")

    mock_service.apply_instruction.assert_called_once()
    call_kwargs = mock_service.apply_instruction.call_args.kwargs
    assert call_kwargs.get("user_id") == user_id
