# Challenge Category Selection via Survival Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LLM-driven category selection for the `llm_habit`, `llm_discovery`, and `generic` challenge slots with a Kaplan-Meier survival-analysis risk score, computed from users' own purchase recency against population-level per-category repurchase curves.

**Architecture:** A new pure, dependency-free `synth/survival.py` module fits a Kaplan-Meier curve per category from population purchase intervals (with correct right-censoring) and exposes a lookup to convert "days since last purchase" into a churn-risk score. A new deterministic builder in `synth/challenges.py` ranks a user's own categories by that risk and returns a templated (non-LLM) challenge for the Nth-ranked one. On the web side, a new `SurvivalCurveStore` service lazily fits the population curves once per process from live receipt data (via a new `SurvivalRepository`) and is injected into `ChallengeService`, which threads the curves into `generate_challenge_for_user`. `llm_basket` and `vibe` are untouched.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 (sync), FastAPI, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-06-challenge-survival-risk-design.md`

## Global Constraints

- No new Poetry dependencies — `web/pyproject.toml` has no numeric/ML libraries today (verified: no numpy/pandas/scipy/lifelines/scikit-survival); the KM estimator is hand-written pure Python.
- `ChallengeAdapter.build_profile` reads the user's **full** purchase history, not a 90-day window (removes the existing `cutoff` in `web/src/webx5/services/challenge_adapter.py:122`).
- Population KM curves are fit **once per process**, lazily on first use (not at module-import time, not on a TTL) — `web/src/webx5/core/challenges.py` must not gain a DB call at import time (its own docstring: "No side effects on module import beyond object construction — do NOT open DB connections here").
- `llm_basket` and `vibe` slots are untouched by this feature.
- No Alembic migration — no schema changes anywhere in this plan.
- `synth/survival.py` stays DB-free (plain `dict`/`date` in, plain `dict`/dataclass out), matching the rest of `synth`'s "pure function generator" contract.
- **Deviation from the spec, made at plan time:** the spec names the new curve-cache class `web/src/webx5/core/survival.py::SurvivalCurveStore`. Putting it in `core/` would make `web/src/webx5/services/challenge.py` (a service) import from `core/` to type-hint its constructor param — backwards per this project's own layering rule ("`core/` не дублирует слои — только создаёт объекты", `.claude/rules/fastapi-rest-api.md`). This plan places the class in `web/src/webx5/services/survival.py` instead (a service, like `ChallengeAdapter`), constructed once in `core/challenges.py` exactly like every other service there. Behavior is unchanged from the spec; only the file path/layer differs.

---

### Task 1: `synth/survival.py` — `SurvivalCurve` + `fit_km_curve`

**Files:**
- Create: `synth/survival.py`
- Test: `tests/synth/test_survival.py`

**Interfaces:**
- Produces: `SurvivalCurve` (frozen dataclass: `times: tuple[int, ...]`, `survival: tuple[float, ...]`; methods `survival_at(days: int) -> float`, `median_survival_days() -> int | None`), `fit_km_curve(durations: list[int], censored: list[bool]) -> SurvivalCurve`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/synth/test_survival.py
from synth.survival import SurvivalCurve, fit_km_curve


def test_fit_km_curve_matches_hand_computed_product_limit_estimate():
    # durations: 5, 10, 10, 15, 20(censored) — 5 subjects total.
    # t=5:  n=5, d=1 -> factor 4/5           -> S=0.8
    # t=10: n=4, d=2 -> factor 2/4 = 0.5     -> S=0.4
    # t=15: n=2, d=1 -> factor 1/2 = 0.5     -> S=0.2
    # t=20: censored only, no event -> no step, S stays 0.2
    curve = fit_km_curve(
        durations=[5, 10, 10, 15, 20],
        censored=[False, False, False, False, True],
    )
    assert curve.times == (5, 10, 15)
    assert curve.survival == pytest.approx((0.8, 0.4, 0.2))


def test_survival_at_is_a_step_function():
    curve = fit_km_curve(durations=[5, 10, 10, 15, 20], censored=[False, False, False, False, True])
    assert curve.survival_at(0) == 1.0
    assert curve.survival_at(4) == 1.0
    assert curve.survival_at(5) == pytest.approx(0.8)
    assert curve.survival_at(7) == pytest.approx(0.8)
    assert curve.survival_at(10) == pytest.approx(0.4)
    assert curve.survival_at(15) == pytest.approx(0.2)
    # Past the last observed event: last computed S, not extrapolated to 0.
    assert curve.survival_at(1000) == pytest.approx(0.2)


def test_median_survival_days_returns_first_time_at_or_below_half():
    curve = fit_km_curve(durations=[5, 10, 10, 15, 20], censored=[False, False, False, False, True])
    assert curve.median_survival_days() == 10


def test_median_survival_days_is_none_when_curve_never_drops_to_half():
    curve = fit_km_curve(durations=[100, 100], censored=[True, True])
    assert curve.median_survival_days() is None


def test_fit_km_curve_with_all_censored_observations_never_drops_below_one():
    curve = fit_km_curve(durations=[3, 7], censored=[True, True])
    assert curve.times == ()
    assert curve.survival_at(0) == 1.0
    assert curve.survival_at(100) == 1.0
```

Add `import pytest` at the top of the test file alongside the existing import.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_survival.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'synth.survival'`

- [ ] **Step 3: Implement `synth/survival.py`**

```python
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class SurvivalCurve:
    """Kaplan-Meier product-limit estimate of P(category not yet
    repurchased | t days since last purchase). `times`/`survival` are
    parallel: `survival[i]` is S(t) for all t in
    `[times[i], times[i+1])` (or `[times[i], inf)` for the last entry)."""

    times: tuple[int, ...]
    survival: tuple[float, ...]

    def survival_at(self, days: int) -> float:
        """Step function. Before the first event time: 1.0 (nothing has
        happened yet, by definition). At or after the last observed event
        time: the last computed S — we never extrapolate to 0, since
        beyond the observed data we have no information at all."""
        if not self.times or days < self.times[0]:
            return 1.0
        result = self.survival[0]
        for t, s in zip(self.times, self.survival):
            if days < t:
                break
            result = s
        return result

    def median_survival_days(self) -> int | None:
        """Smallest t where S(t) <= 0.5; None if the curve never reaches
        0.5 within the observed times (used to size a challenge deadline —
        no data means no informed deadline, caller must supply a default)."""
        for t, s in zip(self.times, self.survival):
            if s <= 0.5:
                return t
        return None


def fit_km_curve(durations: list[int], censored: list[bool]) -> SurvivalCurve:
    """Standard Kaplan-Meier product-limit estimator:

        S(t) = product over all event times t_i <= t of (1 - d_i / n_i)

    where `d_i` is the number of UNCENSORED observations equal to `t_i`,
    and `n_i` is the number of observations still "at risk" at `t_i`
    (duration >= t_i, censored or not — censoring only removes an
    observation from the risk set for STRICTLY LATER times, it never
    produces an event of its own). Observations with duration <= 0 are
    dropped (a same-day repurchase carries no information about time-to-
    event at day granularity).
    """
    pairs = [(d, c) for d, c in zip(durations, censored) if d > 0]
    if not pairs:
        return SurvivalCurve(times=(), survival=())

    event_times = sorted({d for d, c in pairs if not c})
    n_total = len(pairs)

    times: list[int] = []
    survival: list[float] = []
    running_survival = 1.0
    for t in event_times:
        n_at_risk = sum(1 for d, _ in pairs if d >= t)
        n_events = sum(1 for d, c in pairs if d == t and not c)
        if n_at_risk == 0:
            continue
        running_survival *= 1.0 - (n_events / n_at_risk)
        times.append(t)
        survival.append(running_survival)

    return SurvivalCurve(times=tuple(times), survival=tuple(survival))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_survival.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add synth/survival.py tests/synth/test_survival.py
git commit -m "$(cat <<'EOF'
feat: add Kaplan-Meier survival curve estimator (synth/survival.py)

Pure, dependency-free product-limit estimator with correct right-censoring
handling — the first building block for risk-based challenge category
selection.
EOF
)"
```

---

### Task 2: `synth/survival.py` — `fit_population_curves` + `purchase_dates_from_profiles`

**Files:**
- Modify: `synth/survival.py`
- Test: `tests/synth/test_survival.py`

**Interfaces:**
- Consumes: `SurvivalCurve`, `fit_km_curve` (Task 1).
- Produces: `fit_population_curves(purchase_dates_by_user: dict[str, dict[str, list[date]]], as_of: date) -> dict[str, SurvivalCurve]`, `purchase_dates_from_profiles(profiles: list[dict]) -> dict[str, dict[str, list[date]]]`. Both consumed by Task 5 (CLI) and Task 7/8 (web repository/store).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/synth/test_survival.py
from datetime import date

from synth.survival import fit_population_curves, purchase_dates_from_profiles


def test_fit_population_curves_builds_intervals_and_censoring_per_category():
    # u1: молоко on Jan1, Jan11 (interval 10, uncensored), then censored
    #     Jan11 -> as_of Jan21 (interval 10, censored).
    # u2: молоко on Jan5 only -> censored Jan5 -> as_of Jan21 (interval 16).
    purchase_dates_by_user = {
        "u1": {"молоко": [date(2026, 1, 1), date(2026, 1, 11)]},
        "u2": {"молоко": [date(2026, 1, 5)]},
    }
    curves = fit_population_curves(purchase_dates_by_user, as_of=date(2026, 1, 21))

    assert "молоко" in curves
    # One uncensored event at t=10 (u1's first interval), at risk n=3
    # (u1's two intervals + u2's one), so S(10) = 1 - 1/3.
    assert curves["молоко"].survival_at(10) == pytest.approx(2 / 3)


def test_fit_population_curves_single_purchase_gives_only_a_censored_observation():
    purchase_dates_by_user = {"u1": {"овощи": [date(2026, 1, 1)]}}
    curves = fit_population_curves(purchase_dates_by_user, as_of=date(2026, 1, 8))
    # A single censored observation produces no event -> flat curve at 1.0.
    assert curves["овощи"].times == ()
    assert curves["овощи"].survival_at(100) == 1.0


def test_fit_population_curves_skips_categories_with_no_observations():
    assert fit_population_curves({}, as_of=date(2026, 1, 1)) == {}


def test_purchase_dates_from_profiles_groups_dates_by_user_and_category():
    profiles = [
        {
            "user_id": "u1",
            "receipts": [
                {"purchase_date": "2026-01-01", "lines": [{"category": "молоко"}, {"category": "хлеб"}]},
                {"purchase_date": "2026-01-01", "lines": [{"category": "молоко"}]},  # same-day dup
                {"purchase_date": "2026-01-11", "lines": [{"category": "молоко"}]},
            ],
        },
    ]
    result = purchase_dates_from_profiles(profiles)
    assert result["u1"]["молоко"] == [date(2026, 1, 1), date(2026, 1, 11)]
    assert result["u1"]["хлеб"] == [date(2026, 1, 1)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_survival.py -v -k "population_curves or purchase_dates_from_profiles"`
Expected: FAIL with `ImportError: cannot import name 'fit_population_curves'`

- [ ] **Step 3: Implement**

Append to `synth/survival.py` (add `from datetime import date` to the existing `from __future__ import annotations` import block):

```python
from datetime import date


def fit_population_curves(
    purchase_dates_by_user: dict[str, dict[str, list[date]]],
    as_of: date,
) -> dict[str, SurvivalCurve]:
    """Fit one `SurvivalCurve` per category from population-wide purchase
    history. For each user's sorted purchase dates in a category:
      - each consecutive pair -> an observed (uncensored) interval, and
      - the gap from the LAST purchase to `as_of` -> a censored interval
        (the user may repurchase after `as_of` — we just don't know yet;
        dropping this observation instead of censoring it would bias the
        curve toward overstating risk).
    A user with a single purchase in a category contributes only that one
    censored interval — informative, not noise.
    """
    durations_by_category: dict[str, list[int]] = {}
    censored_by_category: dict[str, list[bool]] = {}

    for categories in purchase_dates_by_user.values():
        for category, dates in categories.items():
            if not dates:
                continue
            ordered = sorted(dates)
            durations = durations_by_category.setdefault(category, [])
            censored = censored_by_category.setdefault(category, [])
            for previous, current in zip(ordered, ordered[1:]):
                durations.append((current - previous).days)
                censored.append(False)
            durations.append((as_of - ordered[-1]).days)
            censored.append(True)

    return {
        category: fit_km_curve(durations_by_category[category], censored_by_category[category])
        for category in durations_by_category
    }


def purchase_dates_from_profiles(profiles: list[dict]) -> dict[str, dict[str, list[date]]]:
    """Population-level per-user per-category purchase dates from the
    `reference_profiles`/`population` profile-dict shape (`user_id` +
    `receipts[].purchase_date` ISO string + `receipts[].lines[].category`).
    Pure/DB-free — the offline (CLI) counterpart of
    `webx5.crud.survival.SurvivalRepository.fetch_purchase_dates`, which
    builds the identical shape from the live DB for the web path."""
    by_user: dict[str, dict[str, set[date]]] = {}
    for profile in profiles:
        by_category = by_user.setdefault(profile["user_id"], {})
        for receipt in profile["receipts"]:
            purchase_date = date.fromisoformat(receipt["purchase_date"])
            for line in receipt["lines"]:
                by_category.setdefault(line["category"], set()).add(purchase_date)

    return {
        user_id: {category: sorted(dates) for category, dates in by_category.items()}
        for user_id, by_category in by_user.items()
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_survival.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add synth/survival.py tests/synth/test_survival.py
git commit -m "$(cat <<'EOF'
feat: fit population-level survival curves from purchase history

Adds fit_population_curves (right-censored interval construction per
category) and purchase_dates_from_profiles, the offline-profile-shape
adapter feeding it.
EOF
)"
```

---

### Task 3: `synth/challenges.py` — `build_survival_risk_challenge`

**Files:**
- Modify: `synth/challenges.py`
- Test: `tests/synth/test_challenges.py`

**Interfaces:**
- Consumes: `SurvivalCurve` (Task 1); `SLOT_TARGET_QUANTITY`, `PERSONAL_TARGET_QUANTITY`, `pick_sku_in_category`, `item_action_description`, `estimate_max_reward_rub` (all already in `synth/challenges.py`).
- Produces: `build_survival_risk_challenge(profile: dict, config: SynthConfig, category_curves: dict[str, SurvivalCurve], rank: int, slot: str, as_of: date | None = None, discount_pct: float = 10.0) -> dict | None`. Consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/synth/test_challenges.py, near the other builder tests
from datetime import date

from synth.survival import SurvivalCurve


def _curve(times, survival):
    return SurvivalCurve(times=tuple(times), survival=tuple(survival))


def test_build_survival_risk_challenge_picks_the_nth_riskiest_category():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {
            "молочные продукты и яйца": "2026-08-01",  # 30 days ago -> high risk
            "овощи": "2026-08-28",  # 3 days ago -> low risk
        },
    }
    curves = {
        "молочные продукты и яйца": _curve([5, 30], [0.9, 0.1]),
        "овощи": _curve([5, 30], [0.9, 0.1]),
    }
    result = build_survival_risk_challenge(
        profile, _config, curves, rank=0, slot="llm_habit", as_of=date(2026, 8, 31),
    )
    assert result is not None
    assert result["target_categories"] == ["молочные продукты и яйца"]
    assert result["target_quantity"] == SLOT_TARGET_QUANTITY["llm_habit"]
    assert result["deadline_days"] is not None

    second = build_survival_risk_challenge(
        profile, _config, curves, rank=1, slot="llm_discovery", as_of=date(2026, 8, 31),
    )
    assert second["target_categories"] == ["овощи"]


def test_build_survival_risk_challenge_returns_none_without_purchase_history():
    profile = {"user_id": "u1", "receipts": [], "category_last_purchase": {}}
    assert build_survival_risk_challenge(profile, _config, {}, rank=0, slot="llm_habit") is None


def test_build_survival_risk_challenge_returns_none_when_rank_exceeds_available_categories():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {"овощи": "2026-08-01"},
    }
    curves = {"овощи": _curve([5], [0.5])}
    assert build_survival_risk_challenge(profile, _config, curves, rank=1, slot="generic") is None


def test_build_survival_risk_challenge_skips_forbidden_categories():
    forbidden = _config.forbidden_categories[0]
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {forbidden: "2026-08-01", "овощи": "2026-08-01"},
    }
    curves = {forbidden: _curve([5], [0.1]), "овощи": _curve([5], [0.9])}
    result = build_survival_risk_challenge(profile, _config, curves, rank=0, slot="generic")
    assert result["target_categories"] == ["овощи"]


def test_build_survival_risk_challenge_skips_categories_without_a_fitted_curve():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {"овощи": "2026-08-01", "фрукты": "2026-08-01"},
    }
    # Only "овощи" has a curve — "фрукты" must be ignored, not crash.
    curves = {"овощи": _curve([5], [0.5])}
    result = build_survival_risk_challenge(profile, _config, curves, rank=0, slot="generic")
    assert result["target_categories"] == ["овощи"]
    assert build_survival_risk_challenge(profile, _config, curves, rank=1, slot="generic") is None


def test_build_survival_risk_challenge_deadline_from_median_survival_capped_at_30():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {"овощи": "2026-08-01"},
    }
    curves = {"овощи": _curve([5, 60], [0.9, 0.1])}  # median never <= 0.5 within cap... see below
    result = build_survival_risk_challenge(profile, _config, curves, rank=0, slot="generic")
    # median_survival_days() -> None for this curve (never <= 0.5 at t=5 or 60... 0.1 IS <= 0.5)
    # so median is 60 -> deadline caps at 30.
    assert result["deadline_days"] == 30


def test_build_survival_risk_challenge_deadline_defaults_when_no_median():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {"овощи": "2026-08-01"},
    }
    curves = {"овощи": _curve([5], [0.9])}  # never drops to 0.5 -> median is None
    result = build_survival_risk_challenge(profile, _config, curves, rank=0, slot="generic")
    assert result["deadline_days"] == 14
```

Add `build_survival_risk_challenge` to the existing `from synth.challenges import (...)` block at the top of the test file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_challenges.py -v -k build_survival_risk_challenge`
Expected: FAIL with `ImportError: cannot import name 'build_survival_risk_challenge'`

- [ ] **Step 3: Implement**

Add to `synth/challenges.py` (near `build_category_expansion_challenge`; add `from synth.survival import SurvivalCurve` to the imports at the top of the file):

```python
_SURVIVAL_TITLE_TEMPLATES: dict[str, str] = {
    "llm_habit": "Вернитесь к «{category}»",
    "llm_discovery": "Не забывайте про «{category}»",
    "generic": "Специально для вас: «{category}»",
}


def build_survival_risk_challenge(
    profile: dict,
    config: SynthConfig,
    category_curves: dict[str, SurvivalCurve],
    rank: int,
    slot: str,
    as_of: date | None = None,
    discount_pct: float = 10.0,
) -> dict | None:
    """Deterministic, no-LLM-call challenge: rank every category the user
    has ever bought (`profile["category_last_purchase"]`) by churn risk —
    `1 - curve.survival_at(days_since_last_purchase)` on that category's
    population Kaplan-Meier curve — and return a challenge on the
    `rank`-th riskiest one (0 = riskiest).

    Categories in `config.forbidden_categories`, or with no fitted curve
    in `category_curves` (population never observed them — shouldn't
    happen in practice, but not guaranteed), are excluded from ranking.

    Returns None if the user has no purchase history at all, or if fewer
    than `rank + 1` categories remain after the exclusions above — the
    caller falls back to the pre-existing generic pool, same as any other
    "can't build this challenge" case in this module.

    `as_of` defaults to `date.today()`; callers needing reproducibility
    (offline scoring against `config.temporal_split`) pass it explicitly.
    """
    last_purchase = profile.get("category_last_purchase") or {}
    if not last_purchase:
        return None

    resolved_as_of = as_of if as_of is not None else date.today()
    forbidden = set(config.forbidden_categories)

    scored: list[tuple[float, str, int, SurvivalCurve]] = []
    for category, last_date_iso in last_purchase.items():
        if category in forbidden:
            continue
        curve = category_curves.get(category)
        if curve is None:
            continue
        days = (resolved_as_of - date.fromisoformat(last_date_iso)).days
        risk = 1.0 - curve.survival_at(days)
        scored.append((risk, category, days, curve))

    scored.sort(key=lambda entry: entry[0], reverse=True)
    if rank >= len(scored):
        return None

    risk, category, days, curve = scored[rank]
    econ_by_category = {e.category: e for e in config.category_economics}
    base_price = econ_by_category[category].base_price_rub
    max_reward = estimate_max_reward_rub(profile)
    reward_rub = round(min(base_price * (discount_pct / 100), max_reward), 2)

    median_days = curve.median_survival_days()
    deadline_days = min(30, median_days) if median_days is not None else 14

    quantity = SLOT_TARGET_QUANTITY.get(slot, PERSONAL_TARGET_QUANTITY)
    sku = pick_sku_in_category(config, category, seed_key=f"{profile['user_id']}:sku:{slot}")

    title_template = _SURVIVAL_TITLE_TEMPLATES.get(slot, _SURVIVAL_TITLE_TEMPLATES["generic"])
    title = title_template.format(category=category)

    if sku is not None:
        description = item_action_description(sku.item, quantity, reward_rub, slot=slot)
    else:
        description = f"Специальное предложение в категории «{category}»."

    median_text = str(median_days) if median_days is not None else "неизвестно"
    reasoning = (
        f"«{category}» — риск оттока {risk:.0%}: не покупали {days} дн., "
        f"медианный цикл повторной покупки по популяции ~{median_text} дн. (ранг {rank + 1})."
    )

    return {
        "challenge_title": title,
        "description": description,
        "target_categories": [category],
        "mechanic": "survival-риск оттока",
        "reward_rub": reward_rub,
        "reasoning": reasoning,
        "target_sku_id": sku.sku_id if sku else None,
        "target_quantity": quantity,
        "deadline_days": deadline_days,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_challenges.py -v -k build_survival_risk_challenge`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add synth/challenges.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: add build_survival_risk_challenge — risk-ranked, template-only challenge builder

No LLM call: ranks the user's own categories by churn risk from a
population Kaplan-Meier curve and returns the rank-th riskiest as a
templated challenge, with a deadline sized from the curve's median.
EOF
)"
```

---

### Task 4: Wire `build_survival_risk_challenge` into `generate_challenge_for_user`

**Files:**
- Modify: `synth/challenges.py` (the `generate_challenge_for_user` function, `synth/challenges.py:958`)
- Modify: `tests/synth/test_challenges.py`

**Interfaces:**
- Consumes: `build_survival_risk_challenge` (Task 3).
- Produces: `generate_challenge_for_user(..., category_curves: dict[str, SurvivalCurve] | None = None)` — new keyword param, default `None`. Consumed by Task 5 (CLI) and Task 9 (web `ChallengeService`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/synth/test_challenges.py`:

```python
def test_generate_challenge_for_user_llm_habit_uses_survival_risk_not_llm(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter must not be called for llm_habit/llm_discovery/generic")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    profile = _profile("bakes_on_weekends", seed=4)
    lines = [l for r in profile["receipts"] for l in r["lines"]]
    top_category = Counter(l["category"] for l in lines).most_common(1)[0][0]
    profile = {
        **profile,
        "category_last_purchase": {top_category: profile["receipts"][0]["purchase_date"]},
    }
    curves = {top_category: fit_km_curve([5, 10], [False, True])}

    results = generate_challenge_for_user(
        profile, _config, model="fake/model", api_key="fake-key", category_curves=curves,
    )
    habit = _by_slot(results)["llm_habit"]
    assert habit["path"] == "personal"
    assert habit["model"] is None
    assert habit["target_categories"] == [top_category]
    assert "prompt" not in habit
    assert "response" not in habit


def test_generate_challenge_for_user_llm_habit_falls_back_without_category_curves():
    profile = _profile("bakes_on_weekends", seed=4)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    habit = _by_slot(results)["llm_habit"]
    discovery = _by_slot(results)["llm_discovery"]
    assert habit["path"] == "generic_fallback"
    assert discovery["path"] == "generic_fallback"


def test_generate_challenge_for_user_dry_run_no_longer_affects_llm_habit_or_discovery():
    """dry_run only ever meant 'skip LLM calls' — llm_habit/llm_discovery
    make none any more, so dry_run must not change their result at all."""
    profile = _profile("bakes_on_weekends", seed=4)
    top_category = Counter(l["category"] for r in profile["receipts"] for l in r["lines"]).most_common(1)[0][0]
    profile = {
        **profile,
        "category_last_purchase": {top_category: profile["receipts"][0]["purchase_date"]},
    }
    curves = {top_category: fit_km_curve([5, 10], [False, True])}

    live = generate_challenge_for_user(profile, _config, model="fake/model", category_curves=curves)
    dry = generate_challenge_for_user(profile, _config, model="fake/model", category_curves=curves, dry_run=True)
    assert _by_slot(live)["llm_habit"]["target_categories"] == _by_slot(dry)["llm_habit"]["target_categories"]
    assert _by_slot(dry)["llm_habit"]["path"] == "personal"
```

Add `from collections import Counter` and `from synth.survival import fit_km_curve` to the test file's imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_challenges.py -v -k "uses_survival_risk_not_llm or falls_back_without_category_curves or dry_run_no_longer_affects"`
Expected: FAIL — `call_openrouter` still gets called for `llm_habit`/`llm_discovery` (old code path), or `TypeError: unexpected keyword argument 'category_curves'`.

- [ ] **Step 3: Implement**

In `synth/challenges.py`, add `category_curves: dict[str, SurvivalCurve] | None = None` to `generate_challenge_for_user`'s signature (after `vibe_month_key`, `:964`):

```python
def generate_challenge_for_user(
    profile: dict,
    config: SynthConfig,
    model: str,
    api_key: str | None = None,
    dry_run: bool = False,
    vibe_month_key: str | None = None,
    category_curves: dict[str, SurvivalCurve] | None = None,
) -> list[dict]:
```

Replace the `generic` slot block (`:1054-1070`, "Drawn FIRST..."):

```python
    # slot: generic — tries the survival-risk pick (rank 2, after llm_habit
    # and llm_discovery's ranks 0/1) first; falls back to the fixed
    # GENERIC_CHALLENGES pool only when there's no purchase history / no
    # fitted curve to rank against (new user, cold start). Drawn FIRST so
    # its fallback pool draw never depends on whether an earlier slot's own
    # fallback already consumed a used_generic_indices slot this cycle.
    generic_risk_challenge = build_survival_risk_challenge(
        profile, config, category_curves or {}, rank=2, slot="generic",
    )
    if generic_risk_challenge is not None:
        results.append({
            "user_id": profile["user_id"], "path": "personal",
            "model": None, "challenge_slot": "generic", **generic_risk_challenge,
        })
    else:
        generic_cycle_index = profile.get("generic_cycle_index", 0)
        offer = _pick_distinct_generic_offer(
            profile["user_id"], config, used_generic_indices, cycle_offset=generic_cycle_index
        )
        results.append({
            "user_id": profile["user_id"], "path": "generic",
            "model": None, "challenge_slot": "generic", **offer,
        })
```

Replace the `allowed_personal_categories` line + `llm_habit`/`llm_discovery` blocks (`:1072-1085`):

```python
    # slots: llm_habit / llm_discovery — the rank-0 and rank-1 riskiest
    # categories (by survival-analysis churn risk) from the user's own
    # purchase history. Deterministic, no LLM call — see
    # `build_survival_risk_challenge`. Falls back to a generic offer when
    # there's no purchase history (cold start) or that rank isn't
    # available (fewer than 2 distinct categories with a fitted curve).
    habit_challenge = build_survival_risk_challenge(
        profile, config, category_curves or {}, rank=0, slot="llm_habit",
    )
    if habit_challenge is not None:
        results.append({
            "user_id": profile["user_id"], "path": "personal",
            "model": None, "challenge_slot": "llm_habit", **habit_challenge,
        })
    else:
        results.append(_generic("llm_habit", "generic_fallback"))

    discovery_challenge = build_survival_risk_challenge(
        profile, config, category_curves or {}, rank=1, slot="llm_discovery",
    )
    if discovery_challenge is not None:
        results.append({
            "user_id": profile["user_id"], "path": "personal",
            "model": None, "challenge_slot": "llm_discovery", **discovery_challenge,
        })
    else:
        results.append(_generic("llm_discovery", "generic_fallback"))
```

Update the function's docstring (`:966-1003`) — replace the paragraph starting "`llm_habit` and `llm_discovery` both call the LLM" with:

```
    `llm_habit`, `llm_discovery`, and `generic` are all
    `build_survival_risk_challenge` picks (ranks 0, 1, 2 by churn risk) —
    no LLM call for any of them. Each falls back to a (slot-distinct)
    generic offer when the user has no purchase history or that rank isn't
    available. `vibe` is the only slot left that calls the LLM.
```

Also update the `CHALLENGE_SLOTS` comment (`:921-925`) to drop "no saturation/receptiveness gate" framing that's no longer the most relevant fact and instead note the risk-based slots:

```python
# The five independent challenge slots every user gets, one attempt each,
# unconditionally. llm_habit/llm_discovery/generic are risk-ranked picks
# from build_survival_risk_challenge (no LLM call); llm_basket is the
# deterministic build_basket_spend_challenge; vibe is the only slot that
# still calls the LLM (see generate_challenge_for_user's docstring).
CHALLENGE_SLOTS = ("llm_habit", "llm_discovery", "llm_basket", "generic", "vibe")
```

- [ ] **Step 4: Run the new tests, then fix the now-broken old tests**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_challenges.py -v`

The 3 new tests from Step 1 now pass, but several pre-existing tests fail because they assumed `llm_habit`/`llm_discovery` call the LLM. Fix them:

1. **Delete** these three test functions entirely (they test LLM-hallucination/JSON-parse-failure handling for `llm_habit`/`llm_discovery`, which can no longer happen since those slots never call the LLM):
   - `test_generate_challenge_for_user_llm_habit_falls_back_on_hallucinated_category`
   - `test_generate_challenge_for_user_llm_habit_personal_path_with_mocked_llm`
   - `test_generate_challenge_for_user_falls_back_on_bad_llm_output`

2. **Update** `test_generate_challenge_for_user_always_returns_five_slots_regardless_of_pattern_strength` (no `category_curves` passed, so `llm_habit`/`llm_discovery` now fall back to generic instead of `"personal_dry_run"`):

```python
def test_generate_challenge_for_user_always_returns_five_slots_regardless_of_pattern_strength(monkeypatch):
    """The receptiveness/saturation gates are gone from the live routing
    function — these three profile classes used to hit three DIFFERENT old
    branches. Now all three get the exact same 5-slot shape. `llm_habit`/
    `llm_discovery`/`llm_basket` all fall back to generic here: no
    `category_curves` is passed (nothing to rank against) and `_profile()`
    never sets `suggested_basket_items` (cold start)."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter should not be called under dry_run")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    for generation_class in ("bakes_on_weekends", "one_off_no_pattern", "already_optimal_no_challenge"):
        profile = _profile(generation_class, seed=1)
        results = generate_challenge_for_user(profile, _config, model="fake/model", dry_run=True)
        assert len(results) == len(CHALLENGE_SLOTS)
        by_slot = _by_slot(results)
        assert set(by_slot) == set(CHALLENGE_SLOTS)
        assert by_slot["llm_habit"]["path"] == "generic_fallback"
        assert by_slot["llm_discovery"]["path"] == "generic_fallback"
        assert by_slot["generic"]["path"] == "generic"
        assert by_slot["vibe"]["path"] == "personal_dry_run"
        assert by_slot["llm_basket"]["path"] == "generic_fallback"
```

3. **Rewrite** `test_generate_challenge_for_user_llm_slots_carry_their_own_prompt_and_response` — only `vibe` calls the LLM now:

```python
def test_generate_challenge_for_user_only_vibe_carries_prompt_and_response(monkeypatch):
    """Regression for the audit-log mismatch: only `vibe` still calls the
    LLM, so only it should carry prompt/response on its result dict —
    llm_habit/llm_discovery/generic are all deterministic risk picks now
    and must not carry stale/borrowed prompt+response fields."""
    profile = _profile("bakes_on_weekends", seed=4)

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return json.dumps({
            "challenge_title": "Vibe title",
            "description": "vibe desc",
            "target_categories": ["бакалея"],
            "mechanic": "скидка",
            "reward_rub": 20,
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    by_slot = _by_slot(results)

    assert "prompt" in by_slot["vibe"] and "response" in by_slot["vibe"]
    for slot in ("llm_habit", "llm_discovery", "generic"):
        assert "prompt" not in by_slot[slot]
        assert "response" not in by_slot[slot]
```

4. **Rename + lightly re-document** `test_generate_challenge_for_user_all_llm_fallbacks_get_distinct_generic_offers` (the test body is unchanged and still passes: with no `category_curves` passed, `llm_habit`/`llm_discovery`/`generic` fall back for lack of data, `llm_basket` falls back for lack of suggested items, and `vibe`'s mocked `call_openrouter` raises — all five reach `_generic`/`_pick_distinct_generic_offer`, which still guarantees distinctness):

```python
def test_generate_challenge_for_user_without_curves_or_working_llm_gets_distinct_generic_offers(monkeypatch):
    """Every slot without personalization data (no category_curves for the
    three risk-ranked slots, no suggested_basket_items for llm_basket) or a
    working LLM call (vibe, mocked to fail here) falls back to
    `_pick_distinct_generic_offer` — which must still hand out 5 distinct
    offers, not silently repeat one."""
    def fail_if_called(*args, **kwargs):
        raise RuntimeError("simulated LLM outage")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    profile = _profile("bakes_on_weekends", seed=4)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    assert len(results) == len(CHALLENGE_SLOTS)
    assert len({r["challenge_title"] for r in results}) == len(CHALLENGE_SLOTS)
    assert len({r["target_sku_id"] for r in results}) == len(CHALLENGE_SLOTS)
```

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_challenges.py -v`
Expected: PASS (entire file, no failures, no skips)

- [ ] **Step 5: Commit**

```bash
git add synth/challenges.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: route llm_habit/llm_discovery/generic through survival risk, not LLM

generate_challenge_for_user gains category_curves; the three slots now
use build_survival_risk_challenge exclusively, with the existing
generic-pool fallback for cold-start users. Only vibe still calls an LLM.
EOF
)"
```

---

### Task 5: Wire population curves into the offline CLI path

**Files:**
- Modify: `synth/challenges.py` (`generate_challenges`, `:1144`; `_replace_legacy_slots_with_deterministic`, `:1161`)
- Modify: `synth/cli.py` (help text only, `:75-95`)
- Test: `tests/synth/test_challenges.py`

**Interfaces:**
- Consumes: `fit_population_curves`, `purchase_dates_from_profiles` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/synth/test_challenges.py
def test_generate_challenges_fits_population_curves_once_and_uses_them(monkeypatch):
    """The CLI batch entry point must fit curves from ALL profiles passed
    to it and actually use them — otherwise re-running it for hit-rate
    scoring would silently exercise only the cold-start fallback path."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("no LLM call expected for llm_habit/llm_discovery/generic")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    profiles = [_profile("bakes_on_weekends", seed=s) for s in (1, 2, 3)]

    from synth.challenges import generate_challenges

    results = generate_challenges(profiles, _config, model="fake/model", dry_run=True)
    by_user = {}
    for r in results:
        by_user.setdefault(r["user_id"], {})[r["challenge_slot"]] = r

    # At least one profile has enough purchase history that llm_habit
    # should resolve to a real risk pick rather than the cold-start
    # fallback, now that curves are actually being fit and passed through.
    assert any(
        slots["llm_habit"]["path"] == "personal" for slots in by_user.values()
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_challenges.py -v -k fits_population_curves_once`
Expected: FAIL (every `llm_habit` result is `"generic_fallback"` — `generate_challenges` doesn't fit/pass curves yet)

- [ ] **Step 3: Implement**

In `synth/challenges.py`, update the import block at the top to add:

```python
from synth.survival import SurvivalCurve, fit_population_curves, purchase_dates_from_profiles
```

Replace `generate_challenges` (`:1144-1158`):

```python
def generate_challenges(
    profiles: list[dict],
    config: SynthConfig,
    model: str,
    api_key: str | None = None,
    dry_run: bool = False,
    delay_seconds: float = 0.0,
) -> list[dict]:
    category_curves = fit_population_curves(
        purchase_dates_from_profiles(profiles), as_of=date.today()
    )
    results: list[dict] = []
    for i, profile in enumerate(profiles):
        batch = generate_challenge_for_user(
            profile, config, model, api_key, dry_run, category_curves=category_curves,
        )
        results.extend(_replace_legacy_slots_with_deterministic(profile, config, batch))
        if not dry_run and delay_seconds > 0 and i < len(profiles) - 1:
            time.sleep(delay_seconds)
    return results
```

In `_replace_legacy_slots_with_deterministic` (`:1161-1195`), remove the now-redundant `generic` → `category_expansion` override — the `generic` slot already comes out of `generate_challenge_for_user` in its final form (risk pick or cold-start pool). Change the `replacements` tuple:

```python
    replacements = (
        ("llm_basket", "spend_threshold", build_spend_threshold_challenge),
    )
```

(Leave the rest of the function and the `llm_basket` → `spend_threshold` replacement exactly as-is — unrelated to this feature.)

In `synth/cli.py`, update the two `--dry-run`/`challenges` help strings (`:75-95`) that describe llm_habit/llm_discovery as LLM-backed:

```python
    chal_parser = subparsers.add_parser(
        "challenges",
        help="Generate exactly 5 challenges per profile, unconditionally (llm_habit, llm_discovery, "
             "generic slots are risk-ranked from a population survival curve, no LLM call; llm_basket is "
             "a deterministic spend-threshold mechanic; vibe is the only slot that calls an LLM).",
    )
```

```python
    chal_parser.add_argument(
        "--dry-run", action="store_true",
        help="Make no real LLM call for the 'vibe' slot (returns a 'personal_dry_run' placeholder "
             "instead) — llm_habit/llm_discovery/generic/llm_basket never call an LLM regardless of "
             "this flag.",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/synth/test_challenges.py -v`
Expected: PASS (entire file)

- [ ] **Step 5: Commit**

```bash
git add synth/challenges.py synth/cli.py tests/synth/test_challenges.py
git commit -m "$(cat <<'EOF'
feat: fit and thread population survival curves through the CLI batch path

generate_challenges now fits curves once from all passed-in profiles and
passes them to every generate_challenge_for_user call; drops the CLI's
own now-redundant generic -> category_expansion override.
EOF
)"
```

---

### Task 6: `ChallengeAdapter.build_profile` — full history + `category_last_purchase`

**Files:**
- Modify: `web/src/webx5/services/challenge_adapter.py:96-202`
- Test: `web/tests/webx5/services/test_challenge_adapter.py`

**Interfaces:**
- Produces: `build_profile(...)`'s returned dict gains a `"category_last_purchase": dict[str, str]` key (ISO date strings); the 90-day cutoff is removed. Consumed by Task 4's `build_survival_risk_challenge` call sites once wired through `ChallengeService` in Task 9.

- [ ] **Step 1: Write the failing test**

```python
# add to web/tests/webx5/services/test_challenge_adapter.py
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from webx5.services.challenge_adapter import ChallengeAdapter


def test_build_profile_reads_full_history_and_computes_category_last_purchase():
    adapter = ChallengeAdapter(task_repo=MagicMock(), basket_repo=MagicMock())
    user_id = uuid.uuid4()

    user = MagicMock(id=user_id, vibe_type=None)

    receipt_old = MagicMock(id=uuid.uuid4(), purchase_date=datetime(2020, 1, 1, tzinfo=UTC), channel="offline")
    receipt_recent = MagicMock(id=uuid.uuid4(), purchase_date=datetime(2026, 8, 1, tzinfo=UTC), channel="offline")

    product = MagicMock()
    product.name = "Молоко 3.2%"
    category = MagicMock()
    category.name = "молочные продукты и яйца"

    def make_item():
        item = MagicMock()
        item.base_price_at_purchase = "80.00"
        item.paid_price = "80.00"
        item.quantity = 1
        item.discount_id = None
        return item

    query_results = iter([
        [receipt_old, receipt_recent],
        [(make_item(), product, category)],
        [(make_item(), product, category)],
    ])

    def execute(stmt):
        rows = next(query_results)
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        result.all.return_value = rows
        return result

    session = MagicMock()
    session.get.return_value = user
    session.execute.side_effect = execute

    adapter.task_repo.count_tasks_for_slot.return_value = 0
    adapter.basket_repo.suggest_items.return_value = []

    config = MagicMock(category_economics=[])
    profile = adapter.build_profile(session, user_id, config)

    assert profile["category_last_purchase"] == {"молочные продукты и яйца": "2026-08-01"}
    assert len(profile["receipts"]) == 2  # spans >90 days — the cutoff is gone
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/services/test_challenge_adapter.py -v -k category_last_purchase`
Expected: FAIL with `KeyError: 'category_last_purchase'`

- [ ] **Step 3: Implement**

In `web/src/webx5/services/challenge_adapter.py`, replace the cutoff + query (`:121-133`):

```python
        # Read the user's FULL purchase history — survival-risk scoring
        # (category_last_purchase below) needs the true last-purchase date
        # per category; a 90-day window would truncate long repurchase-cycle
        # categories and understate their risk.
        rows = (
            session.execute(
                select(Receipt)
                .where(Receipt.loyalty_card_id == user_id)
                .order_by(Receipt.purchase_date.asc())
            )
            .scalars()
            .all()
        )
```

In the per-line loop (`:137-150`), add `category_last_purchase` tracking alongside the existing `habit_counter`:

```python
        receipts_dicts: list[dict] = []
        habit_counter: Counter = Counter()
        category_last_purchase: dict[str, str] = {}
        for r in rows:
            lines: list[dict] = []
            total_rub = Decimal(0)
            items = session.execute(
                select(ReceiptItem, Product, Category)
                .join(Product, ReceiptItem.product_id == Product.id)
                .join(Category, Product.category_id == Category.id)
                .where(ReceiptItem.receipt_id == r.id)
            ).all()
            for ri, product, category in items:
                cat_name = category.name
                habit_counter[cat_name] += 1
                # `rows` is ordered ascending by purchase_date, so the last
                # assignment for a category during this loop IS its true
                # most-recent purchase date — no max() needed.
                category_last_purchase[cat_name] = r.purchase_date.date().isoformat()
```

(Everything else inside the `for ri, product, category in items:` loop is unchanged.)

Add the new field to the returned profile dict (`:189-199`):

```python
        profile: dict = {
            "user_id": str(user_id),
            "chain": "Пятёрочка",
            "segment": "unknown",
            "family_size": 1,
            "habitual_categories": habitual,
            "category_last_purchase": category_last_purchase,
            "receipts": receipts_dicts,
            "vibe_category": vibe_category,
            "suggested_basket_items": suggested_basket_items,
            "generic_cycle_index": generic_cycle_index,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/services/test_challenge_adapter.py -v`
Expected: PASS (entire file)

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/services/challenge_adapter.py web/tests/webx5/services/test_challenge_adapter.py
git commit -m "$(cat <<'EOF'
feat: build_profile reads full purchase history, adds category_last_purchase

Drops the 90-day receipt cutoff (survival risk needs the true
last-purchase date per category) and computes it alongside the existing
habit_counter pass — no extra query.
EOF
)"
```

---

### Task 7: `SurvivalRepository.fetch_purchase_dates`

**Files:**
- Create: `web/src/webx5/crud/survival.py`
- Create: `web/tests/webx5/crud/__init__.py` (empty)
- Test: `web/tests/webx5/crud/test_survival.py`

**Interfaces:**
- Produces: `SurvivalRepository.fetch_purchase_dates(session: Session) -> dict[str, dict[str, list[date]]]`. Consumed by Task 8.

- [ ] **Step 1: Write the failing test**

```python
# web/tests/webx5/crud/test_survival.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from webx5.crud.survival import SurvivalRepository


def test_fetch_purchase_dates_groups_by_user_and_category_deduped():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    rows = [
        (user_a, "молочные продукты и яйца", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        (user_a, "молочные продукты и яйца", datetime(2026, 1, 1, tzinfo=timezone.utc)),  # same-day dup
        (user_a, "молочные продукты и яйца", datetime(2026, 1, 11, tzinfo=timezone.utc)),
        (user_b, "овощи", datetime(2026, 1, 5, tzinfo=timezone.utc)),
    ]
    session = MagicMock()
    session.execute.return_value.all.return_value = rows

    result = SurvivalRepository().fetch_purchase_dates(session)

    assert result[str(user_a)]["молочные продукты и яйца"] == [
        datetime(2026, 1, 1, tzinfo=timezone.utc).date(),
        datetime(2026, 1, 11, tzinfo=timezone.utc).date(),
    ]
    assert result[str(user_b)]["овощи"] == [datetime(2026, 1, 5, tzinfo=timezone.utc).date()]


def test_fetch_purchase_dates_returns_empty_dict_for_no_rows():
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    assert SurvivalRepository().fetch_purchase_dates(session) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/crud/test_survival.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'webx5.crud.survival'`

- [ ] **Step 3: Implement**

```python
# web/src/webx5/crud/survival.py
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from webx5.entities.category import Category
from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem


class SurvivalRepository:
    def fetch_purchase_dates(self, session: Session) -> dict[str, dict[str, list[date]]]:
        """Every (user, category, purchase date) triple across ALL users'
        FULL receipt history — the population-level input
        `synth.survival.fit_population_curves` needs to fit one Kaplan-Meier
        curve per category.

        `.distinct()` collapses multiple line items of the same category on
        one receipt into a single row; the `set()` below also collapses two
        separate same-day receipts in the same category, since a same-day
        repeat purchase isn't a distinct repurchase event at the day
        granularity this model uses.
        """
        rows = session.execute(
            select(Receipt.loyalty_card_id, Category.name, Receipt.purchase_date)
            .join(ReceiptItem, ReceiptItem.receipt_id == Receipt.id)
            .join(Product, ReceiptItem.product_id == Product.id)
            .join(Category, Product.category_id == Category.id)
            .where(Receipt.loyalty_card_id.is_not(None))
            .distinct()
        ).all()

        by_user: dict[str, dict[str, set[date]]] = {}
        for loyalty_card_id, category_name, purchase_date in rows:
            by_category = by_user.setdefault(str(loyalty_card_id), {})
            by_category.setdefault(category_name, set()).add(purchase_date.date())

        return {
            user_id: {category: sorted(dates) for category, dates in by_category.items()}
            for user_id, by_category in by_user.items()
        }
```

```python
# web/tests/webx5/crud/__init__.py
```
(empty file)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/crud/test_survival.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/crud/survival.py web/tests/webx5/crud/__init__.py web/tests/webx5/crud/test_survival.py
git commit -m "$(cat <<'EOF'
feat: add SurvivalRepository.fetch_purchase_dates

Aggregates every user's full purchase history by category across the
whole DB — the population-level input the survival curve fit needs.
EOF
)"
```

---

### Task 8: `SurvivalCurveStore` service + wiring into `core/challenges.py`

**Files:**
- Create: `web/src/webx5/services/survival.py`
- Modify: `web/src/webx5/core/challenges.py`
- Test: `web/tests/webx5/services/test_survival.py`

**Interfaces:**
- Consumes: `SurvivalRepository` (Task 7), `fit_population_curves` (Task 2).
- Produces: `SurvivalCurveStore(db: Database, repo: SurvivalRepository | None = None)` with a `.curves -> dict[str, SurvivalCurve]` property, lazily fetched and cached for the process's life. Consumed by Task 9.

- [ ] **Step 1: Write the failing test**

```python
# web/tests/webx5/services/test_survival.py
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock

from webx5.services.survival import SurvivalCurveStore


def test_curves_are_fetched_lazily_and_cached():
    repo = MagicMock()
    repo.fetch_purchase_dates.return_value = {
        "u1": {"молоко": [date(2026, 1, 1), date(2026, 1, 11)]},
    }

    @contextmanager
    def fake_session():
        yield MagicMock()

    db = MagicMock()
    db.get_sync_session.side_effect = fake_session

    store = SurvivalCurveStore(db=db, repo=repo)
    repo.fetch_purchase_dates.assert_not_called()  # not called on construction

    curves = store.curves
    assert "молоко" in curves
    repo.fetch_purchase_dates.assert_called_once()

    store.curves  # second access
    repo.fetch_purchase_dates.assert_called_once()  # still just once — cached
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/services/test_survival.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'webx5.services.survival'`

- [ ] **Step 3: Implement**

```python
# web/src/webx5/services/survival.py
from __future__ import annotations

from datetime import date

from synth.survival import SurvivalCurve, fit_population_curves
from webx5.crud.survival import SurvivalRepository
from webx5.database.database import Database


class SurvivalCurveStore:
    """Population-level Kaplan-Meier category-risk curves, fit once per
    process and cached in memory for its whole life — no TTL/periodic
    refresh (see `docs/superpowers/specs/2026-09-06-challenge-survival-risk-design.md`
    §2 for why). Fetching is lazy (on first `.curves` access, not at
    construction) so building this object never opens a DB connection by
    itself — `core/challenges.py`, which constructs it, must not gain a
    DB call at import time.
    """

    def __init__(self, db: Database, repo: SurvivalRepository | None = None) -> None:
        self._db = db
        self._repo = repo if repo is not None else SurvivalRepository()
        self._curves: dict[str, SurvivalCurve] | None = None

    @property
    def curves(self) -> dict[str, SurvivalCurve]:
        if self._curves is None:
            with self._db.get_sync_session() as session:
                purchase_dates = self._repo.fetch_purchase_dates(session)
            self._curves = fit_population_curves(purchase_dates, as_of=date.today())
        return self._curves
```

In `web/src/webx5/core/challenges.py`, add imports and construct the store:

```python
from webx5.core.db import db
from webx5.services.survival import SurvivalCurveStore
```

```python
# --- survival risk curves — lazy, fit once on first use ---
survival_curve_store = SurvivalCurveStore(db=db)
```

(Add this right before the `# --- services ---` block, after `synth_config = get_synth_config()`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/services/test_survival.py -v`
Expected: PASS

Also sanity-check the wiring module still imports cleanly with no DB call:

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run python -c "import webx5.core.challenges"`
Expected: no exception (this only works if `DATABASE_URL` env var is set for `webx5.core.db`, matching the existing behavior of importing `webx5.core.challenges` today — this step doesn't change that pre-existing requirement, it only confirms the NEW `SurvivalCurveStore(db=db)` line doesn't itself add a query).

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/services/survival.py web/src/webx5/core/challenges.py web/tests/webx5/services/test_survival.py
git commit -m "$(cat <<'EOF'
feat: add SurvivalCurveStore, wired into the challenges composition root

Lazily fits population survival curves once per process on first access,
keeping core/challenges.py free of DB calls at import time.
EOF
)"
```

---

### Task 9: `ChallengeService` — thread curves through, retire the web-boundary override

**Files:**
- Modify: `web/src/webx5/services/challenge.py`
- Modify: `web/tests/webx5/services/test_challenge_service.py`

**Interfaces:**
- Consumes: `SurvivalCurveStore` (Task 8); `generate_challenge_for_user`'s new `category_curves` param (Task 4).
- Produces: `ChallengeService.__init__` gains a required `curve_store: SurvivalCurveStore` param.

- [ ] **Step 1: Write the failing test**

```python
# add to web/tests/webx5/services/test_challenge_service.py
def test_generate_batch_passes_curve_store_curves_to_generate_challenge_for_user():
    service, task_repo, log_repo, adapter = _service_with_mocks()
    service.curve_store.curves = {"молоко": "sentinel-curve"}

    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return _batch_all_five()

    with patch("webx5.services.challenge.generate_challenge_for_user", side_effect=fake_generate), \
         patch("webx5.services.challenge.capture_openrouter_io") as mock_capture:
        mock_capture.return_value.__enter__.return_value = {}
        service.generate_batch(MagicMock(), uuid.uuid4(), count=5)

    assert captured["category_curves"] == {"молоко": "sentinel-curve"}
```

Update `_service_with_mocks()` to construct `ChallengeService` with a `curve_store`:

```python
def _service_with_mocks():
    task_repo = MagicMock()
    task_repo.get_active_for_user.return_value = []
    task_repo.get_last_criterion_per_slot.return_value = {}
    log_repo = MagicMock()
    log_repo.record.return_value = uuid.uuid4()
    adapter = MagicMock()
    adapter.build_profile.return_value = {"user_id": "u", "receipts": []}
    adapter.persist_challenge.side_effect = lambda session, uid, r: uuid.uuid4()
    adapter.resolve_criterion.side_effect = lambda session, r: ("category", uuid.uuid4())
    adapter.resolve_category_id.side_effect = lambda session, criterion_type, criterion_entity_id: criterion_entity_id
    synth_config = MagicMock()
    curve_store = MagicMock()
    curve_store.curves = {}

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
```

Also delete `test_deterministic_mechanics_replace_legacy_slots` (it tests the `_use_deterministic_mechanics` function this task removes) and change the top import:

```python
from webx5.services.challenge import ChallengeService
```

(drop `_use_deterministic_mechanics` from that import line)

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/services/test_challenge_service.py -v`
Expected: FAIL — `TypeError: ChallengeService.__init__() got an unexpected keyword argument 'curve_store'`

- [ ] **Step 3: Implement**

In `web/src/webx5/services/challenge.py`:

Update the import block (drop `build_category_expansion_challenge`, no longer used once `_use_deterministic_mechanics` is removed):

```python
from synth.challenges import CHALLENGE_SLOTS, generate_challenge_for_user
```

Update `_SLOTS_WITHOUT_NATURAL_VARIATION` (`:38-40`) — `"category_expansion"` and `"spend_threshold"` are dead names on this web-only path once `_use_deterministic_mechanics` is gone (they were only ever produced by that function); `"generic"` now carries the same day-by-day natural variation as `llm_habit`/`llm_discovery` (it's the same risk-ranked mechanism), so it moves out of this set alongside them:

```python
# Slots whose pick has no natural source of cycle-to-cycle variation — see
# the cross-cycle-repeat guard in `ChallengeService.generate_batch` below.
# `llm_basket` is deterministic (`build_basket_spend_challenge`) with no
# rotation of its own, so it's the only slot left here — llm_habit/
# llm_discovery/generic are all survival-risk picks now, and risk changes
# day by day as days-since-last-purchase grows, giving them the same kind
# of natural variation the LLM-driven versions used to get from the LLM's
# own non-determinism.
_SLOTS_WITHOUT_NATURAL_VARIATION = frozenset({"llm_basket"})
```

Delete the `_use_deterministic_mechanics` function entirely (`:43-87`).

Update `ChallengeService.__init__` (`:90-105`):

```python
class ChallengeService:
    def __init__(
        self,
        task_repo: TaskRepository,
        log_repo: ChallengeLogRepository,
        adapter: ChallengeAdapter,
        synth_config: SynthConfig,
        model: str,
        api_key: str,
        curve_store: SurvivalCurveStore,
    ) -> None:
        self.task_repo = task_repo
        self.log_repo = log_repo
        self.adapter = adapter
        self.synth_config = synth_config
        self.model = model
        self.api_key = api_key
        self.curve_store = curve_store
```

Add the import for the type hint, near the other `webx5.services` imports:

```python
from webx5.services.survival import SurvivalCurveStore
```

Replace the `generate_challenge_for_user` call + `_use_deterministic_mechanics` call in `generate_batch` (`:187-198`):

```python
        try:
            with capture_openrouter_io() as capture:
                script_results = generate_challenge_for_user(
                    profile=profile,
                    config=self.synth_config,
                    model=self.model,
                    api_key=self.api_key or None,
                    dry_run=False,
                    category_curves=self.curve_store.curves,
                )
            if capture.get("system") is not None:
```

Update the composition root (`web/src/webx5/core/challenges.py`), which already imports `db`/`SurvivalCurveStore` from Task 8 — pass the store into `ChallengeService`:

```python
challenge_service = ChallengeService(
    task_repo=task_repo,
    log_repo=challenge_log_repo,
    adapter=challenge_adapter,
    synth_config=synth_config,
    model=CHALLENGE_LLM_MODEL,
    api_key=OPENROUTER_API_KEY,
    curve_store=survival_curve_store,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/services/test_challenge_service.py -v`
Expected: PASS (entire file)

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/services/challenge.py web/src/webx5/core/challenges.py web/tests/webx5/services/test_challenge_service.py
git commit -m "$(cat <<'EOF'
feat: thread SurvivalCurveStore through ChallengeService, retire web override

generate_batch now passes curve_store.curves into generate_challenge_for_user
directly; _use_deterministic_mechanics (generic -> category_expansion) is
gone since generate_challenge_for_user already returns the generic slot
in its final risk-ranked form.
EOF
)"
```

---

### Task 10: `deadline_days` plumbing in `persist_challenge`

**Files:**
- Modify: `web/src/webx5/services/challenge_adapter.py:293-338`
- Test: `web/tests/webx5/services/test_challenge_adapter.py`

**Interfaces:**
- Consumes: `script_result["deadline_days"]` (set by `build_survival_risk_challenge`, Task 3).

- [ ] **Step 1: Write the failing tests**

```python
# add to web/tests/webx5/services/test_challenge_adapter.py
from datetime import UTC, datetime
from unittest.mock import patch


def test_persist_challenge_uses_deadline_days_when_present():
    adapter = ChallengeAdapter(task_repo=MagicMock(), basket_repo=MagicMock())
    adapter.task_repo.create.return_value = MagicMock(id=uuid.uuid4())
    adapter.task_item_repo = MagicMock()
    session = MagicMock()

    with patch.object(adapter, "resolve_criterion", return_value=("category", uuid.uuid4())):
        adapter.persist_challenge(
            session, uuid.uuid4(),
            {"challenge_title": "T", "reward_rub": 10, "deadline_days": 14, "challenge_slot": "llm_habit"},
        )

    _, kwargs = adapter.task_repo.create.call_args
    assert kwargs["deadline"] is not None
    assert 13 <= (kwargs["deadline"] - datetime.now(UTC)).days <= 14


def test_persist_challenge_leaves_deadline_none_when_absent():
    adapter = ChallengeAdapter(task_repo=MagicMock(), basket_repo=MagicMock())
    adapter.task_repo.create.return_value = MagicMock(id=uuid.uuid4())
    adapter.task_item_repo = MagicMock()
    session = MagicMock()

    with patch.object(adapter, "resolve_criterion", return_value=("category", uuid.uuid4())):
        adapter.persist_challenge(session, uuid.uuid4(), {"challenge_title": "T", "reward_rub": 10})

    _, kwargs = adapter.task_repo.create.call_args
    assert kwargs["deadline"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/services/test_challenge_adapter.py -v -k deadline_days`
Expected: FAIL — `task_repo.create` is called without a `deadline` kwarg at all today, so `kwargs["deadline"]` raises `KeyError`.

- [ ] **Step 3: Implement**

In `web/src/webx5/services/challenge_adapter.py::persist_challenge`, right before the `task = self.task_repo.create(...)` call (after the existing `qty_target = max(qty_target, 1)` line, `:322`):

```python
        qty_target = max(qty_target, 1)

        deadline = None
        deadline_days = script_result.get("deadline_days")
        if deadline_days is not None:
            deadline = datetime.now(UTC) + timedelta(days=int(deadline_days))

        task = self.task_repo.create(
            session,
            loyalty_card_id=user_id,
            criterion_type=criterion_type,
            criterion_entity_id=criterion_entity_id,
            quantity_target=qty_target,
            title=str(script_result.get("challenge_title", "Challenge")),
            description=str(script_result.get("description", "")),
            mechanic=str(script_result.get("mechanic", "")),
            reward_rub=reward_rub,
            reasoning=script_result.get("reasoning"),
            path=str(script_result.get("path", "personal")),
            model=script_result.get("model"),
            challenge_slot=script_result.get("challenge_slot"),
            deadline=deadline,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/webx5/services/test_challenge_adapter.py -v`
Expected: PASS (entire file)

- [ ] **Step 5: Run the FULL test suite (both packages) to confirm nothing else broke**

Run:
```bash
cd /Users/dimonzhi/Documents/proga/x5hack && poetry run pytest tests/ -v
cd /Users/dimonzhi/Documents/proga/x5hack/web && poetry run pytest tests/ -v
```
Expected: PASS, 0 failures, in both.

- [ ] **Step 6: Commit**

```bash
git add web/src/webx5/services/challenge_adapter.py web/tests/webx5/services/test_challenge_adapter.py
git commit -m "$(cat <<'EOF'
feat: size challenge deadlines from survival-curve median when provided

persist_challenge reads an optional deadline_days from the script result
(set by build_survival_risk_challenge) instead of always defaulting to 7
days; every other slot's behavior is unchanged.
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** §1 KM estimator → Task 1. §2 population curve store → Tasks 2, 7, 8 (with the documented `core/` → `services/` layer correction). §3 profile features → Task 6. §4 builder → Task 3. §5 `generate_challenge_for_user` wiring (web + implicitly CLI) → Tasks 4, 5, 9. §6 deadline plumbing → Task 10. §7 fallback/cold start → covered inline in Tasks 3/4 (rank-exceeds-available and no-history cases). Hit-rate re-scoring risk noted in the spec is an operational follow-up, not a code task — out of this plan by the spec's own words.
- **Type consistency checked:** `SurvivalCurve`/`fit_km_curve` (Task 1) → `fit_population_curves`/`purchase_dates_from_profiles` (Task 2) → `build_survival_risk_challenge` (Task 3) → `generate_challenge_for_user(category_curves=...)` (Task 4) → `SurvivalRepository.fetch_purchase_dates` (Task 7) → `SurvivalCurveStore.curves` (Task 8) → `ChallengeService(curve_store=...)` (Task 9) all use the identical `dict[str, SurvivalCurve]` / `dict[str, dict[str, list[date]]]` shapes throughout — no renamed fields between tasks.
- **No placeholders:** every step has runnable code; test-fixup steps in Task 4 name exact pre-existing test functions to delete/rewrite with full replacement bodies, not descriptions.
