"""Unit tests for ChallengeService.generate_batch — orchestration only.

Mocks the synth.challenges.generate_challenge_for_user call to return
canned dicts; asserts:
  * batch mix uses 3 different challenge_types (FR-005a)
  * no_challenge path skips persistence but still logs (FR-022, FR-018)
  * script exception is caught & logged (FR-018 error path)
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from webx5.services.challenge import ChallengeService


def _service_with_mocks():
    task_repo = MagicMock()
    task_repo.get_active_for_user.return_value = []  # fresh user
    log_repo = MagicMock()
    log_repo.record.return_value = uuid.uuid4()
    adapter = MagicMock()
    adapter.build_profile.return_value = {"user_id": "u", "receipts": []}
    adapter.persist_challenge.side_effect = lambda session, uid, r: uuid.uuid4()
    synth_config = MagicMock()

    service = ChallengeService(
        task_repo=task_repo,
        log_repo=log_repo,
        adapter=adapter,
        synth_config=synth_config,
        model="test-model",
        api_key="test-key",
    )
    return service, task_repo, log_repo, adapter


def _canned(path: str = "personal") -> dict:
    return {
        "user_id": "u",
        "path": path,
        "challenge_title": "T",
        "description": "D",
        "target_categories": ["cat"],
        "mechanic": "порог трат + скидка на любимый товар",
        "reward_rub": 45.0,
        "model": "test-model",
        "reasoning": "test",
    }


def test_generate_batch_mix_calls_three_types_in_order():
    service, task_repo, log_repo, adapter = _service_with_mocks()

    call_types: list[str] = []

    def fake_gen(*args, **kwargs):
        call_types.append(kwargs["challenge_type"])
        return _canned()

    with patch("webx5.services.challenge.generate_challenge_for_user", side_effect=fake_gen), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=3)

    assert call_types == ["spend_threshold", "category_expansion", "llm"]
    assert len(created) == 3
    assert log_repo.record.call_count == 3


def test_generate_batch_no_challenge_path_skips_persist_but_logs():
    service, task_repo, log_repo, adapter = _service_with_mocks()

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_canned("no_challenge")), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=3)

    assert created == []
    # 3 attempts × 1 log each = 3 log rows, no persistence
    assert log_repo.record.call_count == 3
    adapter.persist_challenge.assert_not_called()


def test_generate_batch_script_exception_still_logs_error():
    service, task_repo, log_repo, adapter = _service_with_mocks()

    def raise_boom(*args, **kwargs):
        raise RuntimeError("simulated LLM outage")

    with patch("webx5.services.challenge.generate_challenge_for_user", side_effect=raise_boom), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=3)

    assert created == []
    # Error paths log too
    assert log_repo.record.call_count == 3
    call_args = log_repo.record.call_args_list[0].kwargs
    assert call_args["script_result"]["path"] == "generic_fallback"
    assert "simulated LLM outage" in call_args["script_result"]["error"]


def test_generate_batch_respects_active_count_invariant():
    """If user already has 3 active tasks — generate_batch does nothing (FR-001)."""
    service, task_repo, log_repo, adapter = _service_with_mocks()
    task_repo.get_active_for_user.return_value = [MagicMock(), MagicMock(), MagicMock()]

    created = service.generate_batch(MagicMock(), uuid.uuid4(), count=3)
    assert created == []
    log_repo.record.assert_not_called()
