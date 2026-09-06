from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests

from synth.catalog import SKU, build_catalog, skus_by_category
from synth.config import SynthConfig
from synth.survival import SurvivalCurve

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Default target_quantity for paths that only name a category, not a
# specific item (generic pool + personal/LLM) — the LLM prompt doesn't ask
# for a unit count, and the generic pool's mechanics are worded as
# spend-threshold/percentage offers rather than "buy N", so this is a
# deliberate simplification to fit the single sku_id+quantity progress
# model, not a value derived from the offer's own text. Used by the
# `generic` slot/pool; the four LLM-personal slots use `SLOT_TARGET_QUANTITY`
# below instead, so each reads as a genuinely different kind of ask rather
# than four copies of the same "buy N times" mechanic.
PERSONAL_TARGET_QUANTITY = 2

# Per-slot target_quantity for the LLM-personal slots — without this they
# all shared PERSONAL_TARGET_QUANTITY (always "buy it 2 times"), so despite
# different wording/category every card read as the same mechanic. Product
# decision: a flat single "try/repeat once" ask for every LLM-personal slot
# (`llm_basket` isn't here — it's a deterministic mechanic with its own
# hardcoded quantity, see `build_basket_spend_challenge`).
SLOT_TARGET_QUANTITY: dict[str, int] = {
    "llm_discovery": 1,
    "llm_habit": 1,
    "vibe": 1,
}

# Reward text is phrased in loyalty points, not raw rubles (product
# decision — cashback/points language throughout, never "N ₽"). Synth has
# no DB access to the actual configurable `points_settings.rate_points_per_rub`
# (default 10), so this mirrors the SAME hardcoded rate the mobile app's
# own reward-chip display already uses (`x5mobile/.../savings-view.tsx`
# `TaskCard`'s `rewardPoints = Math.round(reward_rub) * 10`) — keep both in
# sync manually if that rate ever changes.
_POINTS_PER_RUB = 10

# Fixed pool of non-personalized "partner brand" offers. Drawn for EVERY
# user unconditionally via the `generic` slot (not just as a fallback for a
# weak/undetected purchase pattern — see `CHALLENGE_SLOTS`). None of these
# target a forbidden_categories entry. Picked deterministically per user
# (hash of user_id), not randomly — same user always gets the same generic
# offer for a given catalog version, and nothing here needs an LLM call.
GENERIC_CHALLENGES: list[dict] = [
    {
        "challenge_title": "Скидка партнёра на молочную продукцию",
        "description": "5% кэшбэк баллами на молочные продукты и яйца от партнёра программы лояльности.",
        "target_categories": ["молочные продукты и яйца"],
        "mechanic": "партнёрский кэшбэк",
        "reward_rub": 50.0,
        "target_quantity": PERSONAL_TARGET_QUANTITY,
    },
    {
        "challenge_title": "Бонус за покупку свежих овощей и фруктов",
        "description": "Начислим бонусные баллы за покупку овощей или фруктов на сумму от 300 рублей.",
        "target_categories": ["овощи", "фрукты"],
        "mechanic": "бонусные баллы",
        "reward_rub": 40.0,
        "target_quantity": PERSONAL_TARGET_QUANTITY,
    },
    {
        "challenge_title": "Скидка на хозтовары от партнёра",
        "description": "10% скидка на бытовую химию и товары для дома у партнёра сети.",
        "target_categories": ["бытовая химия", "товары для дома"],
        "mechanic": "партнёрская скидка",
        "reward_rub": 60.0,
        "target_quantity": PERSONAL_TARGET_QUANTITY,
    },
    {
        "challenge_title": "Кэшбэк за готовую еду",
        "description": "Верните часть стоимости готовых блюд — бонус за покупку в категории готовой еды.",
        "target_categories": ["готовая еда"],
        "mechanic": "кэшбэк",
        "reward_rub": 55.0,
        "target_quantity": PERSONAL_TARGET_QUANTITY,
    },
    {
        "challenge_title": "Бонус за покупку рыбы и морепродуктов",
        "description": "Дополнительные баллы за покупку в категории рыбы и морепродуктов на этой неделе.",
        "target_categories": ["рыба и морепродукты"],
        "mechanic": "бонусные баллы",
        "reward_rub": 70.0,
        "target_quantity": PERSONAL_TARGET_QUANTITY,
    },
    {
        "challenge_title": "Скидка на личную гигиену от партнёра",
        "description": "Партнёрская скидка 15% на товары личной гигиены.",
        "target_categories": ["личная гигиена"],
        "mechanic": "партнёрская скидка",
        "reward_rub": 45.0,
        "target_quantity": PERSONAL_TARGET_QUANTITY,
    },
    {
        "challenge_title": "Бонус за сладости и снеки",
        "description": "Начислим баллы за покупку сладостей или снеков на сумму от 250 рублей.",
        "target_categories": ["сладости и снеки"],
        "mechanic": "бонусные баллы",
        "reward_rub": 35.0,
        "target_quantity": PERSONAL_TARGET_QUANTITY,
    },
    {
        "challenge_title": "Кэшбэк за товары для животных",
        "description": "Верните часть стоимости при покупке корма или аксессуаров для питомцев.",
        "target_categories": ["товары для животных"],
        "mechanic": "кэшбэк",
        "reward_rub": 50.0,
        "target_quantity": PERSONAL_TARGET_QUANTITY,
    },
]

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

_REQUIRED_FIELDS = ("challenge_title", "description", "target_categories", "mechanic", "reward_rub")


def load_profiles(path: str | Path) -> list[dict]:
    """Load profiles from either a JSON array (reference_profiles*.json) or
    a JSONL / gzipped-JSONL population file — detected by extension."""
    path = Path(path)
    if path.suffix == ".json":
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    opener = gzip.open if path.suffix == ".gz" else open
    profiles: list[dict] = []
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                profiles.append(json.loads(line))
    return profiles


def compute_receptiveness(
    profile: dict,
    config: SynthConfig,
    min_receipts: int = 15,
    min_concentration: float = 0.42,
    top_n: int = 3,
) -> tuple[bool, dict]:
    """Decide personal-vs-generic path from OBSERVABLE data ONLY — the
    user's own train-period receipts. Deliberately does NOT read
    `simulation_truth`'s `challenge_sensitivity`: a real production
    recommender has no such oracle field, so scoring receptiveness from it
    here would inflate the eventual hit-rate in a way that couldn't be
    reproduced outside this synthetic dataset.

    Concentration is computed as the share of train-period purchase LINES
    in the user's own top-`top_n` categories (recomputed directly from
    receipts here, not read from the stored `habitual_categories` field,
    which is top-5 and tuned for a different purpose — display/reporting,
    not this threshold test). Using only the top 3 matters: because
    `category_economics.popularity_weight` already skews which categories
    get bought most often even with NO personal habit at all, top-5
    concentration for a category-popularity-only "shopper" already runs
    ~0.41 in this config — above a naive threshold — while the top-3
    popularity-only baseline is ~0.26, leaving real room for a genuinely
    personal pattern to stand out above it. `min_concentration=0.42` was
    picked by inspecting the actual generated reference profiles: the
    weak-pattern class (`one_off_no_pattern`) measured 0.36-0.47 (mean
    0.41), the other classes 0.39-0.76 (mean 0.49-0.59) — there is real,
    intentional overlap (the reference benchmark's classes are designed to
    be noisy, not perfectly separable), so this will sometimes misclassify
    an edge-case profile in either direction; it is a threshold, not an
    oracle.
    """
    train_end = config.temporal_split.train_end.isoformat()
    train_receipts = [r for r in profile["receipts"] if r["purchase_date"] <= train_end]
    lines = [l for r in train_receipts for l in r["lines"]]

    if not lines:
        return False, {
            "reason": "no train-period purchase history",
            "n_receipts_train": len(train_receipts),
            "concentration": 0.0,
        }

    category_counts = Counter(l["category"] for l in lines)
    top_n_count = sum(count for _, count in category_counts.most_common(top_n))
    concentration = top_n_count / len(lines)
    receptive = len(train_receipts) >= min_receipts and concentration >= min_concentration

    return receptive, {
        "reason": "strong enough pattern" if receptive else "weak/insufficient pattern",
        "n_receipts_train": len(train_receipts),
        "concentration": round(concentration, 3),
    }


def _hash_index(seed_key: str, n: int) -> int:
    return int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest(), 16) % n


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


def pick_sku_in_category(config: SynthConfig, category: str, seed_key: str) -> SKU | None:
    """Deterministically pick one SKU from `category` — same seed_key always
    picks the same SKU. Used for paths that only name a category (generic
    pool, personal/LLM), which never chose a specific item."""
    by_category = skus_by_category(build_catalog(config))
    skus = by_category.get(category)
    if not skus:
        return None
    return skus[_hash_index(seed_key, len(skus))]


def non_forbidden_category_names(config: SynthConfig) -> list[str]:
    """Every catalog category name minus `forbidden_categories` — the exact
    set of names the LLM is allowed to name in `target_categories` for
    `llm_habit`/`llm_discovery`. Passed to `parse_and_validate_challenge` as
    `allowed_categories` and spelled out in `build_personal_prompt`'s system
    text, the same way `vibe`/`llm_basket` already constrain their own
    prompts — without this, the LLM was free to invent near-miss category
    names (e.g. "мясо, птица, рыба" instead of the real "мясо и птица" /
    "рыба и морепродукты"), which passed this function's own forbidden-list
    check but then failed DB category resolution downstream in
    `ChallengeAdapter.resolve_criterion`."""
    forbidden = set(config.forbidden_categories)
    return [c.name for c in config.categories if c.name not in forbidden]


def find_sku_id_for_item(config: SynthConfig, category: str, item: str) -> str | None:
    """Resolve a (category, item) text pair — already chosen by a
    deterministic builder (spend_threshold's favorite_item, category_expansion's
    novel_item) — to its stable catalog sku_id."""
    catalog = build_catalog(config)
    for sku in catalog.values():
        if sku.category == category and sku.item == item:
            return sku.sku_id
    return None


def _pluralize_times(n: int) -> str:
    """Russian plural of "раз" (time/times) for a count — e.g. 1 раз,
    2/3/4 раза, 5-20 раз."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} раз"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} раза"
    return f"{n} раз"


_DESCRIPTION_TEMPLATES: dict[str, str] = {
    "generic": "Купи «{item}» {times} и получи {points} баллов кэшбэком.",
    "llm_habit": "Продолжай в том же духе: возьми «{item}» {times} — начислим {points} баллов кэшбэком.",
    "llm_discovery": "Попробуй новое: «{item}» хотя бы {times} — и мы начислим {points} баллов кэшбэком.",
    "llm_basket": "Добавь «{item}» в свою обычную корзину на этой неделе — получишь {points} баллов кэшбэком.",
    "vibe": "В тему месяца: «{item}» {times} — и +{points} баллов кэшбэком.",
}


def item_action_description(item: str, quantity: int, reward_rub: float, slot: str = "generic") -> str:
    """The concrete, trackable action behind a challenge — names the exact
    item and count progress is measured against (target_sku_id/
    target_quantity), so the copy never promises more than that (a whole
    category, a spend threshold) when the tracking can't actually honor it.
    Used for generic-pool and personal/llm offers, which only ever named a
    category — spend_threshold/category_expansion already name their own
    specific item in their description and don't need this.

    `slot` selects one of a small set of fixed phrasings (see
    `_DESCRIPTION_TEMPLATES`) so cards from different challenge_slot values
    read differently even though they share the same underlying "buy N of
    item X, get reward" mechanic — without this, every generic/personal
    challenge collapsed into the exact same sentence, which read as
    repetitive even when the underlying personalization differed. An
    unrecognized slot (unknown/legacy names from before the 5-slot
    redesign) falls back to the `"generic"` phrasing.

    Reward is phrased in points (`_POINTS_PER_RUB`), not rubles — see that
    constant's docstring for why the conversion is hardcoded here."""
    template = _DESCRIPTION_TEMPLATES.get(slot, _DESCRIPTION_TEMPLATES["generic"])
    points = round(reward_rub * _POINTS_PER_RUB)
    return template.format(item=item, times=_pluralize_times(quantity), points=points)


def pick_generic_challenge(user_id: str, config: SynthConfig) -> dict:
    idx = _hash_index(user_id, len(GENERIC_CHALLENGES))
    offer = dict(GENERIC_CHALLENGES[idx])
    sku = pick_sku_in_category(config, offer["target_categories"][0], seed_key=f"{user_id}:sku")
    offer["target_sku_id"] = sku.sku_id if sku else None
    if sku is not None:
        offer["description"] = item_action_description(sku.item, offer["target_quantity"], offer["reward_rub"])
    return offer


def estimate_max_reward_rub(profile: dict, min_reward: float = 20.0, multiplier: float = 4.0) -> float:
    """Reward ceiling from the user's OWN observed margin — same heuristic
    as the reference-profile answer key's `max_reward_rub`
    (`4 x mean observed line margin`), so a personal challenge never
    proposes a reward the unit economics can't support."""
    lines = [l for r in profile["receipts"] for l in r["lines"]]
    if not lines:
        return min_reward
    mean_margin = sum(l["gross_margin_rub"] for l in lines) / len(lines)
    return round(max(min_reward, mean_margin * multiplier), 2)


def build_spend_threshold_challenge(
    profile: dict,
    config: SynthConfig,
    discount_pct: float = 15.0,
    min_purchase_count: int = 6,
) -> dict | None:
    """Deterministic, no-LLM-call challenge: "spend >= threshold_rub in one
    trip, get `discount_pct`% off your favorite product" — but ONLY when
    that product is genuinely bought often, not just whatever happened to
    be the top item in a thin/noisy purchase history.

    Entirely rule-based from OBSERVABLE train-period receipts:
    - favorite product = the single most-frequently-bought (category, item)
      pair, skipping any that falls in a forbidden category, and REQUIRED
      to have been bought at least `min_purchase_count` times in the
      train period — otherwise this returns None rather than building a
      claim on a weak signal. `min_purchase_count=6` was picked by
      inspecting this project's own reference profiles: top-item counts
      ranged 4-18 (mostly 5-13) across a 90-line-ish train history; 6
      comfortably excludes the thin/coincidental cases (e.g. a
      `one_off_no_pattern` profile whose "top" item was bought only 4
      times) while keeping the profiles with a real repeat pattern.
    - threshold_rub = 1.5x the user's own mean receipt total, rounded to
      the nearest 50 rub — a stretch goal calibrated to their own typical
      basket, not a flat number that means something different to every
      user
    - reward_rub = `discount_pct`% of the favorite item's own observed
      average price, clamped by the same margin-based ceiling as the LLM
      path (`estimate_max_reward_rub`)

    Returns None if there isn't enough train-period purchase history to
    identify a favorite product, everything the user buys happens to be in
    a forbidden category, or the most-bought eligible item still doesn't
    clear `min_purchase_count` — the caller should treat all of these the
    same as any other "can't build this challenge" case.
    """
    train_end = config.temporal_split.train_end.isoformat()
    train_receipts = [r for r in profile["receipts"] if r["purchase_date"] <= train_end]
    lines = [l for r in train_receipts for l in r["lines"]]
    if not lines:
        return None

    item_counts = Counter((l["category"], l["item"]) for l in lines)
    favorite = None
    for (cat, item), count in item_counts.most_common():
        if cat in config.forbidden_categories:
            continue
        # most_common() is sorted descending — the first non-forbidden item
        # IS the most-bought eligible one, so if it doesn't clear the bar,
        # nothing lower-count could either.
        if count < min_purchase_count:
            return None
        favorite = (cat, item)
        break
    if favorite is None:
        return None
    fav_category, fav_item = favorite

    fav_prices = [l["regular_unit_price_rub"] for l in lines if (l["category"], l["item"]) == favorite]
    fav_price = sum(fav_prices) / len(fav_prices)

    mean_receipt_total = sum(r["total_rub"] for r in train_receipts) / len(train_receipts)
    threshold_rub = max(100.0, round((mean_receipt_total * 1.5) / 50) * 50)

    max_reward = estimate_max_reward_rub(profile)
    reward_rub = round(min(fav_price * (discount_pct / 100), max_reward), 2)

    return {
        "challenge_title": f"Скидка {discount_pct:.0f}% на {fav_item}",
        "description": (
            f"Потрать от {threshold_rub:.0f} ₽ за один поход в магазин и получи "
            f"скидку {discount_pct:.0f}% на {fav_item}."
        ),
        "target_categories": [fav_category],
        "mechanic": "порог трат + скидка на любимый товар",
        "reward_rub": reward_rub,
        "reasoning": (
            f"«{fav_item}» — самая часто покупаемая позиция пользователя "
            f"({item_counts[favorite]} раз за train-период)."
        ),
        "spend_threshold_rub": threshold_rub,
        "favorite_item": fav_item,
        "baseline_mean_receipt_rub": round(mean_receipt_total, 2),
        "target_sku_id": find_sku_id_for_item(config, fav_category, fav_item),
        "target_quantity": 1,
    }


def build_category_expansion_challenge(
    profile: dict,
    config: SynthConfig,
    discount_pct: float = 5.0,
) -> dict | None:
    """Deterministic, no-LLM-call challenge: a discount on an item from a
    category this user essentially never buys — the opposite target of
    `build_spend_threshold_challenge`.

    `discount_pct=5.0` (not the 15-20% used by the other two challenge
    types) is a deliberate, config-derived choice, not an arbitrary
    smaller number: unlike `build_spend_threshold_challenge`, this
    challenge's reward is NOT discounted for "would have bought it
    anyway" (see `synth/simulation.py`'s expansion-channel docstring — the
    whole point is that it's fully incremental), so `discount_pct` alone
    must stay below the category's own `margin_pct` or every single
    response is a guaranteed per-unit loss regardless of how rare
    responses are. The thinnest ELIGIBLE (non-forbidden) category margin
    in the current config (v0.6.0) is 8.47% (мясо и птица / рыба и
    морепродукты) — 5% leaves real headroom under that floor for every
    category, so a response is unit-economically sound before the
    behavioral question ("did they respond at all") even comes into it.

    Rationale (raised by the user, not originally in this project's design):
    a challenge on a habitual category rewards a purchase that would very
    likely have happened anyway — the reward buys no incremental behavior,
    only margin given away. A challenge on a category the user doesn't buy
    is lower-probability to land, but a response is far more likely to be a
    genuinely NEW purchase, not a subsidized habit. This is the standard
    "always-buyer" problem from uplift/incrementality marketing: targeting
    people who'd convert anyway wastes the reward.

    Entirely rule-based from OBSERVABLE train-period receipts:
    - target category = the LEAST-bought non-forbidden category among ALL
      of `config.categories` (ties broken by category name for
      determinism), including categories with a train-period count of
      zero — those are the most novel by construction.
    - target item = picked deterministically from that category's item
      list via a hash of the user_id (mirrors `pick_generic_challenge`) —
      there's no observed purchase to anchor on, unlike the spend-threshold
      challenge's "favorite item".
    - reward_rub = `discount_pct`% of the category's own CONFIGURED
      `base_price_rub` (there's no per-user observed price for a category
      they don't buy), clamped by the same margin-based ceiling as the
      other paths (`estimate_max_reward_rub`, from the user's own overall
      purchase history — that part IS observable regardless of category).

    Returns None if there isn't enough train-period purchase history to
    compute category counts, or if every one of `config.categories` is a
    forbidden category (never true for this project's schema, but kept for
    the same reason the other builders guard their inputs).
    """
    train_end = config.temporal_split.train_end.isoformat()
    train_receipts = [r for r in profile["receipts"] if r["purchase_date"] <= train_end]
    lines = [l for r in train_receipts for l in r["lines"]]
    if not lines:
        return None

    category_counts = Counter(l["category"] for l in lines)
    econ_by_category = {e.category: e for e in config.category_economics}
    items_by_category = {c.name: c.items for c in config.categories}

    eligible = [c.name for c in config.categories if c.name not in config.forbidden_categories]
    if not eligible:
        return None
    eligible.sort(key=lambda cat: (category_counts.get(cat, 0), cat))
    target_category = eligible[0]

    items = items_by_category[target_category]
    idx = int(hashlib.sha256(profile["user_id"].encode("utf-8")).hexdigest(), 16) % len(items)
    target_item = items[idx]

    base_price = econ_by_category[target_category].base_price_rub
    max_reward = estimate_max_reward_rub(profile)
    reward_rub = round(min(base_price * (discount_pct / 100), max_reward), 2)

    n_purchases = category_counts.get(target_category, 0)

    return {
        "challenge_title": f"Попробуйте: {discount_pct:.0f}% на {target_item}",
        "description": (
            f"Скидка {discount_pct:.0f}% на {target_item} — категория, которую вы "
            "почти не покупаете. Попробуйте что-то новое."
        ),
        "target_categories": [target_category],
        "mechanic": "скидка на новую категорию",
        "reward_rub": reward_rub,
        "reasoning": (
            f"«{target_category}» — наименее покупаемая категория пользователя "
            f"({n_purchases} покупок за train-период) — максимум шансов на инкрементальную, "
            "а не замещающую покупку."
        ),
        "novel_category": target_category,
        "novel_item": target_item,
        "target_sku_id": find_sku_id_for_item(config, target_category, target_item),
        "target_quantity": 1,
    }


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

    resolved_as_of = as_of if as_of is not None else date.today()  # noqa: DTZ011 — calendar date, not a timestamp
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


def build_basket_spend_challenge(
    profile: dict,
    config: SynthConfig,
    markup_pct: float = 30.0,
    cashback_pct: float = 5.0,
) -> dict | None:
    """Deterministic, no-LLM-call `llm_basket` mechanic (product decision —
    replaces the old free-form "assemble your usual weekly basket" LLM
    prompt): buy your #1 usual weekly item AND spend at least a threshold
    in that same trip, for `cashback_pct`% of that threshold back as points.

    threshold_rub = this user's own mean train-period receipt total,
    marked up by `markup_pct`% and rounded to the nearest 100 ₽ — a
    stretch goal calibrated to their own typical basket, same idea as
    `build_spend_threshold_challenge`'s threshold but with this mechanic's
    own markup/rounding.

    The anchor item (`suggested_basket_items[0]`, already ranked by weekly
    purchase frequency in `BasketRepository.suggest_items`) gives the base
    item_quantity criterion something concrete to track — the same role
    `build_spend_threshold_challenge`'s favorite item plays there; the
    actual basket-total requirement is enforced separately via the
    `spend_threshold_rub` criterion (`SCRIPT_FIELD_TO_CRITERION_KIND`).

    Being a pure function of OBSERVABLE train-period stats with no LLM
    call and no rotation, this slot needs the same cross-cycle repeat
    guard as `generic`/`category_expansion`/`spend_threshold` — see
    `_SLOTS_WITHOUT_NATURAL_VARIATION` in `web/.../services/challenge.py`.

    Returns None if there are no suggested weekly-basket items (new user,
    no purchase history) or no train-period receipts to compute a mean
    receipt total from — the caller falls back to a generic offer.
    """
    suggested_items = profile.get("suggested_basket_items") or []
    if not suggested_items:
        return None

    train_end = config.temporal_split.train_end.isoformat()
    train_receipts = [r for r in profile["receipts"] if r["purchase_date"] <= train_end]
    if not train_receipts:
        return None

    mean_receipt_total = sum(r["total_rub"] for r in train_receipts) / len(train_receipts)
    threshold_rub = max(100.0, round(mean_receipt_total * (1 + markup_pct / 100) / 100) * 100)
    reward_rub = round(threshold_rub * (cashback_pct / 100), 2)
    points = round(reward_rub * _POINTS_PER_RUB)

    anchor = suggested_items[0]
    target_sku_id = find_sku_id_for_item(config, anchor["category"], anchor["item"])

    return {
        "challenge_title": "Кэшбэк за полную корзину",
        "description": (
            f"Собери корзину от {threshold_rub:.0f} ₽ за один поход, включая «{anchor['item']}», "
            f"и получи {points} баллов кэшбэком ({cashback_pct:.0f}% от суммы)."
        ),
        "target_categories": [anchor["category"]],
        "mechanic": "кэшбэк за сумму корзины",
        "reward_rub": reward_rub,
        "reasoning": (
            f"Порог рассчитан от среднего чека пользователя ({mean_receipt_total:.0f} ₽) "
            f"+ {markup_pct:.0f}%, округлён до сотен."
        ),
        "spend_threshold_rub": threshold_rub,
        "target_sku_id": target_sku_id,
        "target_quantity": 1,
    }


def summarize_purchase_pattern(profile: dict, config: SynthConfig) -> dict:
    train_end = config.temporal_split.train_end.isoformat()
    train_receipts = [r for r in profile["receipts"] if r["purchase_date"] <= train_end]
    lines = [l for r in train_receipts for l in r["lines"]]
    cat_counts = Counter(l["category"] for l in lines)
    n_receipts = len(train_receipts)
    weekend = sum(1 for r in train_receipts if date.fromisoformat(r["purchase_date"]).weekday() >= 5)
    promo_lines = sum(1 for l in lines if l["on_promo"])
    mean_total = sum(r["total_rub"] for r in train_receipts) / n_receipts if n_receipts else 0.0

    return {
        "n_receipts_90d_train": n_receipts,
        "top_categories": cat_counts.most_common(5),
        "weekend_share": round(weekend / n_receipts, 3) if n_receipts else 0.0,
        "promo_share": round(promo_lines / len(lines), 3) if lines else 0.0,
        "mean_receipt_total_rub": round(mean_total, 2),
    }


def build_personal_prompt(
    profile: dict, config: SynthConfig, max_reward_rub: float, focus: str = "habit"
) -> tuple[str, str]:
    summary = summarize_purchase_pattern(profile, config)
    forbidden = ", ".join(config.forbidden_categories)
    allowed = ", ".join(non_forbidden_category_names(config))

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
        f"target_categories обязаны быть строго из этого списка названий, "
        f"дословно, без сокращений и без объединения нескольких категорий "
        f"через запятую в одну строку: {allowed}\n"
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


def build_basket_prompt(
    profile: dict, config: SynthConfig, max_reward_rub: float, suggested_items: list[dict]
) -> tuple[str, str]:
    """Wraps the user's own deterministic weekly-purchase-frequency list
    (`suggested_items` — from `BasketRepository.suggest_items`, which
    ranks products by how often the user buys them weekly) into a
    challenge encouraging them to buy their usual weekly basket.
    `target_categories` must stay within
    the categories already present in `suggested_items` — enforced by
    `parse_and_validate_challenge`'s `allowed_categories`, not by this
    function. The caller (`generate_challenge_for_user`) never calls this
    with an empty `suggested_items` — there is nothing to wrap into a
    challenge for a user with no purchase history yet, so that case is
    handled as a cold-start fallback before this function is ever reached."""
    suggested_items = suggested_items[:20]
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


def build_vibe_prompt_from_context(
    profile: dict, config: SynthConfig, max_reward_rub: float, vibe_name: str, vibe_context: str
) -> tuple[str, str]:
    """Variant of build_vibe_prompt that uses a free-form llm_context string
    (from VibeType.llm_context) instead of a VIBE_CATEGORIES key lookup.
    This allows POS operators to define custom vibes with arbitrary categories.
    """
    summary = summarize_purchase_pattern(profile, config)

    system = (
        "Ты — модуль персональных рекомендаций программы лояльности X5 "
        "(Пятёрочка/Перекрёсток/Чижик). Пользователю выбран вайб: "
        f'"{vibe_name}". Предложи ОДИН челлендж строго в рамках этого вайба.\n\n'
        f"Контекст вайба (используй как ориентир для target_categories): {vibe_context}\n"
        f"reward_rub не должен превышать {max_reward_rub:.0f} ₽.\n\n"
        "Ответь СТРОГО в виде одного JSON-объекта, без текста вне JSON:\n"
        '{"challenge_title": string, "description": string, '
        '"target_categories": [string, ...], "mechanic": string, '
        '"reward_rub": number, "reasoning": string}'
    )

    user = (
        f"Сеть: {profile['chain']}\n"
        f"Вайб: {vibe_name}\n"
        f"Чеков за 90 дней: {summary['n_receipts_90d_train']}\n"
        f"Топ категорий по числу позиций: {summary['top_categories']}\n"
        f"Средний чек: {summary['mean_receipt_total_rub']:.0f} ₽\n"
    )
    return system, user


def call_openrouter(
    model: str,
    system: str,
    user: str,
    api_key: str | None = None,
    timeout: float = 60.0,
    max_retries: int = 3,
) -> str:
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (env var, or pass api_key explicitly)")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.4,
                },
                timeout=timeout,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise RuntimeError(f"OpenRouter transient error {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (requests.RequestException, RuntimeError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"OpenRouter call failed after {max_retries} attempts: {last_error}")


def _strip_code_fence(text: str) -> str:
    """Some OpenRouter routes (observed: anthropic/claude-haiku-4.5 via the
    Amazon Bedrock upstream) wrap JSON output in a markdown code fence even
    with `response_format: json_object` set — strip it before parsing."""
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
    return match.group(1).strip() if match else text


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


def compute_frequency_saturation(
    profile: dict,
    config: SynthConfig,
    min_receipts_for_no_challenge: int = 85,
) -> tuple[bool, dict]:
    """Observable-only "this user is already buying so often that a
    challenge probably isn't worth issuing" signal — the third routing
    outcome, alongside personal/generic.

    Uses raw train-period receipt COUNT, not the hidden
    `frequency_headroom`/`baseline_visits_28d` fields. `min_receipts_for_no_challenge=85`
    was picked by inspecting this project's own generated reference
    profiles after the 0.5.0 frequency-calibration fix (see that config
    version's changelog): the `already_optimal_no_challenge` class measured
    87-92 train-period receipts (mean 88.8), while every other reference
    class stayed at or below 82, and the general population's 99th
    percentile sat at 89 — so 85 sits in the gap between "a genuinely
    unusual amount of shopping" and "everyone else," with a real margin on
    both sides. Before that fix, receipt count saturated at a shared
    day-count ceiling for a large fraction of the population and could not
    be used this way at all — see `synth/receipts.py`'s docstring.
    """
    train_end = config.temporal_split.train_end.isoformat()
    n_receipts_train = sum(1 for r in profile["receipts"] if r["purchase_date"] <= train_end)
    saturated = n_receipts_train >= min_receipts_for_no_challenge
    return saturated, {"n_receipts_train": n_receipts_train, "threshold": min_receipts_for_no_challenge}


# The five independent challenge slots every user gets, one attempt each,
# unconditionally. llm_habit/llm_discovery/generic are risk-ranked picks
# from build_survival_risk_challenge (no LLM call); llm_basket is the
# deterministic build_basket_spend_challenge; vibe is the only slot that
# still calls the LLM (see generate_challenge_for_user's docstring).
CHALLENGE_SLOTS = ("llm_habit", "llm_discovery", "llm_basket", "generic", "vibe")


def _pick_distinct_generic_offer(
    user_id: str, config: SynthConfig, used_indices: list[int], cycle_offset: int = 0
) -> dict:
    """Like `pick_generic_challenge`, but skips any offer index already used
    for this user's other slots — so a user who falls back to generic on
    more than one slot gets distinct offers, not duplicate cards.

    `cycle_offset` rotates the STARTING index by a fixed amount before the
    within-batch distinctness check — used only by the dedicated `generic`
    slot in `generate_challenge_for_user` (via `profile["generic_cycle_index"]`,
    a count of that user's past `generic`-slot tasks), so the same user's
    generic offer actually changes across generation cycles instead of
    being pinned forever by `ChallengeService.generate_batch`'s cross-cycle
    dedup check (the hash-based pick alone is 100% stable per user with no
    cycle component). Left at its default (0) for every OTHER caller — the
    `_generic()` fallback used by `llm_habit`/`llm_discovery`/`llm_basket`/
    `vibe` on failure — whose own repeat behavior is unrelated to this."""
    idx = (_hash_index(f"{user_id}:generic", len(GENERIC_CHALLENGES)) + cycle_offset) % len(GENERIC_CHALLENGES)
    while idx in used_indices:
        idx = (idx + 1) % len(GENERIC_CHALLENGES)
    used_indices.append(idx)
    offer = dict(GENERIC_CHALLENGES[idx])
    sku = pick_sku_in_category(config, offer["target_categories"][0], seed_key=f"{user_id}:sku:{idx}")
    offer["target_sku_id"] = sku.sku_id if sku else None
    if sku is not None:
        offer["description"] = item_action_description(sku.item, offer["target_quantity"], offer["reward_rub"])
    return offer


def generate_challenge_for_user(
    profile: dict,
    config: SynthConfig,
    model: str,
    api_key: str | None = None,
    dry_run: bool = False,
    vibe_month_key: str | None = None,
    category_curves: dict[str, SurvivalCurve] | None = None,
) -> list[dict]:
    """Route one profile to exactly `len(CHALLENGE_SLOTS)` records — one per
    slot (`llm_habit`, `llm_discovery`, `llm_basket`, `generic`, `vibe`) —
    for EVERY user, regardless of purchase-pattern strength or frequency.
    There is no saturation/receptiveness gate here any more: a thin/noisy
    purchase history degrades gracefully through the LLM prompt
    (`summarize_purchase_pattern` already renders "—" for empty fields)
    rather than being rejected upfront.

    `llm_habit`, `llm_discovery`, and `generic` are all
    `build_survival_risk_challenge` picks (ranks 0, 1, 2 by churn risk) —
    no LLM call for any of them. Each falls back to a (slot-distinct)
    generic offer when the user has no purchase history or that rank isn't
    available. `vibe` is the only slot left that calls the LLM, constrained
    to the user's monthly theme: `profile["vibe_category"]` if
    the caller already resolved/persisted one (the web layer always does,
    see `ChallengeAdapter._resolve_vibe_category`), otherwise
    `pick_vibe_category` picks one deterministically from `vibe_month_key`
    (defaults to the current UTC year-month) so offline/dry-run calls
    without a DB-backed profile still get a stable answer.

    `llm_basket` is deterministic, not LLM-driven despite the name (kept
    for slot-name/DB stability) — see `build_basket_spend_challenge`. It
    uses the user's own weekly-purchase-frequency list
    (`profile.get("suggested_basket_items")`, populated by the web layer
    from `BasketRepository.suggest_items` — see
    `ChallengeAdapter._suggested_basket_items`) to pick an anchor item, and
    the user's own mean receipt total to compute a spend threshold + cashback.
    If there are no suggested items or no train-period receipts (new user,
    no purchase history), this slot falls straight to a generic offer, the
    same way the other deterministic builders return `None` on insufficient
    history.

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
            if slot == "vibe":
                # Product decision: mark vibe cards as part of the month's
                # themed selection in the title itself, not just the body —
                # otherwise a vibe card reads exactly like an ordinary
                # personal challenge with no visible tie to the chosen theme.
                challenge["challenge_title"] = f"Вайб месяца: {challenge['challenge_title']}"
            quantity = SLOT_TARGET_QUANTITY.get(slot, PERSONAL_TARGET_QUANTITY)
            challenge["target_quantity"] = quantity
            sku = pick_sku_in_category(config, challenge["target_categories"][0], seed_key=f"{profile['user_id']}:sku:{slot}")
            challenge["target_sku_id"] = sku.sku_id if sku else None
            if sku is not None:
                challenge["description"] = item_action_description(
                    sku.item, quantity, challenge["reward_rub"], slot=slot
                )
            results.append({
                "user_id": profile["user_id"], "path": "personal",
                "model": model, "challenge_slot": slot, **challenge,
                "prompt": f"[SYSTEM]\n{system}\n\n[USER]\n{user_msg}",
                "response": raw,
            })
        except Exception as e:  # noqa: BLE001 — deliberately broad: any failure must fall back, not propagate
            results.append(_generic(slot, "generic_fallback", error=str(e), model_attempted=model))

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

    # slot: llm_basket — deterministic (see `build_basket_spend_challenge`):
    # spend threshold from the user's own mean receipt total, cashback
    # reward as a % of that threshold. No LLM call for this slot any more
    # (the old free-form "assemble your basket" prompt let the LLM pick a
    # forbidden category from the user's own real weekly basket — e.g.
    # "детское питание" — which then failed validation deterministically
    # every cycle; this mechanic sidesteps that entirely).
    #
    # Drop forbidden-category items before picking an anchor — the anchor
    # is item [0] of `suggested_basket_items`, so a forbidden category
    # there would otherwise become the challenge's own target_categories.
    basket_profile = {
        **profile,
        "suggested_basket_items": [
            item for item in (profile.get("suggested_basket_items") or [])
            if item["category"] not in config.forbidden_categories
        ],
    }
    basket_challenge = build_basket_spend_challenge(basket_profile, config)
    if basket_challenge is None:
        results.append(_generic(
            "llm_basket", "generic_fallback",
            error="no suggested weekly-basket items or train-period receipts to compute a basket threshold from",
        ))
    else:
        results.append({
            "user_id": profile["user_id"], "path": "personal",
            "model": None, "challenge_slot": "llm_basket", **basket_challenge,
        })

    # slot: vibe
    # If user has a VibeType selected, profile["vibe_context"] carries its
    # llm_context (comma-separated category list). Fall back to the old
    # VIBE_CATEGORIES-based logic for users without a vibe selection.
    vibe_context: str | None = profile.get("vibe_context")
    if vibe_context:
        vibe_category = profile.get("vibe_category") or pick_vibe_category(
            profile["user_id"], vibe_month_key or date.today().strftime("%Y-%m")
        )
        # Parse allowed categories from llm_context (comma-separated list).
        allowed_from_context = {cat.strip() for cat in vibe_context.split(",") if cat.strip()}
        system, user_msg = build_vibe_prompt_from_context(profile, config, max_reward, vibe_category, vibe_context)
        _run_llm_slot("vibe", system, user_msg, allowed_categories=allowed_from_context or None)
    else:
        vibe_category = profile.get("vibe_category") or pick_vibe_category(
            profile["user_id"], vibe_month_key or date.today().strftime("%Y-%m")
        )
        if vibe_category not in VIBE_CATEGORIES:
            vibe_category = pick_vibe_category(
                profile["user_id"], vibe_month_key or date.today().strftime("%Y-%m")
            )
        system, user_msg = build_vibe_prompt(profile, config, max_reward, vibe_category)
        _run_llm_slot("vibe", system, user_msg, allowed_categories=set(VIBE_CATEGORIES[vibe_category]))

    return results


def generate_challenges(
    profiles: list[dict],
    config: SynthConfig,
    model: str,
    api_key: str | None = None,
    dry_run: bool = False,
    delay_seconds: float = 0.0,
) -> list[dict]:
    results: list[dict] = []
    for i, profile in enumerate(profiles):
        batch = generate_challenge_for_user(profile, config, model, api_key, dry_run)
        results.extend(_replace_legacy_slots_with_deterministic(profile, config, batch))
        if not dry_run and delay_seconds > 0 and i < len(profiles) - 1:
            time.sleep(delay_seconds)
    return results


def _replace_legacy_slots_with_deterministic(
    profile: dict, config: SynthConfig, script_results: list[dict]
) -> list[dict]:
    """Put the implemented deterministic mechanics into generated batches.

    The single-profile router still owns the legacy five-slot LLM/generic
    contract because it is also used by older callers. Batch generation is
    the user-facing path, so replace the generic and basket slots there with
    the already implemented spend-threshold and category-expansion builders.
    A builder may return ``None`` for insufficient history; in that case the
    original fallback record is preserved.
    """
    replacements = (
        ("llm_basket", "spend_threshold", build_spend_threshold_challenge),
        ("generic", "category_expansion", build_category_expansion_challenge),
    )
    replacement_by_slot: dict[str, dict] = {}
    for legacy_slot, challenge_slot, builder in replacements:
        challenge = builder(profile, config)
        if challenge is None:
            continue
        replacement_by_slot[legacy_slot] = {
            "user_id": profile["user_id"],
            # Keep the persisted path compatible with the web Task enum. The
            # concrete deterministic mechanic is carried by challenge_slot.
            "path": "personal",
            "model": None,
            "challenge_slot": challenge_slot,
            **challenge,
        }

    return [
        replacement_by_slot.get(result.get("challenge_slot"), result)
        for result in script_results
    ]


def backfill_target_sku(challenges: list[dict], config: SynthConfig) -> list[dict]:
    """Add target_sku_id/target_quantity to challenge records written before
    these fields existed, without re-calling the LLM.

    Uses whatever item-level info the record already carries
    (favorite_item/novel_item from the deterministic spend_threshold/
    category_expansion paths) when present; otherwise falls back to the
    same category-hash pick used for newly-generated generic/personal
    records (`pick_sku_in_category`). Records that already have
    target_sku_id, or that carry no target_categories at all
    (`no_challenge`), pass through unchanged.
    """
    result: list[dict] = []
    for original in challenges:
        c = dict(original)
        if "target_sku_id" in c or not c.get("target_categories"):
            result.append(c)
            continue

        category = c["target_categories"][0]
        item = c.get("favorite_item") or c.get("novel_item")
        sku_id = find_sku_id_for_item(config, category, item) if item else None
        if sku_id is not None:
            c["target_quantity"] = 1
        else:
            sku = pick_sku_in_category(config, category, seed_key=f"{c['user_id']}:sku")
            sku_id = sku.sku_id if sku else None
            c["target_quantity"] = PERSONAL_TARGET_QUANTITY

        c["target_sku_id"] = sku_id
        result.append(c)
    return result


def rewrite_descriptions_for_tracked_item(challenges: list[dict], config: SynthConfig) -> list[dict]:
    """Rewrite `description` to name the exact target_sku_id/target_quantity
    a record tracks, for records whose original copy described a whole
    category instead — generic-pool offers and llm-slot personal
    challenges. No LLM call needed: the item is looked up from the
    already-resolved target_sku_id.

    A record already names its own specific item — and is left untouched —
    only if it carries `favorite_item`/`novel_item`, set exclusively by
    `build_spend_threshold_challenge`/`build_category_expansion_challenge`
    when they actually succeed. `challenge_slot` alone is NOT a reliable
    signal here: a `generic_fallback` record still carries
    `challenge_slot="spend_threshold"` (naming which slot it's replacing)
    while its actual copy came from `GENERIC_CHALLENGES` — category-level,
    same as any other generic offer — so it must still be rewritten.
    `no_challenge` records and any record whose target_sku_id didn't
    resolve to a real catalog SKU are left untouched.

    Only a `path == "personal"` record's own `challenge_slot` picks its
    phrasing template (see `item_action_description`) — a `generic`/
    `generic_fallback` record's copy is genuinely generic-pool content
    regardless of which slot name it's tagged under (see the
    `challenge_slot` caveat above), so it always gets the `"generic"`
    phrasing, matching what the live generator does for that same case.
    """
    catalog = build_catalog(config)
    result: list[dict] = []
    for original in challenges:
        c = dict(original)
        sku_id = c.get("target_sku_id")
        already_item_specific = c.get("favorite_item") or c.get("novel_item")
        needs_rewrite = sku_id in catalog and not already_item_specific
        if needs_rewrite:
            slot = c.get("challenge_slot") if c.get("path") == "personal" else "generic"
            c["description"] = item_action_description(
                catalog[sku_id].item,
                c.get("target_quantity", PERSONAL_TARGET_QUANTITY),
                c.get("reward_rub", 0.0),
                slot=slot or "generic",
            )
        result.append(c)
    return result


def write_challenges_json(path: str | Path, challenges: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(challenges, f, ensure_ascii=False, indent=2)


def score_against_answer_key(challenges: list[dict], answer_key: list[dict]) -> dict:
    """Hit-rate scorer against the reference answer key.

    `abstain_is_correct` means the answer key expects NO personal, LLM-
    generated claim for this profile — it covers two different reasons
    (see `synth/reference_profiles.py::_draft_answer_key_entry`):
    `one_off_no_pattern` (pattern too weak to personalize confidently — a
    generic offer is the honest response) and `already_optimal_no_challenge`
    (purchase frequency is already saturated — no offer, personal or
    generic, is warranted). A hit is therefore any path that is NOT an
    unfounded personal claim: `no_challenge`, `generic`, or
    `generic_fallback`. Only `personal`/`personal_dry_run` counts as a miss
    for these profiles.
    """
    key_by_id = {a["user_id"]: a for a in answer_key}
    hits = 0
    scored = 0
    details: list[dict] = []

    for c in challenges:
        key = key_by_id.get(c["user_id"])
        if not key:
            continue
        scored += 1

        if key["abstain_is_correct"]:
            hit = c["path"] in ("no_challenge", "generic", "generic_fallback")
        else:
            target_hit = bool(set(c.get("target_categories", [])) & set(key["acceptable_target_categories"]))
            mechanic_hit = c.get("mechanic") in key["acceptable_mechanics"]
            hit = target_hit or mechanic_hit

        hits += int(hit)
        details.append({"user_id": c["user_id"], "hit": hit, "path": c["path"]})

    rate = hits / scored if scored else 0.0
    return {"hit_rate": round(rate, 3), "hits": hits, "scored": scored, "details": details}
