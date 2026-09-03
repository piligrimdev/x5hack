# Chains and Segments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the synthetic-data generator so every user/profile carries a chain (Пятёрочка/Перекрёсток/Чижик) and a demographic segment (5 groups), with receipt totals calibrated per chain×segment via multipliers instead of one flat average.

**Architecture:** Two new config-driven lookup tables (`ChainConfig`, `SegmentConfig`) added to `synth/config.py`. A new `assign_chains_and_segments()` in `synth/entities.py` draws chain (uniform) then segment (chain-weighted) per user, on its own seed stream. `generate_receipts_for_user` in `synth/receipts.py` gains an optional `price_multiplier` that scales `avg_receipt_total_rub` only (never frequency). `population()` and `reference_profiles()` wire the assignment + multiplier together and add `chain`/`segment` fields to their output records — following the same pattern `family_size` already uses (looked up and merged into the output dict, not added to the `User` dataclass itself).

**Tech Stack:** Same as the base plan — Python 3.11+, PyYAML, pytest, stdlib only.

**Spec:** `docs/superpowers/specs/2026-09-03-synthetic-data-chains-segments-design.md` (extends `docs/superpowers/specs/2026-09-03-synthetic-data-schema-design.md`)

## Global Constraints

- The three chains and five segments, and every percentage/multiplier attached to them, come verbatim from the spec's tables — do not round, adjust, or "improve" any of these numbers; they're either the user's proprietary data or the spec's already-derived-and-approved multipliers.
- `price_multiplier(user) = segment.price_multiplier × chain.price_multiplier`, applied only to `avg_receipt_total_rub` inside `generate_receipts_for_user` — `purchases_per_month_mean`/`stddev` and `offline_share` stay shared, unscaled by chain or segment (spec's Calibration formula section).
- No category-vocabulary or category-preference differences by chain or segment — every user still draws from the same 22-category config regardless of chain/segment (spec's Out of scope section).
- All random generation stays seeded and deterministic. `assign_chains_and_segments` must use a seed stream that never collides with: the raw `seed` (already used by `assign_households` in both `population()` and `reference_profiles()`), or the `seed*4 + i*4 + {1,2}` (population's habit/receipt streams) / `seed*4 + i*4 + {3,4}` (reference_profiles' archetype/receipt streams) per-user families. Use `seed + 900_000_001` in `population()` and `seed + 900_000_002` in `reference_profiles()` — two different large offsets, disjoint from each other and from every existing stream for any realistic `seed`/`i` (see math notes doc §1 for why the existing streams are disjoint from each other; this follows the same reasoning).
- Do not run `git init`, `git add`, `git commit`, or `git push` at any point in this plan — the user handles all git operations directly. Each task ends with a review step (`git status`/`git diff` if a repo exists, otherwise just re-reading the changed files) instead of a commit step.

---

## File Structure

```
config/synth_schema.yaml          # add chains: and segments: top-level blocks
synth/
  config.py                       # add ChainConfig, SegmentConfig; SynthConfig.chains/segments
  entities.py                     # add assign_chains_and_segments()
  receipts.py                     # add price_multiplier param to generate_receipts_for_user
  population.py                   # wire in chain/segment assignment + price_multiplier
  reference_profiles.py           # wire in chain/segment assignment + price_multiplier
tests/synth/
  test_config.py                  # extend: chains/segments parse correctly
  test_entities.py                # extend: assign_chains_and_segments
  test_receipts.py                # extend: price_multiplier scales avg_receipt_total_rub
  test_population.py              # extend: chain/segment in output, weights respected
  test_reference_profiles.py      # extend: same, for reference profiles
```

No new files — every change lands in an existing, already-reviewed module, each still with its single existing responsibility (`config.py` only parses config, `entities.py` only builds entity/assignment logic, `receipts.py` only generates receipts, `population.py`/`reference_profiles.py` only orchestrate).

---

### Task 1: Config — `ChainConfig`, `SegmentConfig`, YAML data

**Files:**
- Modify: `config/synth_schema.yaml`
- Modify: `synth/config.py`
- Modify: `tests/synth/test_config.py`

**Interfaces:**
- Produces: `synth.config.ChainConfig(name: str, price_multiplier: float, segment_weights: dict[str, float])`, `synth.config.SegmentConfig(name: str, price_multiplier: float)`, and `SynthConfig.chains: list[ChainConfig]` / `SynthConfig.segments: list[SegmentConfig]`, populated by the existing `load_config()`.

- [ ] **Step 1: Add `chains:` and `segments:` blocks to `config/synth_schema.yaml`**

Append at the end of the file:

```yaml
chains:
  - name: "Пятёрочка"
    price_multiplier: 1.0
    segment_weights:
      "Молодёжь": 0.37
      "Взрослые с вредными привычками": 0.05
      "Взрослые с детьми до 3х лет": 0.26
      "Зрелые": 0.21
      "Старшие": 0.11
  - name: "Перекрёсток"
    price_multiplier: 1.25
    segment_weights:
      "Молодёжь": 0.31
      "Взрослые с вредными привычками": 0.03
      "Взрослые с детьми до 3х лет": 0.26
      "Зрелые": 0.32
      "Старшие": 0.09
  - name: "Чижик"
    price_multiplier: 0.75
    segment_weights:
      "Молодёжь": 0.27
      "Взрослые с вредными привычками": 0.04
      "Взрослые с детьми до 3х лет": 0.28
      "Зрелые": 0.24
      "Старшие": 0.18

segments:
  - name: "Молодёжь"
    price_multiplier: 0.75
  - name: "Взрослые с вредными привычками"
    price_multiplier: 1.0
  - name: "Взрослые с детьми до 3х лет"
    price_multiplier: 1.0
  - name: "Зрелые"
    price_multiplier: 1.4
  - name: "Старшие"
    price_multiplier: 0.78
```

Also bump `version: "0.2.0"` to `version: "0.3.0"` at the top of the file, and add a one-line comment above it noting what changed (same style as the existing `0.2.0` changelog comment already in the file):

```yaml
version: "0.3.0"
# 0.3.0 (2026-09-03): added chains (Пятёрочка/Перекрёсток/Чижик) and
# demographic segments, with per-chain segment distribution and
# segment/chain price multipliers. See
# docs/superpowers/specs/2026-09-03-synthetic-data-chains-segments-design.md
```

- [ ] **Step 2: Write the failing test**

```python
# append to tests/synth/test_config.py
def test_load_config_parses_chains_and_segments():
    config = load_config("config/synth_schema.yaml")
    assert config.version == "0.3.0"
    assert len(config.chains) == 3
    assert len(config.segments) == 5

    chain_names = {c.name for c in config.chains}
    assert chain_names == {"Пятёрочка", "Перекрёсток", "Чижик"}

    segment_names = {s.name for s in config.segments}
    assert segment_names == {
        "Молодёжь",
        "Взрослые с вредными привычками",
        "Взрослые с детьми до 3х лет",
        "Зрелые",
        "Старшие",
    }

    pyaterochka = next(c for c in config.chains if c.name == "Пятёрочка")
    assert pyaterochka.price_multiplier == 1.0
    assert set(pyaterochka.segment_weights.keys()) == segment_names
    assert abs(pyaterochka.segment_weights["Молодёжь"] - 0.37) < 1e-9

    zrelye = next(s for s in config.segments if s.name == "Зрелые")
    assert zrelye.price_multiplier == 1.4
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/synth/test_config.py -v`
Expected: FAIL — `SynthConfig.__init__() got an unexpected keyword argument` or `AttributeError` (no `chains`/`segments` field yet), and `config.version == "0.3.0"` fails since the YAML still says `0.2.0` before Step 1's YAML edit is picked up by the loader (Step 1 and this test are done together — after Step 1's YAML edit, the version assertion passes even before Step 4's code change; the `chains`/`segments` assertions fail until Step 4).

- [ ] **Step 4: Modify `synth/config.py`**

Add two new dataclasses (near `CategoryConfig`/`CalibrationConfig`):

```python
@dataclass
class ChainConfig:
    name: str
    price_multiplier: float
    segment_weights: dict[str, float]


@dataclass
class SegmentConfig:
    name: str
    price_multiplier: float
```

Add two fields to `SynthConfig`:

```python
@dataclass
class SynthConfig:
    version: str
    frozen_at: str | None
    categories: list[CategoryConfig]
    calibration: CalibrationConfig
    districts: list[str]
    household_size_weights: dict[int, float]
    reference_date: date
    chains: list[ChainConfig]
    segments: list[SegmentConfig]
    ...  # all_items() unchanged
```

In `load_config`, after the existing parsing and before constructing `SynthConfig`:

```python
    chains = [
        ChainConfig(
            name=c["name"],
            price_multiplier=float(c["price_multiplier"]),
            segment_weights={k: float(v) for k, v in c["segment_weights"].items()},
        )
        for c in raw["chains"]
    ]
    segments = [
        SegmentConfig(name=s["name"], price_multiplier=float(s["price_multiplier"]))
        for s in raw["segments"]
    ]
```

And pass `chains=chains, segments=segments` into the `SynthConfig(...)` constructor call alongside the existing arguments.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/synth/test_config.py -v`
Expected: PASS (3 passed — the 2 pre-existing tests plus the new one)

- [ ] **Step 6: Review changes**

Re-read `config/synth_schema.yaml` and `synth/config.py` to confirm only the intended additions are present. Do not commit — the user commits per project convention.

---

### Task 2: Entities — `assign_chains_and_segments()`

**Files:**
- Modify: `synth/entities.py`
- Modify: `tests/synth/test_entities.py`

**Interfaces:**
- Consumes: `synth.config.ChainConfig` (Task 1).
- Produces: `synth.entities.assign_chains_and_segments(n_users: int, chains: list[ChainConfig], seed: int) -> list[tuple[str, str]]` — one `(chain_name, segment_name)` pair per user index, in order.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/synth/test_entities.py
from synth.config import ChainConfig
from synth.entities import assign_chains_and_segments


def _sample_chains() -> list[ChainConfig]:
    return [
        ChainConfig(
            name="Пятёрочка",
            price_multiplier=1.0,
            segment_weights={"Молодёжь": 0.7, "Старшие": 0.3},
        ),
        ChainConfig(
            name="Чижик",
            price_multiplier=0.75,
            segment_weights={"Молодёжь": 0.2, "Старшие": 0.8},
        ),
    ]


def test_assign_chains_and_segments_covers_all_users():
    result = assign_chains_and_segments(n_users=200, chains=_sample_chains(), seed=1)
    assert len(result) == 200
    chain_names = {"Пятёрочка", "Чижик"}
    segment_names = {"Молодёжь", "Старшие"}
    assert all(chain in chain_names for chain, _ in result)
    assert all(segment in segment_names for _, segment in result)


def test_assign_chains_and_segments_is_deterministic_for_same_seed():
    a = assign_chains_and_segments(100, _sample_chains(), seed=7)
    b = assign_chains_and_segments(100, _sample_chains(), seed=7)
    assert a == b


def test_assign_chains_and_segments_respects_segment_weights_per_chain():
    result = assign_chains_and_segments(n_users=5000, chains=_sample_chains(), seed=42)
    pyaterochka_segments = [seg for chain, seg in result if chain == "Пятёрочка"]
    chizhik_segments = [seg for chain, seg in result if chain == "Чижик"]

    pyaterochka_young_share = pyaterochka_segments.count("Молодёжь") / len(pyaterochka_segments)
    chizhik_young_share = chizhik_segments.count("Молодёжь") / len(chizhik_segments)

    # Пятёрочка's weights give 70% Молодёжь, Чижик's give 20% — should be
    # clearly separated, not just "roughly random"
    assert pyaterochka_young_share > 0.6
    assert chizhik_young_share < 0.3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_entities.py -v`
Expected: FAIL with `ImportError: cannot import name 'assign_chains_and_segments'`

- [ ] **Step 3: Add to `synth/entities.py`**

Add the import `from synth.config import ChainConfig` at the top (alongside any existing imports), then:

```python
def assign_chains_and_segments(
    n_users: int,
    chains: list[ChainConfig],
    seed: int,
) -> list[tuple[str, str]]:
    """For each of n_users, draw a chain uniformly, then a segment weighted
    by that chain's segment_weights. Returns (chain_name, segment_name)
    pairs, one per user index, in order."""
    rng = random.Random(seed)
    chain_names = [c.name for c in chains]
    chains_by_name = {c.name: c for c in chains}

    result: list[tuple[str, str]] = []
    for _ in range(n_users):
        chain_name = rng.choice(chain_names)
        chain = chains_by_name[chain_name]
        segment_names = list(chain.segment_weights.keys())
        weights = list(chain.segment_weights.values())
        segment_name = rng.choices(segment_names, weights=weights, k=1)[0]
        result.append((chain_name, segment_name))

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_entities.py -v`
Expected: PASS (6 passed — the 3 pre-existing tests plus the 3 new ones)

- [ ] **Step 5: Review changes**

Re-read `synth/entities.py`. Do not commit — the user commits per project convention.

---

### Task 3: Receipts — `price_multiplier` parameter

**Files:**
- Modify: `synth/receipts.py`
- Modify: `tests/synth/test_receipts.py`

**Interfaces:**
- Modifies: `synth.receipts.generate_receipts_for_user` gains one new optional parameter: `price_multiplier: float = 1.0`. All existing parameters (`user_id`, `config`, `seed`, `months`, `habitual_categories`, `promo_affinity`, `weekend_bias`) are unchanged — this is purely additive, no existing call site breaks.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/synth/test_receipts.py
def test_price_multiplier_scales_mean_receipt_total():
    config = load_config("config/synth_schema.yaml")

    baseline = generate_receipts_for_user("u_pm_1", config, seed=100, months=3, price_multiplier=1.0)
    scaled = generate_receipts_for_user("u_pm_2", config, seed=100, months=3, price_multiplier=2.0)

    baseline_lines = [line for r in baseline for line in r.lines]
    scaled_lines = [line for r in scaled for line in r.lines]

    baseline_mean_price = sum(l.price_rub for l in baseline_lines) / len(baseline_lines)
    scaled_mean_price = sum(l.price_rub for l in scaled_lines) / len(scaled_lines)

    # same seed, only price_multiplier differs -> scaled prices should be
    # ~2x the baseline (same random draws feed a range that's 2x wider)
    ratio = scaled_mean_price / baseline_mean_price
    assert 1.8 < ratio < 2.2


def test_price_multiplier_defaults_to_one():
    config = load_config("config/synth_schema.yaml")
    explicit = generate_receipts_for_user("u_pm_3", config, seed=50, months=3, price_multiplier=1.0)
    default = generate_receipts_for_user("u_pm_3", config, seed=50, months=3)
    assert [r.total_rub for r in explicit] == [r.total_rub for r in default]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_receipts.py -v`
Expected: FAIL with `TypeError: generate_receipts_for_user() got an unexpected keyword argument 'price_multiplier'`

- [ ] **Step 3: Modify `synth/receipts.py`**

Add `price_multiplier: float = 1.0` to `generate_receipts_for_user`'s parameter list (after `weekend_bias`), and change the line that computes each line's price from:

```python
            price = _price_for_item(rng, cal.avg_receipt_total_rub, on_promo)
```

to:

```python
            price = _price_for_item(rng, cal.avg_receipt_total_rub * price_multiplier, on_promo)
```

No other line in the function changes.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_receipts.py -v`
Expected: PASS (all receipts tests, pre-existing plus the 2 new ones)

- [ ] **Step 5: Review changes**

Re-read `synth/receipts.py`. Do not commit — the user commits per project convention.

---

### Task 4: Population — wire in chains and segments

**Files:**
- Modify: `synth/population.py`
- Modify: `tests/synth/test_population.py`

**Interfaces:**
- Consumes: `synth.entities.assign_chains_and_segments` (Task 2); `generate_receipts_for_user(..., price_multiplier=...)` (Task 3); `config.chains: list[ChainConfig]`, `config.segments: list[SegmentConfig]` (Task 1).
- `population()`'s own signature (`population(n, seed, config) -> list[dict]`) does not change — only the dicts it returns gain two new keys: `"chain"` and `"segment"`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/synth/test_population.py
def test_population_users_have_chain_and_segment():
    config = load_config("config/synth_schema.yaml")
    users = population(n=50, seed=1, config=config)

    chain_names = {c.name for c in config.chains}
    segment_names = {s.name for s in config.segments}

    assert all("chain" in u and "segment" in u for u in users)
    assert all(u["chain"] in chain_names for u in users)
    assert all(u["segment"] in segment_names for u in users)


def test_population_segment_distribution_matches_chain_weights():
    config = load_config("config/synth_schema.yaml")
    users = population(n=3000, seed=2, config=config)

    pyaterochka_users = [u for u in users if u["chain"] == "Пятёрочка"]
    pyaterochka_young_share = (
        sum(1 for u in pyaterochka_users if u["segment"] == "Молодёжь")
        / len(pyaterochka_users)
    )
    # configured weight is 0.37 for Пятёрочка/Молодёжь — allow sampling noise
    assert 0.30 < pyaterochka_young_share < 0.44


def test_population_price_multiplier_affects_receipt_totals():
    config = load_config("config/synth_schema.yaml")
    users = population(n=2000, seed=3, config=config)

    # Зрелые (1.4x) should have a visibly higher mean receipt total than
    # Молодёжь (0.75x), holding chain constant isn't required for this
    # coarse a check — the segment multiplier gap (1.4 vs 0.75, ~1.87x) is
    # large enough to show through chain-multiplier noise (0.75-1.25x)
    def mean_total(segment: str) -> float:
        totals = [
            r["total_rub"]
            for u in users if u["segment"] == segment
            for r in u["receipts"]
        ]
        return sum(totals) / len(totals)

    zrelye_mean = mean_total("Зрелые")
    molodezh_mean = mean_total("Молодёжь")
    assert zrelye_mean > molodezh_mean * 1.3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_population.py -v`
Expected: FAIL — `KeyError: 'chain'` (the field doesn't exist yet)

- [ ] **Step 3: Modify `synth/population.py`**

Add the import `from synth.entities import assign_chains_and_segments` (alongside the existing `synth.entities` import), then in `population()`, after the existing `households_by_id = {...}` line and before the `category_names = [...]` line, add:

```python
    chain_segment_seed = seed + 900_000_001
    chain_segments = assign_chains_and_segments(n, config.chains, chain_segment_seed)
    chains_by_name = {c.name: c for c in config.chains}
    segments_by_name = {s.name: s for s in config.segments}
```

Then inside the per-user loop, after `habit_rng = random.Random(habit_seed)` / before the call to `generate_receipts_for_user`, add:

```python
        chain_name, segment_name = chain_segments[i]
        price_multiplier = (
            chains_by_name[chain_name].price_multiplier
            * segments_by_name[segment_name].price_multiplier
        )
```

Update the `generate_receipts_for_user(...)` call to add `price_multiplier=price_multiplier`.

Update the dict appended to `result` to add `"chain": chain_name, "segment": segment_name,` (alongside the existing `"family_size"` key — same style, plain string values).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_population.py -v`
Expected: PASS

- [ ] **Step 5: Review changes**

Re-read `synth/population.py`. Do not commit — the user commits per project convention.

---

### Task 5: Reference profiles — wire in chains and segments

**Files:**
- Modify: `synth/reference_profiles.py`
- Modify: `tests/synth/test_reference_profiles.py`

**Interfaces:**
- Consumes: same as Task 4, plus the existing `assign_households`/`build_districts` wiring already in this file from the earlier final-fix-wave (Fix 5).
- `reference_profiles()`'s own signature does not change — its returned dicts gain `"chain"` and `"segment"` keys.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/synth/test_reference_profiles.py
def test_reference_profiles_have_chain_and_segment():
    config = load_config("config/synth_schema.yaml")
    profiles = reference_profiles(default_archetype_list(30), seed=1, config=config)

    chain_names = {c.name for c in config.chains}
    segment_names = {s.name for s in config.segments}

    assert all("chain" in p and "segment" in p for p in profiles)
    assert all(p["chain"] in chain_names for p in profiles)
    assert all(p["segment"] in segment_names for p in profiles)


def test_reference_profiles_chain_segment_seed_differs_from_population():
    """The chain/segment assignment must not reproduce population()'s
    sequence when called with the same base seed — different offset
    constants (900_000_001 vs 900_000_002) should give different draws."""
    config = load_config("config/synth_schema.yaml")
    profiles = reference_profiles(default_archetype_list(50), seed=999, config=config)
    from synth.population import population
    users = population(n=50, seed=999, config=config)

    profile_chains = [p["chain"] for p in profiles]
    user_chains = [u["chain"] for u in users]
    # not a strict inequality requirement on every element (some overlap by
    # chance is fine with only 3 chains) — just confirm the two sequences
    # aren't byte-identical, which they would be if the offsets collided
    assert profile_chains != user_chains
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_reference_profiles.py -v`
Expected: FAIL — `KeyError: 'chain'`

- [ ] **Step 3: Modify `synth/reference_profiles.py`**

Add the import `from synth.entities import assign_chains_and_segments` (alongside the existing `build_districts`/`assign_households` import), then in `reference_profiles()`, near the existing `districts = build_districts(...)` / `entity_users, entity_households = assign_households(...)` lines added in the earlier final-fix-wave, add:

```python
    chain_segment_seed = seed + 900_000_002
    chain_segments = assign_chains_and_segments(len(archetypes), config.chains, chain_segment_seed)
    chains_by_name = {c.name: c for c in config.chains}
    segments_by_name = {s.name: s for s in config.segments}
```

Inside the per-profile loop, alongside the existing archetype/household lookups, add:

```python
        chain_name, segment_name = chain_segments[i]
        price_multiplier = (
            chains_by_name[chain_name].price_multiplier
            * segments_by_name[segment_name].price_multiplier
        )
```

Update the `generate_receipts_for_user(...)` call to add `price_multiplier=price_multiplier`.

Update the dict appended to `result` to add `"chain": chain_name, "segment": segment_name,`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_reference_profiles.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/synth -v`
Expected: all tests across this plan's 5 tasks and the base plan's 6 tasks pass together.

- [ ] **Step 6: Review changes**

Re-read `synth/reference_profiles.py`. Do not commit — the user commits per project convention.

---

## After This Plan

- The two existing generated files (`data/population_1k-10k.jsonl`, and any `reference_profiles.json` produced so far) were generated *before* this change and do not have `chain`/`segment` fields — they need regenerating with the same fixed seed once this plan lands, if the chain/segment fields are needed downstream.
- Not covered here: any chain- or segment-specific category preferences (explicitly out of scope per the spec) — if a later need arises for e.g. "Старшие buy more from заморозка," that's a new spec, not a silent addition to this one.
- The pre-existing minor gap where `population()`'s and `reference_profiles()`'s `assign_households` calls both use the raw `seed` directly (so calling both with the same seed correlates their household/district assignments) was noticed while designing this plan's seed-offset scheme, but is out of scope for this task — not introduced or worsened by it, just observed. Worth a future cleanup pass, not a blocker here.
