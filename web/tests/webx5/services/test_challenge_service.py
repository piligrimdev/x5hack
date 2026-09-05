"""Unit tests for ChallengeService.generate_batch — orchestration only.

The new synth API returns a list of up to 4 records with `challenge_slot`
in one call. Tests mock that call and assert:
  * every returned record is audit-logged (FR-018)
  * `no_challenge` path skips persistence (FR-022)
  * script exception is caught & logged
  * invariant "no more than 4 active tasks" is respected (FR-001)
  * slots already active are skipped
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from webx5.services.challenge import ChallengeService


def _service_with_mocks():
    task_repo = MagicMock()
    task_repo.get_active_for_user.return_value = []
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


def _canned(slot: str, path: str = "personal") -> dict:
    return {
        "user_id": "u",
        "path": path,
        "challenge_slot": slot,
        "challenge_title": f"{slot} title",
        "description": "D",
        "target_categories": ["cat"],
        "mechanic": f"mech {slot}",
        "reward_rub": 45.0,
        "target_quantity": 2,
        "model": "test-model" if slot.startswith("llm") else None,
        "reasoning": "test",
    }


def _batch_all_four() -> list[dict]:
    return [
        _canned("llm_habit"),
        _canned("llm_discovery"),
        _canned("generic"),
        _canned("vibe"),
    ]


def test_generate_batch_persists_all_four_slots():
    service, task_repo, log_repo, adapter = _service_with_mocks()

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_four()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    assert len(created) == 4
    assert log_repo.record.call_count == 4
    assert adapter.persist_challenge.call_count == 4


def test_generate_batch_no_challenge_returns_empty_but_logs():
    service, task_repo, log_repo, adapter = _service_with_mocks()

    no_challenge_batch = [{"user_id": "u", "path": "no_challenge", "challenge_slot": None, "reasoning": "sat"}]
    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=no_challenge_batch), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    assert created == []
    assert log_repo.record.call_count == 1
    adapter.persist_challenge.assert_not_called()


def test_generate_batch_script_exception_logs_and_returns_empty():
    service, task_repo, log_repo, adapter = _service_with_mocks()

    def raise_boom(*args, **kwargs):
        raise RuntimeError("simulated LLM outage")

    with patch("webx5.services.challenge.generate_challenge_for_user", side_effect=raise_boom), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    assert created == []
    log_repo.record.assert_called_once()
    kwargs = log_repo.record.call_args.kwargs
    assert kwargs["script_result"]["path"] == "generic_fallback"
    assert "simulated LLM outage" in kwargs["script_result"]["error"]


def test_generate_batch_no_slots_when_4_active():
    service, task_repo, log_repo, adapter = _service_with_mocks()
    task_repo.get_active_for_user.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]

    created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)
    assert created == []
    log_repo.record.assert_not_called()


def test_generate_batch_skips_slot_already_active():
    """If user already has an 'llm_habit' task active, that record from the batch is skipped."""
    service, task_repo, log_repo, adapter = _service_with_mocks()

    llm_active_task = MagicMock()
    llm_active_task.challenge_slot = "llm_habit"
    task_repo.get_active_for_user.return_value = [llm_active_task]

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_four()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=3)

    assert len(created) == 3
    persisted_slots = [
        call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list
    ]
    assert "llm_habit" not in persisted_slots
    assert set(persisted_slots) == {"llm_discovery", "generic", "vibe"}
