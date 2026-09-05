# Challenge `llm_basket` Slot + Cross-Cycle Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 5th challenge slot (`llm_basket`, wrapping the existing weekly-basket-suggestion feature in an LLM challenge) and make challenges stop repeating their own previous cycle's exact target, per slot.

**Architecture:** `synth/challenges.py` gains one more slot in the pure-function generator (mirrors `build_vibe_prompt`'s shape). The web layer (`ChallengeAdapter`, `ChallengeService`) gains a new data source (`BasketRepository.suggest_items`, already used by `GET /basket/suggested`) and a new per-slot history check reusing the cross-slot duplicate-guard machinery already in `ChallengeService.generate_batch`.

**Tech Stack:** Python 3.12, FastAPI + SQLAlchemy 2.0, pytest, Poetry (`web/`) — plain `pytest`/`requirements.txt` (root, for `synth`/`tests/synth`).

**Spec:** `docs/superpowers/specs/2026-09-05-challenge-basket-slot-dedup-design.md`

## Global Constraints

- No new Alembic migration — `Task.challenge_slot`/`criterion_type`/`criterion_entity_id`/`issued_at` already exist; the invariant "max active tasks" auto-derives from `len(CHALLENGE_SLOTS)`, already wired that way in `ChallengeService.generate_batch`.
- `BasketRepository` is reused from the already-constructed instance in `web/src/webx5/core/basket.py` (`basket_repo`) — not re-instantiated in `core/challenges.py`.
- Cross-cycle dedup uses the SAME resolved-criterion comparison for all 5 slots, including `generic` — no separate index-tracking mechanism.
- A skipped (repeat/collision) slot is dropped for this cycle only, never retried with a different seed within the same call — matches the existing cross-slot collision behavior.
- Follow existing code style exactly: docstrings explain WHY not just WHAT (this codebase's established convention), `from __future__ import annotations` where the touched file already has it.

---

### Task 1: `TaskRepository.get_last_criterion_per_slot`

**Files:**
- Modify: `web/src/webx5/crud/task.py`

**Interfaces:**
- Produces: `TaskRepository.get_last_criterion_per_slot(session, user_id: uuid.UUID) -> dict[str, tuple[str, uuid.UUID]]` — consumed by Task 5 (`ChallengeService.generate_batch`).

**Note on testing:** `TaskRepository` currently has zero direct unit tests anywhere in this codebase (`web/tests/` has no `test_task.py` for `crud/task.py`) — every existing method is exercised indirectly through service-layer tests that mock `task_repo` entirely (see `web/tests/webx5/services/test_challenge_service.py`). This task follows that same established convention: no dedicated unit test here (writing one would mean introducing a new real-database or in-memory-SQLite test harness with no precedent in this file, out of scope for this task). Task 5 verifies the DEDUP BEHAVIOR this method enables by mocking its return value, same as every other `task_repo` method already is.

- [ ] **Step 1: Add the method**

In `web/src/webx5/crud/task.py`, add this method right after `count_active_for_user` (before `get_history_for_user`):

```python
    def get_last_criterion_per_slot(
        self, session: Session, user_id: uuid.UUID
    ) -> dict[str, tuple[str, uuid.UUID]]:
        """For each `challenge_slot` this user has EVER had a task in (any
        status — open, completed, expired, not just currently active),
        return the `(criterion_type, criterion_entity_id)` pair from that
        slot's most-recently-`issued_at` task. Used by
        `ChallengeService.generate_batch` to avoid a slot repeating its own
        previous cycle's exact target — a challenge that already ran once
        for "milk" shouldn't come back as "milk" again next month.

        Ordering by `(challenge_slot, issued_at DESC)` and keeping the
        first row seen per slot is a portable way to get "most recent per
        group" without a database-specific `DISTINCT ON`/window function.
        """
        rows = session.execute(
            select(Task.challenge_slot, Task.criterion_type, Task.criterion_entity_id)
            .where(Task.loyalty_card_id == user_id, Task.challenge_slot.is_not(None))
            .order_by(Task.challenge_slot, Task.issued_at.desc())
        ).all()

        result: dict[str, tuple[str, uuid.UUID]] = {}
        for slot, criterion_type, criterion_entity_id in rows:
            if slot not in result:
                result[slot] = (criterion_type, criterion_entity_id)
        return result
```

- [ ] **Step 2: Verify it imports and runs cleanly**

Run: `cd web && PYTHONPATH=/Users/dimonzhi/Documents/proga/x5hack python3 -m poetry run python -c "from webx5.crud.task import TaskRepository; print(TaskRepository.get_last_criterion_per_slot)"`
Expected: prints the bound method reference, no import errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/webx5/crud/task.py
git commit -m "$(cat <<'EOF'
feat: add TaskRepository.get_last_criterion_per_slot for cross-cycle dedup

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `build_basket_prompt`

**Files:**
- Modify: `synth/challenges.py`
- Test: `tests/synth/test_challenges.py`

**Interfaces:**
- Produces: `build_basket_prompt(profile, config, max_reward_rub, suggested_items: list[dict]) -> tuple[str, str]` — consumed by Task 3. `suggested_items` items have keys `"item"` (str), `"category"` (str), `"weekly_quantity"` (int).

- [ ] **Step 1: Write the failing test**

Add `build_basket_prompt` to the `from synth.challenges import (...)` block in `tests/synth/test_challenges.py`, alphabetically right before `build_category_expansion_challenge`:

```python
from synth.challenges import (
    CHALLENGE_SLOTS,
    GENERIC_CHALLENGES,
    PERSONAL_TARGET_QUANTITY,
    VIBE_CATEGORIES,
    backfill_target_sku,
    build_basket_prompt,
    build_category_expansion_challenge,
    build_personal_prompt,
    build_spend_threshold_challenge,
    build_vibe_prompt,
    compute_frequency_saturation,
    compute_receptiveness,
    estimate_max_reward_rub,
    find_sku_id_for_item,
    generate_challenge_for_user,
    item_action_description,
    load_profiles,
    parse_and_validate_challenge,
    pick_generic_challenge,
    pick_sku_in_category,
    pick_vibe_category,
    rewrite_descriptions_for_tracked_item,
    score_against_answer_key,
)
```

Add this test right after `test_build_vibe_prompt_restricts_to_theme_categories_and_mentions_reward_ceiling`:

```python
def test_build_basket_prompt_restricts_to_suggested_categories_and_mentions_reward_ceiling():
    profile = _profile("promo_hunter", seed=1)
    suggested = [
        {"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2},
        {"item": "Хлеб белый", "category": "хлеб и выпечка", "weekly_quantity": 1},
    ]
    system, user = build_basket_prompt(profile, _config, max_reward_rub=65.0, suggested_items=suggested)
    assert "Молоко 3.2%" in system
    assert "Хлеб белый" in system
    assert "65" in system
    assert "Молоко 3.2%" in user
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && python3 -m pytest tests/synth/test_challenges.py -k "build_basket_prompt" -v`
Expected: FAIL — `ImportError: cannot import name 'build_basket_prompt'`.

- [ ] **Step 3: Add `build_basket_prompt`**

In `synth/challenges.py`, insert right after `build_vibe_prompt`:

```python
def build_basket_prompt(
    profile: dict, config: SynthConfig, max_reward_rub: float, suggested_items: list[dict]
) -> tuple[str, str]:
    """Wraps the user's own deterministic weekly-purchase-frequency list
    (`suggested_items` — from `BasketRepository.suggest_items`, the same
    source `GET /basket/suggested` uses) into a challenge encouraging them
    to buy their usual weekly basket. `target_categories` must stay within
    the categories already present in `suggested_items` — enforced by
    `parse_and_validate_challenge`'s `allowed_categories`, not by this
    function. The caller (`generate_challenge_for_user`) never calls this
    with an empty `suggested_items` — there is nothing to wrap into a
    challenge for a user with no purchase history yet, so that case is
    handled as a cold-start fallback before this function is ever reached."""
    summary = summarize_purchase_pattern(profile, config)
    items_text = "; ".join(
        f"{item['item']} ({item['category']}, ~{item['weekly_quantity']}/нед.)" for item in suggested_items
    )

    system = (
        "Ты — модуль персональных рекомендаций программы лояльности X5 "
        "(Пятёрочка/Перекрёсток/Чижик). У пользователя есть обычная "
        "недельная корзина — товары, которые он покупает регулярно. "
        "Предложи ОДИН челлендж, поощряющий купить что-то из этой обычной "
        "корзины на этой неделе (например, за нужное количество или всю "
        "корзину целиком).\n\n"
        f"Список обычных недельных покупок: {items_text}\n"
        "target_categories обязаны быть подмножеством категорий из этого "
        "списка — другие категории использовать нельзя.\n"
        f"reward_rub не должен превышать {max_reward_rub:.0f} ₽ — это "
        "ограничение по марже конкретно этого пользователя.\n\n"
        "Ответь СТРОГО в виде одного JSON-объекта, без текста вне JSON:\n"
        '{"challenge_title": string, "description": string, '
        '"target_categories": [string, ...], "mechanic": string, '
        '"reward_rub": number, "reasoning": string}'
    )

    user = (
        f"Сеть: {profile['chain']}\n"
        f"Обычная недельная корзина: {items_text}\n"
        f"Чеков за 90 дней (train-период): {summary['n_receipts_90d_train']}\n"
        f"Средний чек: {summary['mean_receipt_total_rub']:.0f} ₽\n"
    )
    return system, user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && python3 -m pytest tests/synth/test_challenges.py -k "build_basket_prompt" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add synth/challenges.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: add build_basket_prompt for the themed weekly-basket challenge slot

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire `llm_basket` into `CHALLENGE_SLOTS` + `generate_challenge_for_user`

**Files:**
- Modify: `synth/challenges.py`
- Test: `tests/synth/test_challenges.py`

**Interfaces:**
- Consumes: `build_basket_prompt` (Task 2).
- Produces: `CHALLENGE_SLOTS = ("llm_habit", "llm_discovery", "llm_basket", "generic", "vibe")` (5-tuple); `generate_challenge_for_user` reads `profile.get("suggested_basket_items")` (list of dicts, may be absent/empty) — consumed by Task 4 (`ChallengeAdapter.build_profile` populates this key) and Task 5 (`ChallengeService.generate_batch`, unchanged call site).

- [ ] **Step 1: Update the test file's constant comment expectations and add new tests**

In `tests/synth/test_challenges.py`, replace `test_generate_challenge_for_user_always_returns_four_slots_regardless_of_pattern_strength` with:

```python
def test_generate_challenge_for_user_always_returns_five_slots_regardless_of_pattern_strength(monkeypatch):
    """The receptiveness/saturation gates are gone from the live routing
    function — these three profile classes used to hit three DIFFERENT old
    branches. Now all three get the exact same 5-slot shape. `llm_basket`
    falls back to generic here because `_profile()` never sets
    `suggested_basket_items` on the returned profile dict (cold start)."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter should not be called under dry_run")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    for generation_class in ("bakes_on_weekends", "one_off_no_pattern", "already_optimal_no_challenge"):
        profile = _profile(generation_class, seed=1)
        results = generate_challenge_for_user(profile, _config, model="fake/model", dry_run=True)
        assert len(results) == len(CHALLENGE_SLOTS)
        by_slot = _by_slot(results)
        assert set(by_slot) == set(CHALLENGE_SLOTS)
        assert by_slot["llm_habit"]["path"] == "personal_dry_run"
        assert by_slot["llm_discovery"]["path"] == "personal_dry_run"
        assert by_slot["generic"]["path"] == "generic"
        assert by_slot["vibe"]["path"] == "personal_dry_run"
        assert by_slot["llm_basket"]["path"] == "generic_fallback"
```

Add these new tests right after it:

```python
def test_generate_challenge_for_user_llm_basket_personal_path_with_mocked_llm(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)
    profile = {**profile, "suggested_basket_items": [
        {"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2},
    ]}

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return json.dumps({
            "challenge_title": "Собери свою обычную корзину",
            "description": "desc",
            "target_categories": ["молочные продукты и яйца"],
            "mechanic": "бонус",
            "reward_rub": 40,
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    basket_result = _by_slot(results)["llm_basket"]
    assert basket_result["path"] == "personal"
    assert basket_result["target_categories"] == ["молочные продукты и яйца"]


def test_generate_challenge_for_user_llm_basket_falls_back_when_llm_picks_category_outside_suggested(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)
    profile = {**profile, "suggested_basket_items": [
        {"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2},
    ]}

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return json.dumps({
            "challenge_title": "Скидка на бакалею",
            "description": "desc",
            "target_categories": ["бакалея"],
            "mechanic": "скидка",
            "reward_rub": 30,
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    basket_result = _by_slot(results)["llm_basket"]
    assert basket_result["path"] == "generic_fallback"
    assert "outside allowed set" in basket_result["error"]


def test_generate_challenge_for_user_llm_basket_falls_back_without_calling_llm_when_no_suggestions(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter should not be called with no suggested_basket_items")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    profile = _profile("bakes_on_weekends", seed=4)
    # no suggested_basket_items key at all — same as a brand-new user
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    basket_result = _by_slot(results)["llm_basket"]
    assert basket_result["path"] == "generic_fallback"
```

Update `test_generate_challenge_for_user_all_llm_fallbacks_get_distinct_generic_offers` (it already uses `len(CHALLENGE_SLOTS)` dynamically, so only the docstring/comment needs a mental note — no code change required there; leave it as-is, it will now assert 5 instead of 4 automatically).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && python3 -m pytest tests/synth/test_challenges.py -k "generate_challenge_for_user" -v`
Expected: FAIL — `llm_basket` isn't a real slot yet, `set(by_slot) == set(CHALLENGE_SLOTS)` and the new tests' lookups on `_by_slot(results)["llm_basket"]` raise `KeyError`.

- [ ] **Step 3: Update `CHALLENGE_SLOTS` and `generate_challenge_for_user`**

In `synth/challenges.py`, update the comment and constant:

```python
# The five independent challenge slots every user gets, one attempt each,
# unconditionally — no receptiveness/saturation gate decides who gets
# personalization any more (see `compute_receptiveness`/
# `compute_frequency_saturation`, still used by `synth/simulation.py`'s
# offline effect model, but no longer by `generate_challenge_for_user`).
CHALLENGE_SLOTS = ("llm_habit", "llm_discovery", "llm_basket", "generic", "vibe")
```

Update `generate_challenge_for_user`'s docstring (first paragraph) to say "five" instead of "four" and list `llm_basket`:

```python
    """Route one profile to exactly `len(CHALLENGE_SLOTS)` records — one per
    slot (`llm_habit`, `llm_discovery`, `llm_basket`, `generic`, `vibe`) —
    for EVERY user, regardless of purchase-pattern strength or frequency.
    There is no saturation/receptiveness gate here any more: a thin/noisy
    purchase history degrades gracefully through the LLM prompt
    (`summarize_purchase_pattern` already renders "—" for empty fields)
    rather than being rejected upfront.
```

(Keep the rest of the docstring's existing paragraphs about `llm_habit`/`llm_discovery`/`generic`/`vibe` as-is; add one new paragraph right after the `vibe` paragraph, before "Any LLM-backed slot whose call/validation fails..."):

```python
    `llm_basket` wraps the user's own deterministic weekly-purchase-
    frequency list (`profile.get("suggested_basket_items")`, populated by
    the web layer from `BasketRepository.suggest_items` — see
    `ChallengeAdapter._suggested_basket_items`) into a challenge via
    `build_basket_prompt`. If there are no suggested items (new user, no
    purchase history), this slot never calls the LLM at all — it falls
    straight to a generic offer, the same way the old deterministic
    builders returned `None` on insufficient history.
```

Add the new slot's code, right after the `vibe` slot block (at the end of the function, before `return results`):

```python
    # slot: llm_basket
    suggested_items = profile.get("suggested_basket_items") or []
    if not suggested_items:
        results.append(_generic(
            "llm_basket", "generic_fallback",
            error="no suggested weekly-basket items — no purchase history to build from",
        ))
    else:
        system, user_msg = build_basket_prompt(profile, config, max_reward, suggested_items)
        allowed_categories = {item["category"] for item in suggested_items}
        _run_llm_slot("llm_basket", system, user_msg, allowed_categories=allowed_categories)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && python3 -m pytest tests/synth/test_challenges.py -v`
Expected: all PASS (full file — confirms retained functions' own tests plus all `generate_challenge_for_user` tests, old and new).

- [ ] **Step 5: Run the offline simulation's own test suite to confirm it's unaffected**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && python3 -m pytest tests/synth/test_simulation.py -v`
Expected: all PASS, unchanged — `synth/simulation.py` isn't touched by this task.

- [ ] **Step 6: Commit**

```bash
git add synth/challenges.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: add llm_basket as a 5th unconditional challenge slot

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `ChallengeAdapter` — `basket_repo` DI + `suggested_basket_items`

**Files:**
- Modify: `web/src/webx5/services/challenge_adapter.py`
- Test: `web/tests/webx5/services/test_challenge_adapter.py`

**Interfaces:**
- Produces: `ChallengeAdapter.__init__(self, task_repo: TaskRepository, basket_repo: BasketRepository)` (constructor signature CHANGES — new required param); `ChallengeAdapter._suggested_basket_items(self, session, user_id) -> list[dict]`; `build_profile(...)`'s returned dict gains a `"suggested_basket_items"` key — consumed by Task 3's `generate_challenge_for_user` (already reads `profile.get("suggested_basket_items")`) via `ChallengeService.generate_batch` (no call-site change needed there). Consumed by Task 6 (`core/challenges.py`, new constructor arg).

- [ ] **Step 1: Write the failing tests**

In `web/tests/webx5/services/test_challenge_adapter.py`, update the `_adapter()` helper and add new tests:

```python
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

from synth.challenges import VIBE_CATEGORIES
from webx5.services.challenge_adapter import ChallengeAdapter


def _adapter():
    return ChallengeAdapter(task_repo=MagicMock(), basket_repo=MagicMock())
```

(Every existing test in this file calls `_adapter()` with no further changes needed — only the helper itself changes.)

Add these two tests at the end of the file:

```python
def test_suggested_basket_items_converts_product_quantity_pairs_to_plain_dicts():
    adapter = _adapter()
    product = MagicMock()
    product.name = "Молоко 3.2%"
    product.category.name = "молочные продукты и яйца"
    adapter.basket_repo.suggest_items.return_value = [(product, 2)]

    result = adapter._suggested_basket_items(MagicMock(), uuid.uuid4())

    assert result == [{"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2}]


def test_suggested_basket_items_empty_when_no_suggestions():
    adapter = _adapter()
    adapter.basket_repo.suggest_items.return_value = []

    result = adapter._suggested_basket_items(MagicMock(), uuid.uuid4())

    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && PYTHONPATH=/Users/dimonzhi/Documents/proga/x5hack python3 -m poetry run pytest tests/webx5/services/test_challenge_adapter.py -v`
Expected: FAIL — `TypeError: ChallengeAdapter.__init__() missing 1 required positional argument: 'basket_repo'` on every test (since `_adapter()` itself now fails first).

- [ ] **Step 3: Add `basket_repo` DI and `_suggested_basket_items`**

In `web/src/webx5/services/challenge_adapter.py`, add the import:

```python
from webx5.crud.basket import BasketRepository
```

Change the constructor:

```python
class ChallengeAdapter:
    def __init__(self, task_repo: TaskRepository, basket_repo: BasketRepository) -> None:
        self.task_repo = task_repo
        self.basket_repo = basket_repo
```

Add this method right after `_resolve_vibe_category` (before `build_profile`):

```python
    # ------- weekly-basket suggestion → plain-dict context -------
    def _suggested_basket_items(self, session: Session, user_id: uuid.UUID) -> list[dict]:
        """Convert `BasketRepository.suggest_items`'s `(Product, quantity)`
        pairs into the plain-dict shape `synth.challenges.build_basket_prompt`
        expects — keeps `synth.challenges` free of any ORM dependency, same
        reason `build_profile` converts receipts/products to dicts too."""
        suggested = self.basket_repo.suggest_items(session, user_id)
        return [
            {"item": product.name, "category": product.category.name, "weekly_quantity": qty}
            for product, qty in suggested
        ]
```

In `build_profile`, right after the `vibe_category = self._resolve_vibe_category(session, user)` line, add:

```python
        suggested_basket_items = self._suggested_basket_items(session, user_id)
```

And add the key to the returned dict (right after `"vibe_category": vibe_category,`):

```python
            "suggested_basket_items": suggested_basket_items,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && PYTHONPATH=/Users/dimonzhi/Documents/proga/x5hack python3 -m poetry run pytest tests/webx5/services/test_challenge_adapter.py -v`
Expected: PASS (all tests, old and new — 6 total).

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/services/challenge_adapter.py web/tests/webx5/services/test_challenge_adapter.py
git commit -m "$(cat <<'EOF'
feat: wire BasketRepository into ChallengeAdapter for the llm_basket slot

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `ChallengeService.generate_batch` — cross-cycle dedup

**Files:**
- Modify: `web/src/webx5/services/challenge.py`
- Test: `web/tests/webx5/services/test_challenge_service.py`

**Interfaces:**
- Consumes: `TaskRepository.get_last_criterion_per_slot` (Task 1).
- Produces: nothing new consumed by later tasks — this is the last behavioral task.

- [ ] **Step 1: Update `_service_with_mocks()` and add new tests**

In `web/tests/webx5/services/test_challenge_service.py`, add one line to `_service_with_mocks()` right after `task_repo.get_active_for_user.return_value = []`:

```python
def _service_with_mocks():
    task_repo = MagicMock()
    task_repo.get_active_for_user.return_value = []
    task_repo.get_last_criterion_per_slot.return_value = {}
    log_repo = MagicMock()
    ...
```

(Rest of the function unchanged.)

Also update `_batch_all_four` calls conceptually — no rename needed, it still returns 4 canned records; the tests below add specific new ones on top, so leave `_batch_all_four()` as-is (it's just a fixture name, not a count assertion).

Add these two tests at the end of the file:

```python
def test_generate_batch_skips_slot_that_repeats_its_own_previous_cycle():
    """If llm_habit's newly-resolved criterion is identical to what llm_habit
    itself resolved to last cycle (from task history), skip persisting it —
    same target as last time, not a fresh challenge."""
    service, task_repo, log_repo, adapter = _service_with_mocks()

    previous_criterion = ("category", uuid.uuid4())
    task_repo.get_last_criterion_per_slot.return_value = {"llm_habit": previous_criterion}

    def resolve(session, script_result):
        if script_result["challenge_slot"] == "llm_habit":
            return previous_criterion
        return ("category", uuid.uuid4())

    adapter.resolve_criterion.side_effect = resolve

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_four()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    assert len(created) == 3
    persisted_slots = [call.args[2]["challenge_slot"] for call in adapter.persist_challenge.call_args_list]
    assert "llm_habit" not in persisted_slots


def test_generate_batch_does_not_skip_when_criterion_matches_a_different_slots_history():
    """The repeat check is per-slot, not global — a previous cycle's
    llm_habit criterion showing up as history must not block a DIFFERENT
    slot in this cycle from using a fresh (non-matching) criterion of its
    own."""
    service, task_repo, log_repo, adapter = _service_with_mocks()

    previous_criterion = ("category", uuid.uuid4())
    task_repo.get_last_criterion_per_slot.return_value = {"llm_habit": previous_criterion}
    # default resolve_criterion.side_effect (from _service_with_mocks) gives
    # every slot a fresh uuid4() — none will match previous_criterion

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_four()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    assert len(created) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && PYTHONPATH=/Users/dimonzhi/Documents/proga/x5hack python3 -m poetry run pytest tests/webx5/services/test_challenge_service.py -v`
Expected: FAIL — `AttributeError` or wrong count on the two new tests (the repeat check doesn't exist yet, so `llm_habit` gets persisted normally in the first new test, making `len(created) == 4` not `3`).

- [ ] **Step 3: Add the cross-cycle dedup check**

In `web/src/webx5/services/challenge.py`, update the module docstring:

```python
"""High-level challenge service: batch generation via `synth.challenges` +
resolving current-active list for API.

Synth API (single call → list[dict] of exactly 5 records, each with
`challenge_slot ∈ {'llm_habit', 'llm_discovery', 'llm_basket', 'generic',
'vibe'}`). De-dup with active tasks is done via `task.challenge_slot`.
"""
```

Update `generate_batch`'s docstring (the "no more than 4" line):

```python
        """Generate up to `count` new tasks for `user_id`, filling missing challenge slots.
        Respects invariant "no more than 5 active tasks" (FR-001).

        Synth API: one call → list[dict] with exactly 5 records.
        We filter the returned records by challenge_slot to skip slots the user
        already has active, then persist up to `count` of the remaining.
        """
```

Right after the `existing_criteria` block (after its closing `}`), add:

```python
        # Cross-cycle duplicate guard: a slot's own previous cycle's target
        # shouldn't come back unchanged — e.g. llm_habit shouldn't propose
        # "milk" again right after a "milk" llm_habit challenge already ran.
        # Keyed by challenge_slot (not by user overall), and independent of
        # `existing_criteria` above (which only guards THIS batch/active
        # tasks against each other, not against history).
        previous_by_slot = self.task_repo.get_last_criterion_per_slot(session, user_id)
```

In the main loop, right after the `criterion = self.adapter.resolve_criterion(session, script_result)` block's `try/except` (i.e. right after the code that currently has the `if criterion in existing_criteria:` check), add the new check BEFORE it:

```python
            if previous_by_slot.get(slot) == criterion:
                logger.info(
                    "generate_batch.repeats_previous_cycle_skip",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    criterion_type=criterion[0],
                    criterion_entity_id=str(criterion[1]),
                )
                continue

            if criterion in existing_criteria:
                logger.info(
                    "generate_batch.duplicate_criterion_skip",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    criterion_type=criterion[0],
                    criterion_entity_id=str(criterion[1]),
                )
                continue
```

(The second `if` block already exists — you're inserting the new `if previous_by_slot.get(slot) == criterion:` block immediately before it, not replacing anything.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && PYTHONPATH=/Users/dimonzhi/Documents/proga/x5hack python3 -m poetry run pytest tests/webx5/services/test_challenge_service.py -v`
Expected: all PASS (9 tests: 7 previous + 2 new).

- [ ] **Step 5: Run the full web test suite for a regression check**

Run: `cd web && PYTHONPATH=/Users/dimonzhi/Documents/proga/x5hack python3 -m poetry run pytest -v`
Expected: same known pre-existing failures as baseline (2 need Postgres, 2 fail on the `SYNTH_CONFIG_PATH=/dev/null` test-setup bug in `test_challenges.py`), zero NEW failures.

- [ ] **Step 6: Commit**

```bash
git add web/src/webx5/services/challenge.py web/tests/webx5/services/test_challenge_service.py
git commit -m "$(cat <<'EOF'
feat: skip a challenge slot that repeats its own previous cycle's target

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `core/challenges.py` — wire `basket_repo` into `ChallengeAdapter`

**Files:**
- Modify: `web/src/webx5/core/challenges.py`

**Interfaces:**
- Consumes: `ChallengeAdapter.__init__(task_repo, basket_repo)` (Task 4); `basket_repo` (the module-level instance already constructed in `web/src/webx5/core/basket.py`).

- [ ] **Step 1: Wire the shared `basket_repo` instance**

In `web/src/webx5/core/challenges.py`, add the import (alongside the existing `from webx5.crud.task import TaskRepository` line):

```python
from webx5.core.basket import basket_repo
```

Change the adapter construction:

```python
# --- adapter (ORM ↔ synth dict-profile) ---
challenge_adapter = ChallengeAdapter(task_repo=task_repo, basket_repo=basket_repo)
```

- [ ] **Step 2: Verify the module still imports cleanly (no circular import)**

Run: `cd web && PYTHONPATH=/Users/dimonzhi/Documents/proga/x5hack python3 -m poetry run python -c "import webx5.core.challenges; print('ok')"`
Expected: prints `ok`. If this raises `ImportError`/`ImportError: cannot import name ... (most likely due to a circular import)`, STOP — do not work around it by moving the import inside a function; report back, since `core/basket.py` genuinely shouldn't import anything from `core/challenges.py`'s dependency chain (verified during planning via `grep -rn "^from webx5" web/src/webx5/services/basket_assistant.py web/src/webx5/core/points.py web/src/webx5/core/purchases.py web/src/webx5/crud/basket.py web/src/webx5/crud/store.py | grep -i challenge` — no hits), so a circular import here would mean something changed since the plan was written and needs investigation, not a workaround.

- [ ] **Step 3: Run the full web test suite for a regression check**

Run: `cd web && PYTHONPATH=/Users/dimonzhi/Documents/proga/x5hack python3 -m poetry run pytest -v`
Expected: same known pre-existing failures as baseline, zero new.

- [ ] **Step 4: Commit**

```bash
git add web/src/webx5/core/challenges.py
git commit -m "$(cat <<'EOF'
feat: wire basket_repo into ChallengeAdapter's DI construction

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Documentation — BACKLOG.md follow-up note

**Files:**
- Modify: `BACKLOG.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Add the entry**

Read the current `BACKLOG.md`'s existing "## Персональные челленджи: ..." sections (added in the prior 4-slot redesign) to match heading level and tone, then add a new `##`-level section:

```markdown
## Персональные челленджи: 5-й слот llm_basket (2026-09-05)

`CHALLENGE_SLOTS` вырос до 5 (`llm_habit`, `llm_discovery`, `llm_basket`,
`generic`, `vibe`) — добавлен `llm_basket`, оборачивающий существующую фичу
"предложенная корзина на неделю" (`BasketRepository.suggest_items`) в LLM-
челлендж. Инвариант "макс. активных заданий" вырос до 5 автоматически (код
уже вычислял его как `len(CHALLENGE_SLOTS)`, без хардкода).

Мобильный экран заданий рассчитан на переменное число карточек (список,
без хардкода на 3/4) — но 5 карточек одновременно ещё не проверялись вживую;
стоит визуально проверить экран при первой возможности, как и было
рекомендовано при переходе 3→4.

Добавлен дедуп между последовательными циклами генерации: если резолвленный
критерий слота совпадает с тем, что этот же слот выдавал в прошлый раз
(`TaskRepository.get_last_criterion_per_slot`), слот пропускается в этом
цикле — не пытается перегенерироваться с другим seed, просто ждёт
следующего триггера. См. `docs/superpowers/specs/2026-09-05-challenge-basket-slot-dedup-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: record llm_basket slot and cross-cycle dedup in BACKLOG.md

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

## Manual verification (not automated — do after Task 7)

- [ ] `cd /Users/dimonzhi/Documents/proga/x5hack && python3 -m pytest tests/synth -v` — full synth suite green (same one known pre-existing `test_config.py` failure, nothing new).
- [ ] `cd web && PYTHONPATH=/Users/dimonzhi/Documents/proga/x5hack python3 -m poetry run pytest -v` — full web suite green (same known pre-existing baseline, nothing new).
- [ ] `grep -rn "len(CHALLENGE_SLOTS)\|CHALLENGE_SLOTS" web/src/webx5/services/challenge.py` — confirm no stray hardcoded `4` or `5` snuck back in anywhere in that file.
- [ ] Rebuild and restart the `web`/`worker` Docker containers (`docker compose build web worker && docker compose up -d web worker`) and trigger a fresh generation for a test account with purchase history — confirm 5 tasks appear with slots `llm_habit`, `llm_discovery`, `llm_basket`, `generic`, `vibe`, and that `llm_basket`'s card references items from that account's actual weekly-frequent purchases (via `GET /basket/suggested` on the same account, for comparison).
