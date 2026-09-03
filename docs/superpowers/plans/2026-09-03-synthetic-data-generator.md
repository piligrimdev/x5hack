# Synthetic Data Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the synthetic-data generator (schema config + Python generator) that produces the 1–10k user population for the H1/H4 simulation and the 30–50 reference profiles for the H2 hit-rate evaluation, from one shared, frozen schema.

**Architecture:** A YAML config (`config/synth_schema.yaml`) defines categories, a small item vocabulary per category, calibration constants, districts, and household-size weights. A small Python package (`synth/`) builds users/households/districts, generates deterministic (seeded) receipt histories per user — either from a random habitual-category set (population) or from an explicit `persona_archetype` rule (reference profiles) — and writes the results as JSONL/JSON. A CLI ties the two generation modes together.

**Tech Stack:** Python 3.11+, PyYAML for config parsing, pytest for tests, stdlib only otherwise (`dataclasses`, `random`, `json`, `datetime`, `argparse`).

**Spec:** `docs/superpowers/specs/2026-09-03-synthetic-data-schema-design.md`

## Global Constraints

- No PII anywhere: only synthetic IDs, no real names or addresses (spec §Format and freeze mechanism; CONTEXT_PACK §3 fail-condition).
- 3 months of purchase history generated per user (spec §Generation).
- Small per-category item vocabulary (5–10 concrete items per category), not a full SKU catalog (spec §Entities — Item).
- Purchase channel is skewed offline (spec §Calibration; CONTEXT_PACK §7 answer 6).
- Calibration constants come from reasonable assumptions plus public retail data, never real X5 data, and each constant's source is recorded inline in the config (spec §Calibration).
- `config/synth_schema.yaml` carries a `version` field and is the single frozen source of categories/items/calibration; once H2/H3 prompt or logic tuning starts, it is not edited silently (spec §Format and freeze mechanism).
- Datasets are written as `data/population_1k-10k.jsonl` (JSONL, one user object per line) and `data/reference_profiles.json` (JSON array) (spec §Format and freeze mechanism).
- All random generation is seeded and deterministic — the same `(seed, config)` must reproduce byte-identical output, since "frozen" data has to be regenerable.
- Do not run `git init`, `git add`, `git commit`, or `git push` at any point in this plan — per this project's CLAUDE.md, the user handles all git operations directly. Each task ends with a review step instead of a commit step.

---

## File Structure

```
requirements.txt                          # pyyaml, pytest
config/
  synth_schema.yaml                        # frozen schema: categories, items, calibration, districts
synth/
  __init__.py
  config.py                                # SynthConfig dataclasses + load_config()
  entities.py                              # User/Household/District + assign_households()
  receipts.py                              # Receipt/ReceiptLine + generate_receipts_for_user()
  population.py                            # population() + write_population_jsonl()
  reference_profiles.py                    # archetypes + reference_profiles() + write_reference_profiles_json()
  cli.py                                   # argparse entrypoint: `python -m synth.cli population|reference`
tests/
  synth/
    test_config.py
    test_entities.py
    test_receipts.py
    test_population.py
    test_reference_profiles.py
    test_cli.py
data/                                       # generator output, created at runtime — not committed
```

Each file has one responsibility: `config.py` only parses/validates the frozen schema, `entities.py` only builds the user/household/district graph, `receipts.py` only turns a user + config into receipt history, `population.py`/`reference_profiles.py` only wire entities+receipts into the two output shapes, `cli.py` only exposes them as commands.

---

### Task 1: Project scaffolding + schema config + loader

**Files:**
- Create: `requirements.txt`
- Create: `config/synth_schema.yaml`
- Create: `synth/__init__.py`
- Create: `synth/config.py`
- Test: `tests/synth/test_config.py`

**Interfaces:**
- Produces: `synth.config.CategoryConfig(name: str, items: list[str])`, `synth.config.CalibrationConfig(avg_receipt_total_rub: float, purchases_per_month_mean: float, purchases_per_month_stddev: float, offline_share: float, source: str)`, `synth.config.SynthConfig(version: str, frozen_at: str | None, categories: list[CategoryConfig], calibration: CalibrationConfig, districts: list[str], household_size_weights: dict[int, float])` with method `SynthConfig.all_items() -> list[tuple[str, str]]`, and `synth.config.load_config(path: str | Path) -> SynthConfig`.

- [ ] **Step 1: Create `requirements.txt`**

```
pyyaml>=6.0
pytest>=7.0
```

- [ ] **Step 2: Create `config/synth_schema.yaml`**

```yaml
version: "0.1.0"
frozen_at: null

calibration:
  avg_receipt_total_rub: 850.0
  purchases_per_month_mean: 10.0
  purchases_per_month_stddev: 3.0
  offline_share: 0.8
  source: >
    Reasonable assumptions calibrated against public Russian grocery-retail
    aggregates (no real X5 data available per CONTEXT_PACK.md §3/§4).
    Revisit if the case owner provides real numbers (CONTEXT_PACK.md §7).

districts:
  - "Район-01"
  - "Район-02"
  - "Район-03"
  - "Район-04"
  - "Район-05"
  - "Район-06"
  - "Район-07"
  - "Район-08"
  - "Район-09"
  - "Район-10"
  - "Район-11"
  - "Район-12"
  - "Район-13"
  - "Район-14"
  - "Район-15"
  - "Район-16"
  - "Район-17"
  - "Район-18"
  - "Район-19"
  - "Район-20"

household_size_weights:
  1: 0.30
  2: 0.30
  3: 0.25
  4: 0.15

categories:
  - name: "молочные продукты и яйца"
    items: ["молоко", "сметана", "творог", "кефир", "сыр", "яйца"]
  - name: "овощи"
    items: ["картофель", "морковь", "лук", "свёкла", "капуста", "огурцы"]
  - name: "фрукты"
    items: ["яблоки", "бананы", "апельсины", "груши", "виноград", "лимоны"]
  - name: "мясо и птица"
    items: ["курица", "говядина", "свинина", "фарш", "сосиски", "колбаса"]
  - name: "рыба и морепродукты"
    items: ["сельдь", "форель", "рыбные консервы", "креветки", "кальмары", "минтай"]
  - name: "бакалея"
    items: ["мука", "сахар", "соль", "гречка", "рис", "макароны"]
  - name: "хлеб и выпечка"
    items: ["хлеб белый", "хлеб чёрный", "батон", "лаваш", "булочки", "сухари"]
  - name: "напитки"
    items: ["вода", "сок", "газировка", "чай", "кофе", "компот"]
  - name: "заморозка"
    items: ["пельмени", "овощная смесь", "мороженое", "замороженные ягоды", "наггетсы", "блины"]
  - name: "сладости и снеки"
    items: ["шоколад", "печенье", "чипсы", "орехи солёные", "зефир", "вафли"]
  - name: "консервация"
    items: ["тушёнка", "кукуруза консервированная", "горошек консервированный", "оливки", "огурцы маринованные", "томатная паста"]
  - name: "соусы и приправы"
    items: ["майонез", "кетчуп", "соевый соус", "специи", "горчица", "уксус"]
  - name: "масла и жиры"
    items: ["подсолнечное масло", "оливковое масло", "сливочное масло", "маргарин", "кокосовое масло", "кулинарный жир"]
  - name: "бытовая химия"
    items: ["стиральный порошок", "средство для мытья посуды", "чистящее средство", "мешки для мусора", "губки", "отбеливатель"]
  - name: "личная гигиена"
    items: ["зубная паста", "шампунь", "мыло", "гель для душа", "дезодорант", "туалетная бумага"]
  - name: "детское питание"
    items: ["пюре детское", "каша детская", "молочная смесь", "печенье детское", "сок детский", "вода детская"]
  - name: "алкоголь"
    items: ["пиво", "вино", "водка", "сидр", "шампанское", "коньяк"]
  - name: "кондитерка"
    items: ["торт", "пирожное", "конфеты", "мармелад", "пастила", "круассан"]
  - name: "готовая еда"
    items: ["салат готовый", "суп готовый", "пицца готовая", "роллы", "сэндвич", "каша быстрого приготовления"]
  - name: "орехи и сухофрукты"
    items: ["изюм", "курага", "чернослив", "миндаль", "фундук", "кешью"]
  - name: "товары для дома"
    items: ["свечи", "батарейки", "фольга", "плёнка пищевая", "спички", "скотч"]
  - name: "товары для животных"
    items: ["корм для кошек", "корм для собак", "наполнитель для туалета", "лакомства", "миски", "игрушки для животных"]
```

- [ ] **Step 3: Create `synth/__init__.py`** (empty file, makes `synth` a package)

- [ ] **Step 4: Write the failing test**

```python
# tests/synth/test_config.py
from synth.config import load_config


def test_load_config_returns_expected_structure():
    config = load_config("config/synth_schema.yaml")
    assert config.version == "0.1.0"
    assert len(config.categories) == 22
    assert all(5 <= len(c.items) <= 10 for c in config.categories)
    assert 0.0 < config.calibration.offline_share <= 1.0
    assert config.calibration.avg_receipt_total_rub > 0
    assert len(config.districts) == 20
    assert abs(sum(config.household_size_weights.values()) - 1.0) < 1e-6


def test_all_items_returns_category_item_pairs():
    config = load_config("config/synth_schema.yaml")
    pairs = config.all_items()
    assert len(pairs) == sum(len(c.items) for c in config.categories)
    assert all(isinstance(p, tuple) and len(p) == 2 for p in pairs)
    assert ("овощи", "картофель") in pairs
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest tests/synth/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'synth.config'` (or `synth`)

- [ ] **Step 6: Write `synth/config.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class CategoryConfig:
    name: str
    items: list[str]


@dataclass
class CalibrationConfig:
    avg_receipt_total_rub: float
    purchases_per_month_mean: float
    purchases_per_month_stddev: float
    offline_share: float
    source: str


@dataclass
class SynthConfig:
    version: str
    frozen_at: str | None
    categories: list[CategoryConfig]
    calibration: CalibrationConfig
    districts: list[str]
    household_size_weights: dict[int, float]

    def all_items(self) -> list[tuple[str, str]]:
        """Return (category_name, item_name) pairs for every item in the schema."""
        return [(c.name, item) for c in self.categories for item in c.items]


def load_config(path: str | Path) -> SynthConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    categories = [
        CategoryConfig(name=c["name"], items=list(c["items"]))
        for c in raw["categories"]
    ]
    calibration = CalibrationConfig(**raw["calibration"])
    household_size_weights = {
        int(k): float(v) for k, v in raw["household_size_weights"].items()
    }

    return SynthConfig(
        version=raw["version"],
        frozen_at=raw.get("frozen_at"),
        categories=categories,
        calibration=calibration,
        districts=list(raw["districts"]),
        household_size_weights=household_size_weights,
    )
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/synth/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Review changes**

Run: `git status` and `git diff` to confirm only the intended files changed. Do not commit — the user commits per project convention.

---

### Task 2: Entities — User, Household, District

**Files:**
- Create: `synth/entities.py`
- Test: `tests/synth/test_entities.py`

**Interfaces:**
- Consumes: `synth.config.SynthConfig` (Task 1) — specifically `config.districts: list[str]` and `config.household_size_weights: dict[int, float]`.
- Produces: `synth.entities.District(district_id: str, name: str)`, `synth.entities.Household(household_id: str, district_id: str, family_size: int)`, `synth.entities.User(user_id: str, household_id: str, district_id: str)`, `synth.entities.build_districts(names: list[str]) -> list[District]`, `synth.entities.assign_households(n_users: int, districts: list[District], household_size_weights: dict[int, float], seed: int) -> tuple[list[User], list[Household]]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/synth/test_entities.py
from synth.entities import build_districts, assign_households


def test_build_districts_creates_one_per_name():
    districts = build_districts(["Район-01", "Район-02"])
    assert [d.district_id for d in districts] == ["d_01", "d_02"]
    assert districts[0].name == "Район-01"


def test_assign_households_covers_all_users_exactly_once():
    districts = build_districts(["Район-01", "Район-02", "Район-03"])
    users, households = assign_households(
        n_users=50,
        districts=districts,
        household_size_weights={1: 0.5, 2: 0.5},
        seed=42,
    )
    assert len(users) == 50
    assert len({u.user_id for u in users}) == 50
    household_ids = {h.household_id for h in households}
    district_ids = {d.district_id for d in districts}
    assert all(u.household_id in household_ids for u in users)
    assert all(u.district_id in district_ids for u in users)


def test_assign_households_is_deterministic_for_same_seed():
    districts = build_districts(["Район-01", "Район-02"])
    users_a, _ = assign_households(30, districts, {1: 1.0}, seed=7)
    users_b, _ = assign_households(30, districts, {1: 1.0}, seed=7)
    assert [u.user_id for u in users_a] == [u.user_id for u in users_b]
    assert [u.household_id for u in users_a] == [u.household_id for u in users_b]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_entities.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'synth.entities'`

- [ ] **Step 3: Write `synth/entities.py`**

```python
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class District:
    district_id: str
    name: str


@dataclass
class Household:
    household_id: str
    district_id: str
    family_size: int


@dataclass
class User:
    user_id: str
    household_id: str
    district_id: str


def build_districts(names: list[str]) -> list[District]:
    return [
        District(district_id=f"d_{i:02d}", name=name)
        for i, name in enumerate(names, start=1)
    ]


def assign_households(
    n_users: int,
    districts: list[District],
    household_size_weights: dict[int, float],
    seed: int,
) -> tuple[list[User], list[Household]]:
    """Group n_users into households of weighted-random size, each in a random district."""
    rng = random.Random(seed)
    sizes = list(household_size_weights.keys())
    weights = list(household_size_weights.values())

    users: list[User] = []
    households: list[Household] = []
    household_index = 0
    user_index = 0

    while user_index < n_users:
        household_index += 1
        size = min(rng.choices(sizes, weights=weights, k=1)[0], n_users - user_index)
        district = rng.choice(districts)
        household_id = f"h_{household_index:06d}"
        households.append(
            Household(household_id=household_id, district_id=district.district_id, family_size=size)
        )

        for _ in range(size):
            user_index += 1
            users.append(
                User(
                    user_id=f"u_{user_index:06d}",
                    household_id=household_id,
                    district_id=district.district_id,
                )
            )

    return users, households
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_entities.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Review changes**

Run: `git status` and `git diff`. Do not commit — the user commits per project convention.

---

### Task 3: Receipt generation core

**Files:**
- Create: `synth/receipts.py`
- Test: `tests/synth/test_receipts.py`

**Interfaces:**
- Consumes: `synth.config.SynthConfig` (Task 1) — `config.categories`, `config.calibration`.
- Produces: `synth.receipts.ReceiptLine(category: str, item: str, price_rub: float, qty: int, on_promo: bool)`, `synth.receipts.Receipt(receipt_id: str, user_id: str, purchase_date: str, channel: str, lines: list[ReceiptLine], total_rub: float)`, `synth.receipts.generate_receipts_for_user(user_id: str, config: SynthConfig, seed: int, months: int = 3, habitual_categories: list[str] | None = None, promo_affinity: float = 0.15) -> list[Receipt]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/synth/test_receipts.py
from synth.config import load_config
from synth.receipts import generate_receipts_for_user


def test_generate_receipts_produces_nonempty_history():
    config = load_config("config/synth_schema.yaml")
    receipts = generate_receipts_for_user("u_000001", config, seed=1, months=3)
    assert len(receipts) > 0
    assert all(r.lines for r in receipts)
    assert all(r.total_rub > 0 for r in receipts)
    assert all(r.channel in ("offline", "online") for r in receipts)


def test_generate_receipts_is_deterministic_for_same_seed():
    config = load_config("config/synth_schema.yaml")
    a = generate_receipts_for_user("u_000001", config, seed=5, months=3)
    b = generate_receipts_for_user("u_000001", config, seed=5, months=3)
    assert [r.receipt_id for r in a] == [r.receipt_id for r in b]
    assert [r.total_rub for r in a] == [r.total_rub for r in b]


def test_habitual_categories_dominate_when_given():
    config = load_config("config/synth_schema.yaml")
    habitual = ["молочные продукты и яйца", "овощи"]
    receipts = generate_receipts_for_user(
        "u_000002", config, seed=9, months=3, habitual_categories=habitual
    )
    all_lines = [line for r in receipts for line in r.lines]
    habitual_count = sum(1 for l in all_lines if l.category in habitual)
    assert habitual_count / len(all_lines) > 0.5


def test_no_habitual_categories_means_full_spread():
    config = load_config("config/synth_schema.yaml")
    receipts = generate_receipts_for_user("u_000003", config, seed=11, months=3)
    categories_seen = {line.category for r in receipts for line in r.lines}
    assert len(categories_seen) > 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_receipts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'synth.receipts'`

- [ ] **Step 3: Write `synth/receipts.py`**

```python
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from synth.config import SynthConfig


@dataclass
class ReceiptLine:
    category: str
    item: str
    price_rub: float
    qty: int
    on_promo: bool


@dataclass
class Receipt:
    receipt_id: str
    user_id: str
    purchase_date: str  # ISO date
    channel: str  # "offline" or "online"
    lines: list[ReceiptLine]
    total_rub: float


def _price_for_item(rng: random.Random, avg_receipt_total: float, on_promo: bool) -> float:
    base = rng.uniform(avg_receipt_total * 0.03, avg_receipt_total * 0.15)
    if on_promo:
        base *= rng.uniform(0.6, 0.85)
    return round(base, 2)


def generate_receipts_for_user(
    user_id: str,
    config: SynthConfig,
    seed: int,
    months: int = 3,
    habitual_categories: list[str] | None = None,
    promo_affinity: float = 0.15,
) -> list[Receipt]:
    """Generate `months` worth of receipts for one user.

    If `habitual_categories` is given, ~80% of receipt lines are drawn from
    those categories (repeat pattern); the rest are drawn from any category
    (exploration noise). If not given, every line is drawn from any category
    (no exploitable pattern — used for the "one_off_no_pattern" archetype).
    """
    rng = random.Random(seed)
    cal = config.calibration
    items_by_category: dict[str, list[str]] = {c.name: c.items for c in config.categories}
    all_categories = list(items_by_category.keys())

    n_receipts = max(
        1, round(rng.gauss(cal.purchases_per_month_mean, cal.purchases_per_month_stddev) * months)
    )
    start = date.today() - timedelta(days=30 * months)

    receipts: list[Receipt] = []
    for i in range(n_receipts):
        purchase_date = start + timedelta(days=rng.randint(0, 30 * months - 1))
        channel = "offline" if rng.random() < cal.offline_share else "online"
        n_lines = rng.randint(1, 5)

        lines: list[ReceiptLine] = []
        for _ in range(n_lines):
            if habitual_categories and rng.random() < 0.8:
                category = rng.choice(habitual_categories)
            else:
                category = rng.choice(all_categories)
            item = rng.choice(items_by_category[category])
            on_promo = rng.random() < promo_affinity
            price = _price_for_item(rng, cal.avg_receipt_total_rub, on_promo)
            qty = rng.randint(1, 3)
            lines.append(
                ReceiptLine(category=category, item=item, price_rub=price, qty=qty, on_promo=on_promo)
            )

        total = round(sum(l.price_rub * l.qty for l in lines), 2)
        receipts.append(
            Receipt(
                receipt_id=f"r_{user_id}_{i:04d}",
                user_id=user_id,
                purchase_date=purchase_date.isoformat(),
                channel=channel,
                lines=lines,
                total_rub=total,
            )
        )

    receipts.sort(key=lambda r: r.purchase_date)
    return receipts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_receipts.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Review changes**

Run: `git status` and `git diff`. Do not commit — the user commits per project convention.

---

### Task 4: Population generator + JSONL writer

**Files:**
- Create: `synth/population.py`
- Test: `tests/synth/test_population.py`

**Interfaces:**
- Consumes: `synth.config.SynthConfig`, `synth.config.load_config` (Task 1); `synth.entities.build_districts`, `synth.entities.assign_households` (Task 2); `synth.receipts.generate_receipts_for_user` (Task 3).
- Produces: `synth.population.population(n: int, seed: int, config: SynthConfig) -> list[dict]`, `synth.population.write_population_jsonl(path: str | Path, users: list[dict]) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/synth/test_population.py
import json

from synth.config import load_config
from synth.population import population, write_population_jsonl


def test_population_generates_n_users_with_receipts():
    config = load_config("config/synth_schema.yaml")
    users = population(n=25, seed=100, config=config)
    assert len(users) == 25
    assert len({u["user_id"] for u in users}) == 25
    assert all(u["receipts"] for u in users)
    assert all("habitual_categories" in u for u in users)


def test_population_is_deterministic_for_same_seed():
    config = load_config("config/synth_schema.yaml")
    a = population(n=10, seed=3, config=config)
    b = population(n=10, seed=3, config=config)
    assert a == b


def test_write_population_jsonl_writes_one_json_object_per_line(tmp_path):
    config = load_config("config/synth_schema.yaml")
    users = population(n=5, seed=1, config=config)
    out_path = tmp_path / "population.jsonl"
    write_population_jsonl(out_path, users)

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5
    parsed = [json.loads(l) for l in lines]
    assert {p["user_id"] for p in parsed} == {u["user_id"] for u in users}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_population.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'synth.population'`

- [ ] **Step 3: Write `synth/population.py`**

```python
from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path

from synth.config import SynthConfig
from synth.entities import assign_households, build_districts
from synth.receipts import generate_receipts_for_user


def population(n: int, seed: int, config: SynthConfig) -> list[dict]:
    """Generate a population of `n` synthetic users with 3 months of receipt history.

    Returns a list of dicts, one per user, ready to serialize as JSONL.
    """
    districts = build_districts(config.districts)
    users, households = assign_households(n, districts, config.household_size_weights, seed)
    households_by_id = {h.household_id: h for h in households}

    category_names = [c.name for c in config.categories]
    result: list[dict] = []
    for i, user in enumerate(users):
        user_seed = seed + i + 1
        habit_rng = random.Random(user_seed)
        habitual = habit_rng.sample(category_names, k=habit_rng.randint(3, 6))

        receipts = generate_receipts_for_user(
            user.user_id, config, seed=user_seed, months=3, habitual_categories=habitual
        )

        result.append(
            {
                "user_id": user.user_id,
                "household_id": user.household_id,
                "district_id": user.district_id,
                "family_size": households_by_id[user.household_id].family_size,
                "habitual_categories": habitual,
                "receipts": [
                    {**asdict(r), "lines": [asdict(l) for l in r.lines]} for r in receipts
                ],
            }
        )

    return result


def write_population_jsonl(path: str | Path, users: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for user in users:
            f.write(json.dumps(user, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_population.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Review changes**

Run: `git status` and `git diff`. Do not commit — the user commits per project convention.

---

### Task 5: Reference-profile archetypes + generator + JSON writer

**Files:**
- Create: `synth/reference_profiles.py`
- Test: `tests/synth/test_reference_profiles.py`

**Interfaces:**
- Consumes: `synth.config.SynthConfig`, `synth.config.load_config` (Task 1); `synth.receipts.generate_receipts_for_user` (Task 3).
- Produces: `synth.reference_profiles.ARCHETYPES: tuple[str, ...]`, `synth.reference_profiles.default_archetype_list(count: int) -> list[str]`, `synth.reference_profiles.reference_profiles(archetypes: list[str], seed: int, config: SynthConfig) -> list[dict]`, `synth.reference_profiles.write_reference_profiles_json(path: str | Path, profiles: list[dict]) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/synth/test_reference_profiles.py
import json

from synth.config import load_config
from synth.reference_profiles import (
    ARCHETYPES,
    default_archetype_list,
    reference_profiles,
    write_reference_profiles_json,
)


def test_default_archetype_list_round_robins_all_archetypes():
    archetypes = default_archetype_list(9)
    assert len(archetypes) == 9
    assert set(archetypes) == set(ARCHETYPES)
    assert archetypes[:3] == list(ARCHETYPES)


def test_reference_profiles_generates_one_per_archetype_entry():
    config = load_config("config/synth_schema.yaml")
    archetypes = default_archetype_list(6)
    profiles = reference_profiles(archetypes, seed=42, config=config)
    assert len(profiles) == 6
    assert [p["persona_archetype"] for p in profiles] == archetypes
    assert all(p["receipts"] for p in profiles)


def test_bakes_on_weekends_receipts_are_dominated_by_baking_categories():
    config = load_config("config/synth_schema.yaml")
    profiles = reference_profiles(["bakes_on_weekends"], seed=1, config=config)
    lines = [l for r in profiles[0]["receipts"] for l in r["lines"]]
    baking_categories = {"бакалея", "хлеб и выпечка", "молочные продукты и яйца"}
    baking_count = sum(1 for l in lines if l["category"] in baking_categories)
    assert baking_count / len(lines) > 0.5


def test_one_off_no_pattern_has_no_fixed_habitual_categories():
    config = load_config("config/synth_schema.yaml")
    profiles = reference_profiles(["one_off_no_pattern"], seed=1, config=config)
    assert profiles[0]["habitual_categories"] is None


def test_write_reference_profiles_json_round_trips(tmp_path):
    config = load_config("config/synth_schema.yaml")
    profiles = reference_profiles(default_archetype_list(3), seed=1, config=config)
    out_path = tmp_path / "reference_profiles.json"
    write_reference_profiles_json(out_path, profiles)

    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert [p["user_id"] for p in loaded] == [p["user_id"] for p in profiles]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_reference_profiles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'synth.reference_profiles'`

- [ ] **Step 3: Write `synth/reference_profiles.py`**

```python
from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path

from synth.config import SynthConfig
from synth.receipts import generate_receipts_for_user

ARCHETYPES: tuple[str, ...] = ("bakes_on_weekends", "promo_hunter", "one_off_no_pattern")


def _archetype_params(
    archetype: str, config: SynthConfig, rng: random.Random
) -> tuple[list[str] | None, float]:
    """Return (habitual_categories, promo_affinity) for the given archetype."""
    category_names = [c.name for c in config.categories]

    if archetype == "bakes_on_weekends":
        baking = [
            c for c in category_names
            if c in ("бакалея", "хлеб и выпечка", "молочные продукты и яйца")
        ]
        extra = rng.sample([c for c in category_names if c not in baking], k=1)
        return baking + extra, 0.15

    if archetype == "promo_hunter":
        habitual = rng.sample(category_names, k=rng.randint(4, 6))
        return habitual, 0.6

    if archetype == "one_off_no_pattern":
        return None, 0.15

    raise ValueError(f"unknown archetype: {archetype}")


def default_archetype_list(count: int) -> list[str]:
    """Round-robin `count` archetype assignments across the defined archetypes."""
    return [ARCHETYPES[i % len(ARCHETYPES)] for i in range(count)]


def reference_profiles(archetypes: list[str], seed: int, config: SynthConfig) -> list[dict]:
    """Generate one reference profile per entry in `archetypes`.

    Each profile's receipts deterministically follow the named archetype's
    pattern rules, so a human labeler has a concrete expected pattern to
    check the model's output against.
    """
    result: list[dict] = []
    for i, archetype in enumerate(archetypes):
        profile_seed = seed + i + 1
        rng = random.Random(profile_seed)
        user_id = f"ref_{i:03d}_{archetype}"

        habitual, promo_affinity = _archetype_params(archetype, config, rng)
        receipts = generate_receipts_for_user(
            user_id,
            config,
            seed=profile_seed,
            months=3,
            habitual_categories=habitual,
            promo_affinity=promo_affinity,
        )

        result.append(
            {
                "user_id": user_id,
                "persona_archetype": archetype,
                "habitual_categories": habitual,
                "receipts": [
                    {**asdict(r), "lines": [asdict(l) for l in r.lines]} for r in receipts
                ],
            }
        )

    return result


def write_reference_profiles_json(path: str | Path, profiles: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_reference_profiles.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Review changes**

Run: `git status` and `git diff`. Do not commit — the user commits per project convention.

---

### Task 6: CLI entrypoint

**Files:**
- Create: `synth/cli.py`
- Test: `tests/synth/test_cli.py`

**Interfaces:**
- Consumes: `synth.config.load_config` (Task 1); `synth.population.population`, `synth.population.write_population_jsonl` (Task 4); `synth.reference_profiles.default_archetype_list`, `synth.reference_profiles.reference_profiles`, `synth.reference_profiles.write_reference_profiles_json` (Task 5).
- Produces: `synth.cli.build_parser() -> argparse.ArgumentParser`, `synth.cli.main(argv: list[str] | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/synth/test_cli.py
import json

from synth.cli import main


def test_cli_population_writes_expected_file(tmp_path):
    out_path = tmp_path / "population.jsonl"
    main(["population", "--n", "5", "--seed", "1", "--out", str(out_path)])

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5
    assert all(json.loads(l)["user_id"] for l in lines)


def test_cli_reference_writes_expected_file(tmp_path):
    out_path = tmp_path / "reference_profiles.json"
    main(["reference", "--count", "6", "--seed", "1", "--out", str(out_path)])

    profiles = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(profiles) == 6
    assert all("persona_archetype" in p for p in profiles)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synth/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'synth.cli'`

- [ ] **Step 3: Write `synth/cli.py`**

```python
from __future__ import annotations

import argparse

from synth.config import load_config
from synth.population import population, write_population_jsonl
from synth.reference_profiles import (
    default_archetype_list,
    reference_profiles,
    write_reference_profiles_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synth", description="Generate synthetic loyalty-program data.")
    parser.add_argument(
        "--config", default="config/synth_schema.yaml", help="Path to the frozen schema config."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pop_parser = subparsers.add_parser("population", help="Generate the 1-10k user population for simulation.")
    pop_parser.add_argument("--n", type=int, required=True, help="Number of users to generate.")
    pop_parser.add_argument("--seed", type=int, required=True)
    pop_parser.add_argument("--out", default="data/population_1k-10k.jsonl")

    ref_parser = subparsers.add_parser("reference", help="Generate the 30-50 reference profiles for hit-rate eval.")
    ref_parser.add_argument("--count", type=int, default=40, help="Number of reference profiles to generate.")
    ref_parser.add_argument("--seed", type=int, required=True)
    ref_parser.add_argument("--out", default="data/reference_profiles.json")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)

    if args.command == "population":
        users = population(n=args.n, seed=args.seed, config=config)
        write_population_jsonl(args.out, users)
        print(f"Wrote {len(users)} users to {args.out}")
    elif args.command == "reference":
        archetypes = default_archetype_list(args.count)
        profiles = reference_profiles(archetypes, seed=args.seed, config=config)
        write_reference_profiles_json(args.out, profiles)
        print(f"Wrote {len(profiles)} reference profiles to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synth/test_cli.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/synth -v`
Expected: All tests across Tasks 1–6 pass (19 passed).

- [ ] **Step 6: Review changes**

Run: `git status` and `git diff`. Do not commit — the user commits per project convention.

---

## After This Plan

Not covered here (tracked separately in the Miro/Продукт-канбан):
- Actually running `python -m synth.cli reference --count 40 --seed <fixed>` and handing `data/reference_profiles.json` to Паша/Влад for blind labeling.
- Running `python -m synth.cli population --n <1000-10000> --seed <fixed>` for the H1/H4 simulation, and the simulation logic itself.
- The LLM module (H2/H3) that consumes this data — must not start tuning until `config/synth_schema.yaml`'s `frozen_at` is set.
