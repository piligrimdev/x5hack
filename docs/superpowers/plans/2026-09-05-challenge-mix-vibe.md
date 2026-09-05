# Challenge Mix + Vibe Category Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current 3-slot challenge mix (`llm`, `spend_threshold`, `category_expansion`, gated behind receptiveness/saturation checks) with a fixed 4-slot mix — `llm_habit`, `llm_discovery`, `generic`, `vibe` — issued identically to every user, plus a new monthly "vibe" theme stored per user.

**Architecture:** All changes land in two existing packages: the pure offline generator `synth/challenges.py` (adds `VIBE_CATEGORIES`, `pick_vibe_category`, `build_vibe_prompt`, rewrites `generate_challenge_for_user`) and the live web service `web/src/webx5` (new `users.vibe_category`/`vibe_month` columns, `ChallengeAdapter` resolves/persists the theme, `ChallengeService`/schemas/tasks drop the 3→4 magic numbers and the retired `saturated` empty-reason). `synth/simulation.py` is untouched — it keeps using `compute_receptiveness`/`compute_frequency_saturation`/`build_spend_threshold_challenge`/`build_category_expansion_challenge` directly for its own offline effect model, independent of the live routing function.

**Tech Stack:** Python 3.12, FastAPI + SQLAlchemy 2.0 (`Mapped`/`mapped_column`) + Alembic, Celery, pytest, Poetry (web/) — plain `pytest`/`requirements.txt` (root, for `synth`/`tests/synth`).

**Spec:** `docs/superpowers/specs/2026-09-05-challenge-mix-vibe-design.md`

## Global Constraints

- No new Alembic CHECK-constraint on `vibe_category` — the theme list is application behavior, not a schema invariant (same reasoning already applied to `task.challenge_slot`).
- `synth/simulation.py` and its tests (`tests/synth/test_simulation.py`) are NOT touched by this plan — they consume the retained functions directly and are unaffected.
- `synth/challenges.py`'s `compute_receptiveness`, `compute_frequency_saturation`, `build_spend_threshold_challenge`, `build_category_expansion_challenge` are NOT deleted — only their call sites inside `generate_challenge_for_user` are removed. Their own dedicated unit tests in `tests/synth/test_challenges.py` stay unchanged.
- Root-level tests (`tests/synth/...`) run via plain `pytest` from the repo root (cwd matters — `config/synth_schema.yaml` is loaded by relative path). Web tests (`web/tests/...`) run via `poetry run pytest` from inside `web/`.
- Follow existing code style exactly: `from __future__ import annotations` where the touched file already has it, `Mapped[...]`/`mapped_column(...)` SQLAlchemy 2.0 style, structlog for web-layer logging (no new logging needed here beyond what already exists).

---

### Task 1: `users.vibe_category` / `users.vibe_month` — migration + entity

**Files:**
- Modify: `web/src/webx5/entities/user.py`
- Create: `web/alembic/versions/h6c7d8e9f0a1_add_user_vibe_category.py`
- Test: `web/tests/webx5/entities/test_user.py` (new)

**Interfaces:**
- Produces: `User.vibe_category: str | None`, `User.vibe_month: datetime.date | None` — consumed by Task 7 (`ChallengeAdapter._resolve_vibe_category`).

- [ ] **Step 1: Write the failing test**

Create `web/tests/webx5/entities/test_user.py` (create `web/tests/webx5/entities/__init__.py` too, empty, if the directory doesn't already have one):

```python
from __future__ import annotations

from datetime import date

from webx5.entities.user import User


def test_user_vibe_columns_default_to_none():
    user = User(phone="+70000000000")
    assert user.vibe_category is None
    assert user.vibe_month is None


def test_user_vibe_columns_are_settable():
    user = User(phone="+70000000001")
    user.vibe_category = "Здоровье и лёгкость"
    user.vibe_month = date(2026, 9, 1)
    assert user.vibe_category == "Здоровье и лёгкость"
    assert user.vibe_month == date(2026, 9, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && poetry run pytest tests/webx5/entities/test_user.py -v`
Expected: FAIL — `AttributeError: 'User' object has no attribute 'vibe_category'` (or similar, since the columns don't exist yet).

- [ ] **Step 3: Add the columns to `User`**

In `web/src/webx5/entities/user.py`, replace the full file with:

```python
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from webx5.entities.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    loyalty_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    vibe_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vibe_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && poetry run pytest tests/webx5/entities/test_user.py -v`
Expected: PASS

- [ ] **Step 5: Write the Alembic migration**

Create `web/alembic/versions/h6c7d8e9f0a1_add_user_vibe_category.py`:

```python
"""add vibe_category and vibe_month to users

Revision ID: h6c7d8e9f0a1
Revises: g5b6c7d8e9f0
Create Date: 2026-09-05 12:00:00.000000

Each user is assigned a "vibe" theme for the calendar month (e.g. "Здоровье
и лёгкость") that constrains one of their four challenge slots
(synth.challenges.VIBE_CATEGORIES). Random for now (no selection UI yet) —
these two columns exist so a future manual-selection feature can simply
overwrite them instead of requiring a new migration.
"""
import sqlalchemy as sa
from alembic import op

revision = "h6c7d8e9f0a1"
down_revision = "g5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("vibe_category", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("vibe_month", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "vibe_month")
    op.drop_column("users", "vibe_category")
```

- [ ] **Step 6: Verify the migration chain is consistent**

Run: `cd web && poetry run alembic heads`
Expected: prints exactly one head — `h6c7d8e9f0a1 (head)`. If it prints two heads or errors, `down_revision` doesn't match the real current head; run `poetry run alembic history` and fix `down_revision` to match.

- [ ] **Step 7: Commit**

```bash
git add web/src/webx5/entities/user.py web/alembic/versions/h6c7d8e9f0a1_add_user_vibe_category.py web/tests/webx5/entities/
git commit -m "$(cat <<'EOF'
feat: add vibe_category/vibe_month columns to users

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

### Task 2: `VIBE_CATEGORIES` + `pick_vibe_category`

**Files:**
- Modify: `synth/challenges.py`
- Test: `tests/synth/test_challenges.py`

**Interfaces:**
- Produces: `VIBE_CATEGORIES: dict[str, list[str]]` (6 themes, module-level constant), `pick_vibe_category(user_id: str, month_key: str) -> str` — consumed by Task 6 (`generate_challenge_for_user`) and Task 7 (`ChallengeAdapter._resolve_vibe_category`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/synth/test_challenges.py` (near the top-level constants tests, e.g. right after `test_generic_challenges_never_target_a_forbidden_category`):

```python
def test_vibe_categories_partition_all_non_forbidden_categories_without_overlap():
    all_vibe_categories = [c for cats in VIBE_CATEGORIES.values() for c in cats]
    assert len(all_vibe_categories) == len(set(all_vibe_categories))
    expected = {c.name for c in _config.categories} - set(_config.forbidden_categories)
    assert set(all_vibe_categories) == expected


def test_pick_vibe_category_is_deterministic():
    assert pick_vibe_category("user-1", "2026-09") == pick_vibe_category("user-1", "2026-09")


def test_pick_vibe_category_varies_by_user():
    themes = {pick_vibe_category(f"user-{i}", "2026-09") for i in range(30)}
    assert len(themes) > 1


def test_pick_vibe_category_can_change_across_months():
    themes = {pick_vibe_category("user-1", f"2026-{m:02d}") for m in range(1, 13)}
    assert len(themes) > 1


def test_pick_vibe_category_always_returns_a_known_theme():
    assert pick_vibe_category("user-1", "2026-09") in VIBE_CATEGORIES
```

Add `VIBE_CATEGORIES` and `pick_vibe_category` to the `from synth.challenges import (...)` block at the top of the file (alphabetical, matching the existing style):

```python
from synth.challenges import (
    GENERIC_CHALLENGES,
    PERSONAL_CHALLENGE_SLOTS,
    PERSONAL_TARGET_QUANTITY,
    VIBE_CATEGORIES,
    backfill_target_sku,
    build_category_expansion_challenge,
    build_personal_prompt,
    build_spend_threshold_challenge,
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

(`PERSONAL_CHALLENGE_SLOTS` is renamed to `CHALLENGE_SLOTS` in Task 6 — leave the import as `PERSONAL_CHALLENGE_SLOTS` for now, this task doesn't touch it.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/synth/test_challenges.py -k "vibe_categor or pick_vibe" -v`
Expected: FAIL — `ImportError: cannot import name 'VIBE_CATEGORIES'` (or `'pick_vibe_category'`).

- [ ] **Step 3: Add the constant and function to `synth/challenges.py`**

Insert right after the `GENERIC_CHALLENGES` list (after its closing `]` on line 98, before `_REQUIRED_FIELDS` on line 100):

```python
# Partition of every non-forbidden catalog category into 6 monthly "vibe"
# themes. A user is assigned exactly one theme per calendar month
# (`pick_vibe_category` / `ChallengeAdapter._resolve_vibe_category`), and
# their "vibe" challenge slot is constrained to this theme's categories —
# see `build_vibe_prompt`. No overlap by design (checked by
# `test_vibe_categories_partition_all_non_forbidden_categories_without_overlap`),
# though nothing technically requires that if the list changes later.
VIBE_CATEGORIES: dict[str, list[str]] = {
    "Здоровье и лёгкость": [
        "молочные продукты и яйца", "овощи", "фрукты",
        "мясо и птица", "рыба и морепродукты", "орехи и сухофрукты",
    ],
    "Экономия и запасы": [
        "бакалея", "консервация", "масла и жиры", "соусы и приправы",
    ],
    "Побаловать себя": [
        "кондитерка", "сладости и снеки", "напитки",
    ],
    "Уют и порядок дома": [
        "товары для дома", "бытовая химия", "личная гигиена",
    ],
    "Быстро и просто": [
        "готовая еда", "хлеб и выпечка", "заморозка",
    ],
    "Забота о питомце": [
        "товары для животных",
    ],
}
```

Add `pick_vibe_category` right after `_hash_index` (after line 178, before `pick_sku_in_category`):

```python
def pick_vibe_category(user_id: str, month_key: str) -> str:
    """Deterministic pick of this user's "vibe" theme for `month_key`
    (`"YYYY-MM"`) — same style as `pick_generic_challenge`/
    `pick_sku_in_category`: a hash of `user_id` + `month_key`, not
    `random`, so the same user always gets the same theme for a given
    month without needing anything persisted. The web layer persists the
    result anyway (`ChallengeAdapter._resolve_vibe_category`), as a seat
    for a future manual-selection feature that would overwrite it."""
    names = list(VIBE_CATEGORIES)
    return names[_hash_index(f"{user_id}:vibe:{month_key}", len(names))]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/synth/test_challenges.py -k "vibe_categor or pick_vibe" -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full synth test suite to check nothing else broke**

Run: `pytest tests/synth/test_challenges.py -v`
Expected: all PASS (no regressions — this task only added code, didn't remove/rename anything used elsewhere yet).

- [ ] **Step 6: Commit**

```bash
git add synth/challenges.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: add VIBE_CATEGORIES theme partition and pick_vibe_category

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

### Task 3: `parse_and_validate_challenge` — `allowed_categories` param

**Files:**
- Modify: `synth/challenges.py`
- Test: `tests/synth/test_challenges.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `parse_and_validate_challenge(raw_text, config, max_reward_rub, allowed_categories: set[str] | None = None) -> dict` — consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

Add after `test_parse_and_validate_challenge_strips_markdown_code_fence` in `tests/synth/test_challenges.py`:

```python
def test_parse_and_validate_challenge_accepts_category_within_allowed_set():
    raw = json.dumps({
        "challenge_title": "Test",
        "description": "desc",
        "target_categories": ["бакалея"],
        "mechanic": "скидка",
        "reward_rub": 30,
    })
    result = parse_and_validate_challenge(
        raw, _config, max_reward_rub=100, allowed_categories={"бакалея", "консервация"}
    )
    assert result["target_categories"] == ["бакалея"]


def test_parse_and_validate_challenge_rejects_category_outside_allowed_set():
    raw = json.dumps({
        "challenge_title": "Test",
        "description": "desc",
        "target_categories": ["овощи"],
        "mechanic": "скидка",
        "reward_rub": 30,
    })
    with pytest.raises(ValueError, match="outside allowed set"):
        parse_and_validate_challenge(raw, _config, max_reward_rub=100, allowed_categories={"бакалея"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/synth/test_challenges.py -k "allowed_set" -v`
Expected: FAIL — `TypeError: parse_and_validate_challenge() got an unexpected keyword argument 'allowed_categories'`.

- [ ] **Step 3: Add the parameter**

In `synth/challenges.py`, change the `parse_and_validate_challenge` signature and add the check right after the existing `forbidden_hit` check:

```python
def parse_and_validate_challenge(
    raw_text: str,
    config: SynthConfig,
    max_reward_rub: float,
    allowed_categories: set[str] | None = None,
) -> dict:
    try:
        data = json.loads(_strip_code_fence(raw_text))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON from model: {e}") from e

    missing = [f for f in _REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(f"missing fields in model output: {missing}")

    target_categories = data["target_categories"]
    if not isinstance(target_categories, list) or not target_categories:
        raise ValueError("target_categories must be a non-empty list")

    forbidden_hit = set(target_categories) & set(config.forbidden_categories)
    if forbidden_hit:
        raise ValueError(f"target_categories includes forbidden categories: {forbidden_hit}")

    if allowed_categories is not None:
        disallowed = set(target_categories) - allowed_categories
        if disallowed:
            raise ValueError(f"target_categories outside allowed set: {disallowed}")

    reward = float(data["reward_rub"])
    if reward < 0:
        raise ValueError("reward_rub must be non-negative")
    reward = min(reward, max_reward_rub)

    return {
        "challenge_title": str(data["challenge_title"]),
        "description": str(data["description"]),
        "target_categories": target_categories,
        "mechanic": str(data["mechanic"]),
        "reward_rub": round(reward, 2),
        "reasoning": str(data.get("reasoning", "")),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/synth/test_challenges.py -k "parse_and_validate" -v`
Expected: PASS (all `parse_and_validate_challenge` tests, old and new).

- [ ] **Step 5: Commit**

```bash
git add synth/challenges.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: add allowed_categories filter to parse_and_validate_challenge

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

### Task 4: `build_personal_prompt` — `focus` param (habit vs discovery)

**Files:**
- Modify: `synth/challenges.py`
- Test: `tests/synth/test_challenges.py`

**Interfaces:**
- Produces: `build_personal_prompt(profile, config, max_reward_rub, focus: str = "habit") -> tuple[str, str]` — consumed by Task 6.

- [ ] **Step 1: Write the failing test**

Add after `test_build_personal_prompt_mentions_forbidden_categories_and_reward_ceiling`:

```python
def test_build_personal_prompt_discovery_focus_differs_from_habit_focus():
    profile = _profile("promo_hunter", seed=1)
    habit_system, _ = build_personal_prompt(profile, _config, max_reward_rub=50.0, focus="habit")
    discovery_system, _ = build_personal_prompt(profile, _config, max_reward_rub=50.0, focus="discovery")
    assert habit_system != discovery_system
    assert "почти" in discovery_system
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_challenges.py -k "discovery_focus" -v`
Expected: FAIL — `TypeError: build_personal_prompt() got an unexpected keyword argument 'focus'`.

- [ ] **Step 3: Add the `focus` parameter**

Replace `build_personal_prompt` in `synth/challenges.py`:

```python
def build_personal_prompt(
    profile: dict, config: SynthConfig, max_reward_rub: float, focus: str = "habit"
) -> tuple[str, str]:
    summary = summarize_purchase_pattern(profile, config)
    forbidden = ", ".join(config.forbidden_categories)

    if focus == "discovery":
        focus_instruction = (
            "Сфокусируйся на категориях, которые пользователь почти НЕ покупает "
            "(судя по топ категориям ниже они отсутствуют или редки) — предложи "
            "челлендж, стимулирующий попробовать новую для него категорию. Не "
            "предлагай категорию, которая уже входит в его привычные/топ."
        )
    else:
        focus_instruction = (
            "Сфокусируйся на категориях, которые пользователь покупает чаще всего "
            "(привычные/топ категории ниже) — предложи челлендж, укрепляющий уже "
            "сложившуюся привычку."
        )

    system = (
        "Ты — модуль персональных рекомендаций программы лояльности X5 "
        "(Пятёрочка/Перекрёсток/Чижик). По истории покупок пользователя "
        "предложи ОДИН персональный челлендж — небольшую акцию, релевантную "
        "именно его привычкам, которая подтолкнёт к повторной или "
        "дополнительной покупке.\n\n"
        f"{focus_instruction}\n\n"
        f"Никогда не предлагай в target_categories эти категории: {forbidden} "
        "— они запрещены для челленджей (регулируемые/чувствительные).\n"
        f"reward_rub не должен превышать {max_reward_rub:.0f} ₽ — это ограничение "
        "по марже конкретно этого пользователя.\n"
        "Челлендж должен быть обоснован конкретными данными из истории "
        "покупок ниже, а не общими предположениями.\n\n"
        "Ответь СТРОГО в виде одного JSON-объекта, без текста вне JSON:\n"
        '{"challenge_title": string, "description": string, '
        '"target_categories": [string, ...], "mechanic": string, '
        '"reward_rub": number, "reasoning": string}'
    )

    user = (
        f"Сеть: {profile['chain']}\n"
        f"Сегмент: {profile['segment']}\n"
        f"Размер семьи: {profile['family_size']}\n"
        f"Привычные категории: {', '.join(profile['habitual_categories']) if profile['habitual_categories'] else '—'}\n"
        f"Чеков за 90 дней (train-период): {summary['n_receipts_90d_train']}\n"
        f"Топ категорий по числу позиций: {summary['top_categories']}\n"
        f"Доля покупок по выходным: {summary['weekend_share']:.0%}\n"
        f"Доля позиций по акции: {summary['promo_share']:.0%}\n"
        f"Средний чек: {summary['mean_receipt_total_rub']:.0f} ₽\n"
    )
    return system, user
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/synth/test_challenges.py -k "build_personal_prompt" -v`
Expected: PASS (both the old and new test).

- [ ] **Step 5: Commit**

```bash
git add synth/challenges.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: add habit/discovery focus to build_personal_prompt

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

### Task 5: `build_vibe_prompt`

**Files:**
- Modify: `synth/challenges.py`
- Test: `tests/synth/test_challenges.py`

**Interfaces:**
- Consumes: `VIBE_CATEGORIES` (Task 2).
- Produces: `build_vibe_prompt(profile, config, max_reward_rub, vibe_category: str) -> tuple[str, str]` — consumed by Task 6.

- [ ] **Step 1: Write the failing test**

Add `build_vibe_prompt` to the import block (alphabetical), then add after `test_build_personal_prompt_discovery_focus_differs_from_habit_focus`:

```python
def test_build_vibe_prompt_restricts_to_theme_categories_and_mentions_reward_ceiling():
    profile = _profile("promo_hunter", seed=1)
    system, user = build_vibe_prompt(profile, _config, max_reward_rub=65.0, vibe_category="Экономия и запасы")
    for cat in VIBE_CATEGORIES["Экономия и запасы"]:
        assert cat in system
    assert "65" in system
    assert "Экономия и запасы" in user
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_challenges.py -k "build_vibe_prompt" -v`
Expected: FAIL — `ImportError: cannot import name 'build_vibe_prompt'`.

- [ ] **Step 3: Add `build_vibe_prompt`**

In `synth/challenges.py`, insert right after `build_personal_prompt`:

```python
def build_vibe_prompt(
    profile: dict, config: SynthConfig, max_reward_rub: float, vibe_category: str
) -> tuple[str, str]:
    """Like `build_personal_prompt`, but themed: `target_categories` must
    come from `VIBE_CATEGORIES[vibe_category]` (the user's assigned theme
    for the month) instead of being free-form — enforced by
    `parse_and_validate_challenge`'s `allowed_categories` param, not by this
    function. Doesn't require any purchase history to make sense — the
    theme itself is the personalization signal, not the user's own habits —
    so this slot works identically for a cold-start user with zero
    receipts."""
    summary = summarize_purchase_pattern(profile, config)
    allowed = ", ".join(VIBE_CATEGORIES[vibe_category])

    system = (
        "Ты — модуль персональных рекомендаций программы лояльности X5 "
        "(Пятёрочка/Перекрёсток/Чижик). Пользователю на этот месяц назначена "
        f'тема "{vibe_category}". Предложи ОДИН челлендж строго в рамках этой '
        "темы — он должен ощущаться как часть тематической подборки месяца, "
        "а не случайная акция.\n\n"
        f"target_categories обязаны быть подмножеством этого списка: {allowed} "
        "— другие категории использовать нельзя.\n"
        f"reward_rub не должен превышать {max_reward_rub:.0f} ₽ — это ограничение "
        "по марже конкретно этого пользователя.\n\n"
        "Ответь СТРОГО в виде одного JSON-объекта, без текста вне JSON:\n"
        '{"challenge_title": string, "description": string, '
        '"target_categories": [string, ...], "mechanic": string, '
        '"reward_rub": number, "reasoning": string}'
    )

    user = (
        f"Сеть: {profile['chain']}\n"
        f"Тема месяца: {vibe_category}\n"
        f"Чеков за 90 дней (train-период): {summary['n_receipts_90d_train']}\n"
        f"Топ категорий по числу позиций: {summary['top_categories']}\n"
        f"Средний чек: {summary['mean_receipt_total_rub']:.0f} ₽\n"
    )
    return system, user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_challenges.py -k "build_vibe_prompt" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add synth/challenges.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: add build_vibe_prompt for the themed vibe challenge slot

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

### Task 6: Rewrite `generate_challenge_for_user` — 4 unconditional slots

**Files:**
- Modify: `synth/challenges.py`
- Test: `tests/synth/test_challenges.py`

**Interfaces:**
- Consumes: `VIBE_CATEGORIES`, `pick_vibe_category` (Task 2); `parse_and_validate_challenge(..., allowed_categories=...)` (Task 3); `build_personal_prompt(..., focus=...)` (Task 4); `build_vibe_prompt` (Task 5).
- Produces: `CHALLENGE_SLOTS: tuple[str, ...] = ("llm_habit", "llm_discovery", "generic", "vibe")` (replaces `PERSONAL_CHALLENGE_SLOTS`), `generate_challenge_for_user(profile, config, model, api_key=None, dry_run=False, vibe_month_key: str | None = None) -> list[dict]` — consumed by Task 8 (`web/src/webx5/services/challenge.py`, unchanged call site) and Task 9 (`tests/synth/test_cli.py`).

- [ ] **Step 1: Update the import block in the test file**

In `tests/synth/test_challenges.py`, replace `PERSONAL_CHALLENGE_SLOTS` with `CHALLENGE_SLOTS` in the import list (keep everything else, including `compute_receptiveness`/`compute_frequency_saturation`/`build_spend_threshold_challenge`/`build_category_expansion_challenge` — those stay imported, their own tests are untouched):

```python
from synth.challenges import (
    CHALLENGE_SLOTS,
    GENERIC_CHALLENGES,
    PERSONAL_TARGET_QUANTITY,
    VIBE_CATEGORIES,
    backfill_target_sku,
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

- [ ] **Step 2: Remove the tests tied to the old routing behavior**

Delete these test functions entirely from `tests/synth/test_challenges.py` (the behavior they check no longer exists in `generate_challenge_for_user` — the underlying functions they call are still tested elsewhere and untouched):
- `test_generate_challenge_for_user_routes_already_optimal_to_no_challenge` (calls `compute_frequency_saturation`'s old routing effect)
- `test_generate_challenge_for_user_non_receptive_uses_generic_for_every_slot_without_network`
- `test_generate_challenge_for_user_deterministic_fallbacks_never_record_a_model` (monkeypatches `build_spend_threshold_challenge`/`build_category_expansion_challenge`, which `generate_challenge_for_user` no longer calls)

- [ ] **Step 3: Rewrite the remaining `generate_challenge_for_user`-dependent tests to fail against the new signature**

Replace `test_generate_challenge_for_user_returns_one_record_per_slot` with:

```python
def test_generate_challenge_for_user_always_returns_four_slots_regardless_of_pattern_strength(monkeypatch):
    """The receptiveness/saturation gates are gone from the live routing
    function — these three profile classes used to hit three DIFFERENT old
    branches (strong pattern -> mostly personal, weak pattern -> all
    generic, already_optimal -> zero records). Now all three get the exact
    same 4-slot shape."""
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
        assert by_slot["vibe"]["path"] == "personal_dry_run"
        assert by_slot["generic"]["path"] == "generic"
```

Replace `test_generate_challenge_for_user_personal_path_with_mocked_llm` with (same idea, renamed slot):

```python
def test_generate_challenge_for_user_llm_habit_personal_path_with_mocked_llm(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return json.dumps({
            "challenge_title": "Допеки выходные",
            "description": "desc",
            "target_categories": ["бакалея"],
            "mechanic": "скидка",
            "reward_rub": 40,
            "reasoning": "weekend baking pattern",
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    llm_result = _by_slot(results)["llm_habit"]
    assert llm_result["path"] == "personal"
    assert llm_result["target_categories"] == ["бакалея"]
    assert llm_result["target_quantity"] == PERSONAL_TARGET_QUANTITY
    sku = pick_sku_in_category(_config, "бакалея", seed_key=f"{profile['user_id']}:sku:llm_habit")
    assert llm_result["target_sku_id"] == sku.sku_id
    assert llm_result["challenge_title"] == "Допеки выходные"
    assert sku.item in llm_result["description"]
    assert llm_result["description"] == item_action_description(sku.item, PERSONAL_TARGET_QUANTITY, 40)
```

Replace `test_generate_challenge_for_user_falls_back_on_bad_llm_output` with:

```python
def test_generate_challenge_for_user_falls_back_on_bad_llm_output(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return "not valid json"

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    llm_result = _by_slot(results)["llm_habit"]
    assert llm_result["path"] == "generic_fallback"
    assert "error" in llm_result
    assert llm_result["model"] == "fake/model"
    assert len(results) == len(CHALLENGE_SLOTS)
```

Add two new tests for the `vibe` slot, right after the one above:

```python
def test_generate_challenge_for_user_vibe_slot_uses_profile_vibe_category(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)
    profile = {**profile, "vibe_category": "Экономия и запасы"}

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        assert "Экономия и запасы" in system
        return json.dumps({
            "challenge_title": "Экономь на бакалее",
            "description": "desc",
            "target_categories": ["бакалея"],
            "mechanic": "скидка",
            "reward_rub": 30,
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    vibe_result = _by_slot(results)["vibe"]
    assert vibe_result["path"] == "personal"
    assert vibe_result["target_categories"] == ["бакалея"]


def test_generate_challenge_for_user_vibe_slot_falls_back_when_llm_picks_category_outside_theme(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)
    profile = {**profile, "vibe_category": "Забота о питомце"}  # only "товары для животных" allowed

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
    vibe_result = _by_slot(results)["vibe"]
    assert vibe_result["path"] == "generic_fallback"
    assert "outside allowed set" in vibe_result["error"]
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/synth/test_challenges.py -k "generate_challenge_for_user" -v`
Expected: FAIL — `generate_challenge_for_user` still uses the old 3-slot logic (`PERSONAL_CHALLENGE_SLOTS`/`compute_receptiveness` branch), so slot names/counts won't match.

- [ ] **Step 5: Rewrite `generate_challenge_for_user`**

In `synth/challenges.py`, replace the comment above `PERSONAL_CHALLENGE_SLOTS` (currently right before `_pick_distinct_generic_offer`) and the constant itself:

```python
# The four independent challenge slots every user gets, one attempt each,
# unconditionally — no receptiveness/saturation gate decides who gets
# personalization any more (see `compute_receptiveness`/
# `compute_frequency_saturation`, still used by `synth/simulation.py`'s
# offline effect model, but no longer by `generate_challenge_for_user`).
CHALLENGE_SLOTS = ("llm_habit", "llm_discovery", "generic", "vibe")
```

Keep `_pick_distinct_generic_offer` exactly as-is (still used, now dedups across up to 4 generic draws instead of 3).

Replace the entire `generate_challenge_for_user` function body with:

```python
def generate_challenge_for_user(
    profile: dict,
    config: SynthConfig,
    model: str,
    api_key: str | None = None,
    dry_run: bool = False,
    vibe_month_key: str | None = None,
) -> list[dict]:
    """Route one profile to exactly `len(CHALLENGE_SLOTS)` records — one per
    slot (`llm_habit`, `llm_discovery`, `generic`, `vibe`) — for EVERY user,
    regardless of purchase-pattern strength or frequency. There is no
    saturation/receptiveness gate here any more: a thin/noisy purchase
    history degrades gracefully through the LLM prompt
    (`summarize_purchase_pattern` already renders "—" for empty fields)
    rather than being rejected upfront.

    `llm_habit` and `llm_discovery` both call the LLM
    (`build_personal_prompt` with `focus="habit"`/`"discovery"`) — same
    failure/fallback handling, different instructions. `generic` is the
    deterministic `GENERIC_CHALLENGES` pool, unconditionally attempted for
    everyone (not just as a fallback, unlike before). `vibe` calls the LLM
    constrained to the user's monthly theme: `profile["vibe_category"]` if
    the caller already resolved/persisted one (the web layer always does,
    see `ChallengeAdapter._resolve_vibe_category`), otherwise
    `pick_vibe_category` picks one deterministically from `vibe_month_key`
    (defaults to the current UTC year-month) so offline/dry-run calls
    without a DB-backed profile still get a stable answer.

    Any LLM-backed slot whose call/validation fails falls back to a
    (slot-distinct) generic offer, `path="generic_fallback"` — same as the
    old single `llm` slot's behavior — never drops the slot.
    """
    used_generic_indices: list[int] = []

    def _generic(slot: str, path: str, error: str | None = None, model_attempted: str | None = None) -> dict:
        offer = _pick_distinct_generic_offer(profile["user_id"], config, used_generic_indices)
        record = {
            "user_id": profile["user_id"], "path": path,
            "model": model_attempted, "challenge_slot": slot, **offer,
        }
        if error is not None:
            record["error"] = error
        return record

    max_reward = estimate_max_reward_rub(profile)
    results: list[dict] = []

    def _run_llm_slot(slot: str, system: str, user_msg: str, allowed_categories: set[str] | None = None) -> None:
        if dry_run:
            results.append({
                "user_id": profile["user_id"], "path": "personal_dry_run",
                "model": model, "challenge_slot": slot, "max_reward_rub": max_reward,
                "note": "dry run — no LLM call made",
            })
            return
        try:
            raw = call_openrouter(model, system, user_msg, api_key)
            challenge = parse_and_validate_challenge(raw, config, max_reward, allowed_categories=allowed_categories)
            challenge["target_quantity"] = PERSONAL_TARGET_QUANTITY
            sku = pick_sku_in_category(config, challenge["target_categories"][0], seed_key=f"{profile['user_id']}:sku:{slot}")
            challenge["target_sku_id"] = sku.sku_id if sku else None
            if sku is not None:
                challenge["description"] = item_action_description(
                    sku.item, PERSONAL_TARGET_QUANTITY, challenge["reward_rub"]
                )
            results.append({
                "user_id": profile["user_id"], "path": "personal",
                "model": model, "challenge_slot": slot, **challenge,
            })
        except Exception as e:  # noqa: BLE001 — deliberately broad: any failure must fall back, not propagate
            results.append(_generic(slot, "generic_fallback", error=str(e), model_attempted=model))

    # slot: llm_habit
    system, user_msg = build_personal_prompt(profile, config, max_reward, focus="habit")
    _run_llm_slot("llm_habit", system, user_msg)

    # slot: llm_discovery
    system, user_msg = build_personal_prompt(profile, config, max_reward, focus="discovery")
    _run_llm_slot("llm_discovery", system, user_msg)

    # slot: generic — deterministic, no API call, always attempted for everyone
    offer = _pick_distinct_generic_offer(profile["user_id"], config, used_generic_indices)
    results.append({
        "user_id": profile["user_id"], "path": "generic",
        "model": None, "challenge_slot": "generic", **offer,
    })

    # slot: vibe
    vibe_category = profile.get("vibe_category") or pick_vibe_category(
        profile["user_id"], vibe_month_key or date.today().strftime("%Y-%m")
    )
    system, user_msg = build_vibe_prompt(profile, config, max_reward, vibe_category)
    _run_llm_slot("vibe", system, user_msg, allowed_categories=set(VIBE_CATEGORIES[vibe_category]))

    return results
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/synth/test_challenges.py -v`
Expected: all PASS (full file — this confirms the retained `compute_receptiveness`/`compute_frequency_saturation`/`build_spend_threshold_challenge`/`build_category_expansion_challenge` tests still pass untouched, alongside the new/rewritten `generate_challenge_for_user` tests).

- [ ] **Step 7: Run the offline simulation's own test suite to confirm it's unaffected**

Run: `pytest tests/synth/test_simulation.py -v`
Expected: all PASS, unchanged — `synth/simulation.py` wasn't touched.

- [ ] **Step 8: Commit**

```bash
git add synth/challenges.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: replace 3-slot receptiveness-gated mix with unconditional 4-slot mix

llm_habit + llm_discovery + generic + vibe, issued identically to every
user. compute_receptiveness/compute_frequency_saturation/
build_spend_threshold_challenge/build_category_expansion_challenge remain
for synth/simulation.py's offline effect model, just no longer wired into
this live routing function.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

### Task 7: `ChallengeAdapter` — resolve & persist the monthly vibe category

**Files:**
- Modify: `web/src/webx5/services/challenge_adapter.py`
- Test: `web/tests/webx5/services/test_challenge_adapter.py` (new)

**Interfaces:**
- Consumes: `pick_vibe_category` (Task 2, `synth.challenges`), `User.vibe_category`/`User.vibe_month` (Task 1).
- Produces: `ChallengeAdapter._resolve_vibe_category(session, user) -> str`; `build_profile(...)`'s returned dict gains a `"vibe_category"` key — consumed by Task 6's `generate_challenge_for_user` via `ChallengeService.generate_batch` (no call-site change needed there, the dict just carries one more key).

- [ ] **Step 1: Write the failing tests**

Create `web/tests/webx5/services/test_challenge_adapter.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && poetry run pytest tests/webx5/services/test_challenge_adapter.py -v`
Expected: FAIL — `AttributeError` (`ChallengeAdapter` has no `_resolve_vibe_category`), or a `MagicMock` comparison mismatch.

- [ ] **Step 3: Add `_resolve_vibe_category` and wire it into `build_profile`**

In `web/src/webx5/services/challenge_adapter.py`:

Change the imports at the top (add `date` and `pick_vibe_category`):

```python
from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synth.challenges import pick_vibe_category
from synth.config import SynthConfig
from webx5.crud.task import TaskRepository
from webx5.entities.category import Category
from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem
from webx5.entities.user import User
```

Add the new method right after `__init__` (before `build_profile`):

```python
    # ------- vibe-of-the-month resolution -------
    def _resolve_vibe_category(self, session: Session, user: User) -> str:
        """Return this user's "vibe" theme for the current calendar month.
        Stable across generation calls within a month; auto-rotates at the
        start of each new month via `pick_vibe_category` until a future
        manual-selection feature lets a user pick their own — the
        `vibe_category`/`vibe_month` columns exist for that reason, not
        just as a cache."""
        month_start = date.today().replace(day=1)
        if user.vibe_category and user.vibe_month == month_start:
            return user.vibe_category
        vibe_category = pick_vibe_category(str(user.id), month_start.strftime("%Y-%m"))
        user.vibe_category = vibe_category
        user.vibe_month = month_start
        session.flush()
        return vibe_category
```

In `build_profile`, right after the `if user is None: raise ValueError(...)` check, add:

```python
        vibe_category = self._resolve_vibe_category(session, user)
```

And in the final returned dict, add the key:

```python
        return {
            "user_id": str(user_id),
            "chain": "Пятёрочка",
            "segment": "unknown",
            "family_size": 1,
            "habitual_categories": habitual,
            "receipts": receipts_dicts,
            "vibe_category": vibe_category,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && poetry run pytest tests/webx5/services/test_challenge_adapter.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/services/challenge_adapter.py web/tests/webx5/services/test_challenge_adapter.py
git commit -m "$(cat <<'EOF'
feat: resolve and persist the user's monthly vibe category in build_profile

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

### Task 8: `ChallengeService` / schemas / tasks — 3→4 slots, drop `saturated`

**Files:**
- Modify: `web/src/webx5/services/challenge.py`
- Modify: `web/src/webx5/schemas/challenge.py`
- Modify: `web/src/webx5/tasks/generation.py`
- Modify: `web/src/webx5/tasks/receipt.py`
- Modify: `web/tests/webx5/services/test_challenge_service.py`
- Modify: `web/tests/webx5/routes/test_challenges.py`

**Interfaces:**
- Consumes: `generate_challenge_for_user` (Task 6, same call signature as before — no change needed at this call site beyond the slot names it returns).
- Produces: nothing new consumed by later tasks.

- [ ] **Step 1: Update `test_challenge_service.py` to the new slot names/limit — run first to see it fail**

In `web/tests/webx5/services/test_challenge_service.py`:

Replace `_canned`/`_batch_all_three`:

```python
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
```

Replace every `_batch_all_three()` call with `_batch_all_four()`, and every `count=3`/`assert len(created) == 3`/`log_repo.record.call_count == 3`/`adapter.persist_challenge.call_count == 3` with the `4` equivalent:

```python
def test_generate_batch_persists_all_four_slots():
    service, task_repo, log_repo, adapter = _service_with_mocks()

    with patch("webx5.services.challenge.generate_challenge_for_user", return_value=_batch_all_four()), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        created = service.generate_batch(MagicMock(), uuid.uuid4(), count=4)

    assert len(created) == 4
    assert log_repo.record.call_count == 4
    assert adapter.persist_challenge.call_count == 4
```

```python
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
```

(This test stays — `path == "no_challenge"` is still handled defensively by `generate_batch`, it's just that `generate_challenge_for_user` no longer produces it in practice. Keeping the defensive branch is out of scope for this task; it's harmless dead code the service tolerates.)

```python
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
```

Also update the module docstring (top of the file) and inline comments (`# invariant "no more than 3 active tasks" (FR-001)`) to say 4 instead of 3.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && poetry run pytest tests/webx5/services/test_challenge_service.py -v`
Expected: FAIL — `remaining_slots = 3 - len(active_tasks)` in the source still caps at 3, so `test_generate_batch_persists_all_four_slots` gets only 3 created.

- [ ] **Step 3: Update `web/src/webx5/services/challenge.py`**

Change the module docstring (lines 1-7) to:

```python
"""High-level challenge service: batch generation via `synth.challenges` +
resolving current-active list for API.

Synth API (single call → list[dict] of exactly 4 records, each with
`challenge_slot ∈ {'llm_habit', 'llm_discovery', 'generic', 'vibe'}`).
De-dup with active tasks is done via `task.challenge_slot`.
"""
```

Change line 30:

```python
ALL_SLOTS: tuple[str, ...] = ("llm_habit", "llm_discovery", "generic", "vibe")
```

Remove the now-unused import (line 22): delete `from webx5.entities.challenge_log import ChallengeGenerationLog`.

Change the `generate_batch` docstring and the `3 -`:

```python
    def generate_batch(self, session: Session, user_id: uuid.UUID, count: int) -> list[uuid.UUID]:
        """Generate up to `count` new tasks for `user_id`, filling missing challenge slots.
        Respects invariant "no more than 4 active tasks" (FR-001).

        Synth API: one call → list[dict] with exactly 4 records.
        We filter the returned records by challenge_slot to skip slots the user
        already has active, then persist up to `count` of the remaining.
        """
        active_tasks = self.task_repo.get_active_for_user(session, user_id)
        remaining_slots = 4 - len(active_tasks)
```

Replace `get_current` (drop the `saturated` branch and the now-dead `ChallengeGenerationLog`-based lookup):

```python
    def get_current(self, session: Session, user_id: uuid.UUID) -> tuple[list[Task], str]:
        """Returns (list of active tasks, empty_reason).
        empty_reason ∈ {'none', 'no_history'}."""
        active = self.task_repo.get_active_for_user(session, user_id)
        if active:
            return active, "none"

        has_receipts = session.execute(
            select(exists().where(Receipt.loyalty_card_id == user_id))
        ).scalar()
        if not has_receipts:
            return [], "no_history"

        return [], "none"
```

- [ ] **Step 4: Update `web/src/webx5/schemas/challenge.py`**

Remove `saturated = "saturated"` from `EmptyReason`:

```python
class EmptyReason(str, Enum):
    none = "none"
    no_history = "no_history"
```

- [ ] **Step 5: Update `web/src/webx5/tasks/generation.py`**

Change the default:

```python
def generate_challenges(user_id: str, count: int = 4) -> dict:
```

- [ ] **Step 6: Update `web/src/webx5/tasks/receipt.py`**

Change the first-receipt trigger (around line 62-69):

```python
            # First-receipt trigger (R9): no active tasks → generate 4.
            if not active:
                logger.info(
                    "process_receipt.first_receipt_trigger",
                    user_id=str(user_id),
                    receipt_id=receipt_id,
                )
                generate_challenges.apply_async(args=[str(user_id), 4], queue="challenges")
                return {"status": "first_receipt_generation_enqueued", "user_id": str(user_id)}
```

- [ ] **Step 7: Update `web/tests/webx5/routes/test_challenges.py`**

Rename `test_get_current_returns_3_tasks` to `test_get_current_returns_active_tasks` and use 4 tasks instead of 3:

```python
def test_get_current_returns_active_tasks(client, user_id):
    tc, session = client
    task = _make_task(user_id)

    with patch("webx5.core.challenges.challenge_service.get_current", return_value=([task, task, task, task], "none")):
        resp = tc.get("/challenges/current", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 4
    assert body["empty_reason"] == "none"
```

Delete `test_get_current_saturated` entirely (the `"saturated"` empty_reason no longer exists — `EmptyReason` would reject it with a validation error, not return it).

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd web && poetry run pytest tests/webx5/services/test_challenge_service.py tests/webx5/routes/test_challenges.py -v`
Expected: all PASS.

- [ ] **Step 9: Run the full web test suite for a regression check**

Run: `cd web && poetry run pytest -v`
Expected: all PASS (this also catches anything importing `ChallengeGenerationLog` from `challenge.py` or `EmptyReason.saturated` elsewhere that this task missed).

- [ ] **Step 10: Commit**

```bash
git add web/src/webx5/services/challenge.py web/src/webx5/schemas/challenge.py web/src/webx5/tasks/generation.py web/src/webx5/tasks/receipt.py web/tests/webx5/services/test_challenge_service.py web/tests/webx5/routes/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: raise active-task limit to 4 slots, drop the saturated empty_reason

ALL_SLOTS/remaining_slots/generate_challenges default now match the new
4-slot mix (llm_habit/llm_discovery/generic/vibe). EmptyReason.saturated
and ChallengeService.get_current's matching branch are removed — the
frequency-saturation gate no longer routes the live per-user mix.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

### Task 9: Update `synth/cli.py`'s dry-run/score integration test

**Files:**
- Modify: `tests/synth/test_cli.py`

**Interfaces:**
- Consumes: `CHALLENGE_SLOTS` (Task 6).

- [ ] **Step 1: Update the failing assertion**

In `tests/synth/test_cli.py`, add the import and fix `test_cli_challenges_dry_run_and_score`:

```python
from synth.challenges import CHALLENGE_SLOTS
```

```python
def test_cli_challenges_dry_run_and_score(tmp_path):
    profiles_path = tmp_path / "reference_profiles.json"
    key_path = tmp_path / "answer_key.json"
    main([
        "reference", "--count", "6", "--seed", "1",
        "--out", str(profiles_path),
        "--answer-key-out", str(key_path),
    ])

    challenges_path = tmp_path / "challenges.json"
    main([
        "challenges", "--profiles", str(profiles_path),
        "--dry-run", "--out", str(challenges_path),
    ])
    challenges = json.loads(challenges_path.read_text(encoding="utf-8"))
    # every profile now yields exactly len(CHALLENGE_SLOTS) records — no more
    # saturated/no_challenge short-circuit to a single record
    assert len(challenges) == 6 * len(CHALLENGE_SLOTS)
    assert len({c["user_id"] for c in challenges}) == 6

    main(["score-challenges", "--challenges", str(challenges_path), "--answer-key", str(key_path)])
```

- [ ] **Step 2: Run the test to verify it was failing before the fix, then passes after**

Run: `pytest tests/synth/test_cli.py::test_cli_challenges_dry_run_and_score -v`
Expected: PASS (this confirms end-to-end: reference profiles → dry-run challenges → scoring, all work with the new 4-slot generator).

- [ ] **Step 3: Run the full root test suite**

Run: `pytest tests/synth/ -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/synth/test_cli.py
git commit -m "$(cat <<'EOF'
test: fix CLI dry-run test for the fixed 4-record-per-user challenge mix

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

### Task 10: Documentation — BACKLOG.md and CONTEXT_PACK.md

**Files:**
- Modify: `BACKLOG.md`
- Modify: `CONTEXT_PACK.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Read the current `BACKLOG.md` and `CONTEXT_PACK.md` §6/§H2 to match their existing formatting**

Run: `sed -n '1,40p' BACKLOG.md` and locate the H2/hit-rate section in `CONTEXT_PACK.md` (search for "hit rate" / "87.5%").

- [ ] **Step 2: Add a `BACKLOG.md` entry**

Add an entry (matching the file's existing format/heading level) noting:

```markdown
## Персональные челленджи: receptiveness/saturation-гейтинг живой выдачи

`compute_receptiveness` и `compute_frequency_saturation` (`synth/challenges.py`)
больше не определяют, какой микс челленджей получит живой пользователь —
с 2026-09-05 каждый пользователь получает одинаковый 4-слотовый микс
(`llm_habit`, `llm_discovery`, `generic`, `vibe`) независимо от силы
покупательского паттерна или частоты покупок. Обе функции, а также
`build_spend_threshold_challenge`/`build_category_expansion_challenge`,
остаются в коде и используются `synth/simulation.py` для офлайн-симуляции
экономического эффекта — удалять их нельзя. Решение отказаться от
гейтинга в живой выдаче принято сознательно (см.
`docs/superpowers/specs/2026-09-05-challenge-mix-vibe-design.md`), не баг.
```

- [ ] **Step 3: Add a `CONTEXT_PACK.md` note near the hit-rate status line**

Right after the existing "Статус (2026-09-04): достигнут hit rate 87.5% (35/40) ..." line, add:

```markdown
**Обновление (2026-09-05):** генератор челленджей (`generate_challenge_for_user`)
переработан — единый 4-слотовый микс для всех пользователей вместо
receptiveness/saturation-гейтинга (см. `docs/superpowers/specs/2026-09-05-challenge-mix-vibe-design.md`).
Hit-rate 87.5% посчитан на СТАРОЙ версии генератора и больше не отражает
текущее поведение — нужно перезапустить `synth/cli.py`'s `reference`/
`challenges`/`score-challenges` и обновить это значение. Экономическая
симуляция эффекта (`synth/simulation.py`) не затронута.
```

- [ ] **Step 4: Commit**

```bash
git add BACKLOG.md CONTEXT_PACK.md
git commit -m "$(cat <<'EOF'
docs: record challenge-mix redesign in BACKLOG.md and flag stale hit-rate

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013FrftEfpcx58983JGPHrYX
EOF
)"
```

---

## Manual verification (not automated — do after Task 10)

- [ ] `cd web && poetry run pytest` — full web suite green.
- [ ] `pytest` (repo root) — full synth suite green.
- [ ] `grep -rn "PERSONAL_CHALLENGE_SLOTS" .` — expect zero remaining references (confirms the rename in Task 6 is complete everywhere).
- [ ] Grep the mobile app for a hardcoded slot count that might not render a 4th card correctly:
  `grep -rn "\[0\], .*\[1\], .*\[2\]\|length === 3\|length == 3\|slice(0, 3)" x5mobile/src/hooks/useChallenges.ts x5mobile/src/components/screens/challenges-view.tsx`
  Expected: no matches. If something matches, open the file and confirm it doesn't assume exactly 3 items before deciding whether a follow-up fix is needed (out of scope for this plan per the design doc — file as a new BACKLOG.md/follow-up item instead of fixing inline here).
