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

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Default target_quantity for paths that only name a category, not a
# specific item (generic pool + personal/LLM) — the LLM prompt doesn't ask
# for a unit count, and the generic pool's mechanics are worded as
# spend-threshold/percentage offers rather than "buy N", so this is a
# deliberate simplification to fit the single sku_id+quantity progress
# model, not a value derived from the offer's own text.
PERSONAL_TARGET_QUANTITY = 2

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


def item_action_description(item: str, quantity: int, reward_rub: float) -> str:
    """The concrete, trackable action behind a challenge — names the exact
    item and count progress is measured against (target_sku_id/
    target_quantity), so the copy never promises more than that (a whole
    category, a spend threshold) when the tracking can't actually honor it.
    Used for generic-pool and personal/llm offers, which only ever named a
    category — spend_threshold/category_expansion already name their own
    specific item in their description and don't need this."""
    return f"Купи «{item}» {_pluralize_times(quantity)} и получи {reward_rub:.0f} ₽."


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


# The four independent challenge slots every user gets, one attempt each,
# unconditionally — no receptiveness/saturation gate decides who gets
# personalization any more (see `compute_receptiveness`/
# `compute_frequency_saturation`, still used by `synth/simulation.py`'s
# offline effect model, but no longer by `generate_challenge_for_user`).
CHALLENGE_SLOTS = ("llm_habit", "llm_discovery", "generic", "vibe")


def _pick_distinct_generic_offer(user_id: str, config: SynthConfig, used_indices: list[int]) -> dict:
    """Like `pick_generic_challenge`, but skips any offer index already used
    for this user's other slots — so a user who falls back to generic on
    more than one slot gets distinct offers, not duplicate cards."""
    idx = _hash_index(f"{user_id}:generic", len(GENERIC_CHALLENGES))
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
    everyone (not just as a fallback, unlike before) — it is drawn FIRST in
    the code below, before any LLM slot is attempted, so its own offer
    never depends on whether an earlier LLM slot happened to fail and
    consume a `used_generic_indices` pool slot this cycle. `vibe` calls the LLM
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
                "prompt": f"[SYSTEM]\n{system}\n\n[USER]\n{user_msg}",
                "response": raw,
            })
        except Exception as e:  # noqa: BLE001 — deliberately broad: any failure must fall back, not propagate
            results.append(_generic(slot, "generic_fallback", error=str(e), model_attempted=model))

    # slot: generic — deterministic, no API call, always attempted for
    # everyone. Drawn FIRST, before any LLM slot is attempted, so its own
    # offer never depends on whether an earlier LLM slot happened to fail
    # this cycle (a failed LLM slot also draws from this same
    # used_generic_indices pool via `_generic`/`_pick_distinct_generic_offer`).
    offer = _pick_distinct_generic_offer(profile["user_id"], config, used_generic_indices)
    results.append({
        "user_id": profile["user_id"], "path": "generic",
        "model": None, "challenge_slot": "generic", **offer,
    })

    # slot: llm_habit
    system, user_msg = build_personal_prompt(profile, config, max_reward, focus="habit")
    _run_llm_slot("llm_habit", system, user_msg)

    # slot: llm_discovery
    system, user_msg = build_personal_prompt(profile, config, max_reward, focus="discovery")
    _run_llm_slot("llm_discovery", system, user_msg)

    # slot: vibe
    vibe_category = profile.get("vibe_category") or pick_vibe_category(
        profile["user_id"], vibe_month_key or date.today().strftime("%Y-%m")
    )
    if vibe_category not in VIBE_CATEGORIES:
        # `vibe_category` is a nullable free-text column with no CHECK
        # constraint (by design, to stay flexible for a future
        # manual-selection feature) — nothing guarantees a persisted value
        # is still one of the 6 known theme keys. Never let an unrecognized
        # value crash all 4 slots; fall back to a freshly-picked valid one.
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
        results.extend(generate_challenge_for_user(profile, config, model, api_key, dry_run))
        if not dry_run and delay_seconds > 0 and i < len(profiles) - 1:
            time.sleep(delay_seconds)
    return results


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
    """
    catalog = build_catalog(config)
    result: list[dict] = []
    for original in challenges:
        c = dict(original)
        sku_id = c.get("target_sku_id")
        already_item_specific = c.get("favorite_item") or c.get("novel_item")
        needs_rewrite = sku_id in catalog and not already_item_specific
        if needs_rewrite:
            c["description"] = item_action_description(
                catalog[sku_id].item, c.get("target_quantity", PERSONAL_TARGET_QUANTITY), c.get("reward_rub", 0.0)
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
