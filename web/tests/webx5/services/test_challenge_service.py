"""Unit tests for ChallengeService.generate_batch — orchestration only.

The new synth API returns a list of exactly 5 records with `challenge_slot`
in one call. Tests mock that call and assert:
  * every returned record is audit-logged (FR-018)
  * `no_challenge` path skips persistence (FR-022)
  * script exception is caught & logged
  * invariant "no more than 5 active tasks" is respected (FR-001)
  * slots already active are skipped
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from synth.challenges import CHALLENGE_SLOTS

from webx5.services.challenge import ChallengeService


def _service_with_mocks():
    task_repo = MagicMock()
    task_repo.get_active_for_user.return_value = []
    task_repo.get_last_criterion_per_slot.return_value = {}
    log_repo = MagicMock()
    log_repo.record.return_value = uuid.uuid4()
    adapter = MagicMock()
    adapter.build_profile.return_value = {"user_id": "u", "receipts": []}
    adapter.persist_challenge.side_effect = lambda session, uid, r: uuid.uuid4()
    # Default: every script_result resolves to its own distinct criterion
    # pair, so the cross-slot duplicate guard never fires unless a test
    # deliberately overrides this to force a collision (see
    # test_generate_batch_skips_duplicate_criterion_across_slots below).
    adapter.resolve_criterion.side_effect = lambda session, r: ("category", uuid.uuid4())
    # Default: category-level dedup collapses to the same identity as the
    # criterion-level check above (each criterion's own entity_id acts as
    # its "category"), so it never fires unless a test overrides this to
    # force a same-category-different-product collision.
    adapter.resolve_category_id.side_effect = lambda session, criterion_type, criterion_entity_id: criterion_entity_id
    synth_config = MagicMock()
    curve_store = MagicMock()
    curve_store.refresh.return_value = {}

    service = ChallengeService(
        task_repo=task_repo,
        log_repo=log_repo,
        adapter=adapter,
        synth_config=synth_config,
        model="test-model",
        api_key="test-key",
        curve_store=curve_store,
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


def _batch_all_five() -> list[dict]:
    return [
        _canned("llm_habit"),
        _canned("llm_discovery"),
        _canned("llm_basket"),
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


def test_generate_batch_persists_all_five_slots():
    service, task_repo, log_repo, adapter = _service_with_mocks()

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_five()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=len(CHALLENGE_SLOTS))

    assert len(created) == 5
    persisted_slots = [call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list]
    assert "llm_basket" in persisted_slots


def test_generate_batch_keeps_basket_when_anchor_category_matches_survival_slot():
    """The basket mechanic is independent from a category challenge: its
    spend-threshold criterion must not be removed just because its anchor
    product belongs to a category already used by another slot."""
    service, task_repo, log_repo, adapter = _service_with_mocks()
    shared_category = uuid.uuid4()
    habit_criterion = ("product", uuid.uuid4())
    basket_criterion = ("product", uuid.uuid4())

    def resolve(session, script_result):
        slot = script_result["challenge_slot"]
        if slot == "llm_habit":
            return habit_criterion
        if slot == "llm_basket":
            return basket_criterion
        return ("product", uuid.uuid4())

    def resolve_category(session, criterion_type, criterion_entity_id):
        if criterion_entity_id in {habit_criterion[1], basket_criterion[1]}:
            return shared_category
        return uuid.uuid4()

    adapter.resolve_criterion.side_effect = resolve
    adapter.resolve_category_id.side_effect = resolve_category

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_five()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        service.generate_batch(MagicMock(), uuid.uuid4(), count=5)

    persisted_slots = [
        call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list
    ]
    assert "llm_basket" in persisted_slots


def test_generate_batch_keeps_recurring_basket_when_target_repeats():
    """A stable weekly basket profile must not make the basket slot vanish
    after its previous task completes."""
    service, task_repo, log_repo, adapter = _service_with_mocks()
    previous_basket = ("product", uuid.uuid4())
    task_repo.get_last_criterion_per_slot.return_value = {"llm_basket": previous_basket}

    def resolve(session, script_result):
        if script_result["challenge_slot"] == "llm_basket":
            return previous_basket
        return ("product", uuid.uuid4())

    adapter.resolve_criterion.side_effect = resolve

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_five()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        service.generate_batch(MagicMock(), uuid.uuid4(), count=5)

    persisted_slots = [
        call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list
    ]
    assert "llm_basket" in persisted_slots


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


def test_generate_batch_no_slots_when_all_active():
    """No remaining challenge_slot for the user (CHALLENGE_SLOTS is a
    5-tuple as of the llm_basket slot) → early return, no synth call."""
    service, task_repo, log_repo, adapter = _service_with_mocks()
    task_repo.get_active_for_user.return_value = [MagicMock() for _ in range(5)]

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


def test_generate_batch_keeps_all_slots_when_criteria_collide():
    """A criterion collision is logged for diagnostics but must not reduce
    the user's active challenge count below five."""
    service, task_repo, log_repo, adapter = _service_with_mocks()

    same_criterion = ("category", uuid.uuid4())

    def resolve(session, script_result):
        if script_result["challenge_slot"] in ("llm_habit", "vibe"):
            return same_criterion
        return ("category", uuid.uuid4())

    adapter.resolve_criterion.side_effect = resolve

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_four()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    # 4 records total; llm_habit and vibe collide, but both are persisted.
    assert len(created) == 4
    assert log_repo.record.call_count == 4
    persisted_slots = [
        call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list
    ]
    assert persisted_slots.count("llm_habit") + persisted_slots.count("vibe") == 2
    assert "llm_discovery" in persisted_slots
    assert "generic" in persisted_slots


def test_generate_batch_keeps_slot_when_active_task_criterion_collides():
    """An active criterion collision must not remove a missing challenge
    slot; the slot-level invariant is more important than category variety."""
    service, task_repo, log_repo, adapter = _service_with_mocks()

    active_criterion = ("category", uuid.uuid4())
    active_task = MagicMock()
    active_task.challenge_slot = "spend_threshold"  # not one of this batch's slots
    active_task.criterion_type = active_criterion[0]
    active_task.criterion_entity_id = active_criterion[1]
    task_repo.get_active_for_user.return_value = [active_task]

    def resolve(session, script_result):
        if script_result["challenge_slot"] == "llm_habit":
            return active_criterion
        return ("category", uuid.uuid4())

    adapter.resolve_criterion.side_effect = resolve

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_four()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    assert len(created) == 4
    persisted_slots = [
        call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list
    ]
    assert "llm_habit" in persisted_slots


def test_generate_batch_keeps_generic_when_it_repeats_its_previous_cycle():
    """A repeated generic candidate is logged but still persisted so the
    user keeps five active tasks instead of seeing an empty slot."""
    service, task_repo, log_repo, adapter = _service_with_mocks()

    previous_criterion = ("category", uuid.uuid4())
    task_repo.get_last_criterion_per_slot.return_value = {"generic": previous_criterion}

    def resolve(session, script_result):
        if script_result["challenge_slot"] == "generic":
            return previous_criterion
        return ("category", uuid.uuid4())

    adapter.resolve_criterion.side_effect = resolve

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_four()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    assert len(created) == 4
    persisted_slots = [call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list]
    assert "generic" in persisted_slots


def test_generate_batch_fills_every_eligible_slot_regardless_of_count():
    """Regression test: an earlier design capped persistence at `count`
    slots, walking generate_challenge_for_user's FIXED result order
    (generic, llm_habit, llm_discovery, llm_basket, vibe) and stopping once
    `count` were persisted — silently filling the WRONG slots whenever the
    ones that actually needed filling weren't first in that order. Observed
    in production two ways: (1) several slots completing in one receipt
    each dispatched their own count=1 call, and all of them landed on the
    earlier slots, permanently starving `vibe` (last in the order); (2) an
    account that had never had an llm_basket task could never get one,
    because a count-sized replacement for its other 4 slots always
    preferred them over the never-yet-filled 5th. `count=1` here must still
    persist all 5 eligible slots — count no longer caps anything."""
    service, task_repo, log_repo, adapter = _service_with_mocks()

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_five()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=1)

    assert len(created) == 5
    persisted_slots = {call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list}
    assert persisted_slots == set(CHALLENGE_SLOTS)


def test_generate_batch_fills_missing_slot_even_when_it_was_never_previously_active():
    """An account that predates the llm_basket slot (its active tasks only
    ever occupied the other 4 slots) must still get llm_basket filled in —
    "eligible" only means "not currently active", not "was named in
    whatever just completed"."""
    service, task_repo, log_repo, adapter = _service_with_mocks()

    active_task = MagicMock()
    active_task.challenge_slot = "generic"
    active_task.criterion_type = None
    active_task.criterion_entity_id = None
    task_repo.get_active_for_user.return_value = [active_task]

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_five()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=1)

    persisted_slots = {call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list}
    assert "llm_basket" in persisted_slots
    assert "generic" not in persisted_slots
    assert len(created) == 4


def test_generate_batch_does_not_skip_non_generic_slots_that_repeat_their_own_previous_cycle():
    """Regression test: llm_habit/llm_discovery (survival-risk picks) and
    llm_basket/vibe must NOT be blocked from repeating their own previous
    target — a stable purchase habit or unchanging train-period pattern
    legitimately produces the same recommendation cycle after cycle, and
    treating that as a forbidden "repeat" made those slots permanently
    unfillable in production. Only `generic` is exempt from this exemption
    — see the sibling test above: an expired, uncompleted generic challenge
    leaves the risk ranking unchanged, so without the guard the identical
    category would repeat forever with zero new signal, which IS a bug for
    this slot specifically."""
    service, task_repo, log_repo, adapter = _service_with_mocks()

    llm_habits_previous_criterion = ("category", uuid.uuid4())
    task_repo.get_last_criterion_per_slot.return_value = {"llm_habit": llm_habits_previous_criterion}

    def resolve(session, script_result):
        if script_result["challenge_slot"] == "llm_habit":
            return llm_habits_previous_criterion
        return ("category", uuid.uuid4())

    adapter.resolve_criterion.side_effect = resolve

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_four()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    assert len(created) == 4
    persisted_slots = [call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list]
    assert "llm_habit" in persisted_slots


def test_generate_batch_refreshes_and_passes_curve_store_curves_to_generate_challenge_for_user():
    service, task_repo, log_repo, adapter = _service_with_mocks()
    service.curve_store.refresh.return_value = {"молоко": "sentinel-curve"}

    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return _batch_all_five()

    with patch("webx5.services.challenge.generate_challenge_for_user", side_effect=fake_generate), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        service.generate_batch(MagicMock(), uuid.uuid4(), count=5)

    service.curve_store.refresh.assert_called_once_with()
    assert captured["category_curves"] == {"молоко": "sentinel-curve"}
