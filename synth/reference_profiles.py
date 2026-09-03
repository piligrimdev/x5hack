from __future__ import annotations

import csv
import json
import random
import uuid
from dataclasses import asdict
from pathlib import Path

from synth.catalog import build_catalog, skus_by_category
from synth.config import SynthConfig
from synth.entities import assign_chains_and_segments, assign_households, build_districts
from synth.features import compute_observable_habitual_categories
from synth.receipts import generate_receipts_for_user
from synth.simulation_truth import generate_user_behavior

GENERATION_CLASSES: tuple[str, ...] = (
    "bakes_on_weekends",
    "promo_hunter",
    "one_off_no_pattern",
    "ambiguous_mixed",
    "already_optimal_no_challenge",
)

_BAKING_CATEGORIES = ("бакалея", "хлеб и выпечка", "молочные продукты и яйца")


def _class_params(
    generation_class: str, config: SynthConfig, rng: random.Random
) -> dict:
    """Return the generate_receipts_for_user kwargs + overrides for one
    generation class. Every class is deliberately noisy (parameters drawn
    from a range, not a fixed value) so the resulting archetypes overlap
    rather than being perfectly, trivially separable by a simple threshold
    rule on any one statistic — a real benchmark should require the
    recommender to actually read the purchase history."""
    category_names = [c.name for c in config.categories]

    if generation_class == "bakes_on_weekends":
        baking = [c for c in category_names if c in _BAKING_CATEGORIES]
        if len(baking) != 3:
            raise ValueError(f"expected 3 baking categories in config, found {len(baking)}: {baking}")
        extra = rng.sample([c for c in category_names if c not in baking], k=rng.choice([1, 2]))
        return {
            "habitual_categories": baking + extra,
            "habitual_bias_strength": rng.uniform(0.55, 0.75),
            "promo_affinity_override": rng.uniform(0.10, 0.25),
            "weekend_bias": rng.uniform(0.35, 0.65),
            "frequency_multiplier_override": None,
            "frequency_headroom_override": None,
        }

    if generation_class == "promo_hunter":
        return {
            "habitual_categories": rng.sample(category_names, k=rng.randint(3, 6)),
            "habitual_bias_strength": rng.uniform(0.50, 0.70),
            "promo_affinity_override": rng.uniform(0.25, 0.55),
            "weekend_bias": 0.0,
            "frequency_multiplier_override": None,
            "frequency_headroom_override": None,
        }

    if generation_class == "one_off_no_pattern":
        return {
            "habitual_categories": rng.sample(category_names, k=rng.choice([1, 2])),
            "habitual_bias_strength": rng.uniform(0.15, 0.30),
            "promo_affinity_override": rng.uniform(0.10, 0.20),
            "weekend_bias": 0.0,
            "frequency_multiplier_override": None,
            "frequency_headroom_override": None,
        }

    if generation_class == "ambiguous_mixed":
        baking_subset = rng.sample(list(_BAKING_CATEGORIES), k=rng.choice([1, 2]))
        other = rng.sample([c for c in category_names if c not in baking_subset], k=rng.randint(2, 4))
        return {
            "habitual_categories": baking_subset + other,
            "habitual_bias_strength": rng.uniform(0.40, 0.60),
            "promo_affinity_override": rng.uniform(0.20, 0.40),
            "weekend_bias": rng.uniform(0.25, 0.45),
            "frequency_multiplier_override": None,
            "frequency_headroom_override": None,
        }

    if generation_class == "already_optimal_no_challenge":
        return {
            "habitual_categories": rng.sample(category_names, k=rng.randint(3, 5)),
            "habitual_bias_strength": rng.uniform(0.60, 0.75),
            "promo_affinity_override": rng.uniform(0.10, 0.20),
            "weekend_bias": 0.0,
            "frequency_multiplier_override": rng.uniform(1.8, 2.5),
            "frequency_headroom_override": rng.uniform(0.0, 0.06),
        }

    raise ValueError(f"unknown generation class: {generation_class}")


def default_class_list(count: int, seed: int) -> list[str]:
    """`count` generation-class assignments, round-robin across the 5
    classes then SHUFFLED — round-robin keeps class counts balanced,
    shuffling keeps the class from being recoverable just from a profile's
    position in the list (position alone must not leak the label)."""
    base = [GENERATION_CLASSES[i % len(GENERATION_CLASSES)] for i in range(count)]
    random.Random(seed).shuffle(base)
    return base


def _deterministic_uuid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def reference_profiles(generation_classes: list[str], seed: int, config: SynthConfig) -> list[dict]:
    """Generate one reference profile per entry in `generation_classes`.

    Each profile gets a random (not sequential) UUID `user_id` so the ID
    itself carries no information about which class generated it, and the
    5 generation classes are deliberately noisy/overlapping (see
    `_class_params`) rather than trivially separable, including classes
    for "no discernible pattern" and "already optimal — no challenge
    needed" so a benchmark based on this data can't be solved by a rule
    like "habitual_categories is null -> one_off".
    """
    districts = build_districts(config.districts)
    entity_users, entity_households = assign_households(
        len(generation_classes), districts, config.household_size_weights, seed
    )
    households_by_id = {h.household_id: h for h in entity_households}

    chain_segment_seed = seed * 1_000_003 + 900_000_002
    chain_segments = assign_chains_and_segments(len(generation_classes), config.chains, chain_segment_seed)
    chains_by_name = {c.name: c for c in config.chains}
    segments_by_name = {s.name: s for s in config.segments}

    catalog = build_catalog(config)
    catalog_by_category = skus_by_category(catalog)

    result: list[dict] = []
    for i, generation_class in enumerate(generation_classes):
        id_seed = seed * 8 + i * 8 + 4
        class_seed = seed * 8 + i * 8 + 5
        behavior_seed = seed * 8 + i * 8 + 6
        receipt_seed = seed * 8 + i * 8 + 7

        user_id = _deterministic_uuid(random.Random(id_seed))
        class_rng = random.Random(class_seed)
        params = _class_params(generation_class, config, class_rng)

        chain_name, segment_name = chain_segments[i]
        chain_price_multiplier = chains_by_name[chain_name].price_multiplier
        segment_behavior = segments_by_name[segment_name]

        entity_user = entity_users[i]
        household = households_by_id[entity_user.household_id]

        receipt_kwargs, truth = generate_user_behavior(
            user_id,
            config,
            segment_behavior,
            household.family_size,
            params["habitual_categories"],
            behavior_seed,
            promo_affinity_override=params["promo_affinity_override"],
            frequency_multiplier_override=params["frequency_multiplier_override"],
            frequency_headroom_override=params["frequency_headroom_override"],
        )

        receipts = generate_receipts_for_user(
            user_id,
            config,
            catalog,
            catalog_by_category,
            seed=receipt_seed,
            habitual_categories=params["habitual_categories"],
            habitual_bias_strength=params["habitual_bias_strength"],
            weekend_bias=params["weekend_bias"],
            price_multiplier=chain_price_multiplier,
            frequency_multiplier=receipt_kwargs["frequency_multiplier"],
            basket_size_multiplier=receipt_kwargs["basket_size_multiplier"],
            promo_affinity=receipt_kwargs["promo_affinity"],
        )

        observable_habitual = compute_observable_habitual_categories(receipts, config)

        result.append(
            {
                "user_id": user_id,
                "household_id": entity_user.household_id,
                "district_id": entity_user.district_id,
                "family_size": household.family_size,
                "chain": chain_name,
                "segment": segment_name,
                "generation_class": generation_class,
                "habitual_categories": observable_habitual,
                "receipts": [
                    {**asdict(r), "lines": [asdict(l) for l in r.lines]} for r in receipts
                ],
                "_simulation_truth": {"user_id": user_id, **asdict(truth)},
            }
        )

    return result


def write_reference_profiles_json(path: str | Path, profiles: list[dict]) -> None:
    """Full file: everything, including `generation_class` and
    `_simulation_truth` — for internal use (building the answer key,
    evaluating hit rate), never handed to a blind labeler."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


_HIDDEN_FIELDS = ("generation_class", "_simulation_truth")


def write_blind_reference_profiles_json(path: str | Path, profiles: list[dict], seed: int) -> None:
    """Write profiles for blind labeling: no `generation_class`, no
    `_simulation_truth`, shuffled order. A labeler must not be able to
    infer the class from a hidden field (dropped) or from position in the
    file (shuffled — `default_class_list` already shuffles the assignment
    itself, but the file order is reshuffled again independently here so
    that even someone who knew the class-assignment algorithm couldn't
    invert file position back to class)."""
    rng = random.Random(seed)
    blind = [{k: v for k, v in p.items() if k not in _HIDDEN_FIELDS} for p in profiles]
    rng.shuffle(blind)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blind, f, ensure_ascii=False, indent=2)


def _draft_answer_key_entry(profile: dict, config: SynthConfig) -> dict:
    generation_class = profile["generation_class"]
    truth = profile["_simulation_truth"]
    forbidden = list(config.forbidden_categories)
    # acceptable_target_categories must never include a forbidden category —
    # habitual_categories is generated without regard to forbidden status
    # (a synthetic user can plausibly habitually buy алкоголь), but it would
    # be self-contradictory for the SAME answer key entry to both list a
    # category as forbidden and mark it acceptable to challenge on.
    habitual = [c for c in (profile["habitual_categories"] or []) if c not in forbidden]

    receipts = profile["receipts"]
    margins = [line["gross_margin_rub"] for r in receipts for line in r["lines"]]
    mean_line_margin = sum(margins) / len(margins) if margins else 5.0
    max_reward_rub = round(max(20.0, mean_line_margin * 4), 2)

    if generation_class == "bakes_on_weekends":
        baking_habitual = [c for c in habitual if c in _BAKING_CATEGORIES] or list(_BAKING_CATEGORIES)
        return {
            "acceptable_challenges": [
                "скидка/бонус на бакалею и выпечку в выходные",
                "напоминание докупить недостающий ингредиент для выпечки",
            ],
            "acceptable_target_categories": baking_habitual,
            "acceptable_mechanics": ["персональная скидка", "достижение/бейдж"],
            "forbidden_categories": forbidden,
            "max_reward_rub": max_reward_rub,
            "relevance_reason": "Регулярная выпечка по выходным — устойчивый паттерн в категориях бакалеи/хлеба/молочки.",
            "abstain_is_correct": False,
        }

    if generation_class == "promo_hunter":
        return {
            "acceptable_challenges": [
                "кэшбэк/бонус за регулярные покупки по акции",
                "персональный купон на привычную категорию",
            ],
            "acceptable_target_categories": habitual,
            "acceptable_mechanics": ["кэшбек", "бонусные баллы", "купон"],
            "forbidden_categories": forbidden,
            "max_reward_rub": max_reward_rub,
            "relevance_reason": "Высокая доля покупок по акции — челлендж вокруг промо-механик релевантен.",
            "abstain_is_correct": False,
        }

    if generation_class == "one_off_no_pattern":
        return {
            "acceptable_challenges": [],
            "acceptable_target_categories": [],
            "acceptable_mechanics": [],
            "forbidden_categories": forbidden,
            "max_reward_rub": 0.0,
            "relevance_reason": "Слабый/непоследовательный паттерн покупок — специфичный челлендж рискует быть нерелевантным.",
            "abstain_is_correct": True,
        }

    if generation_class == "ambiguous_mixed":
        return {
            "acceptable_challenges": [
                "скидка на смешанную группу привычных категорий",
                "промо-купон на одну из привычных категорий",
            ],
            "acceptable_target_categories": habitual,
            "acceptable_mechanics": ["персональная скидка", "купон", "бонусные баллы"],
            "forbidden_categories": forbidden,
            "max_reward_rub": max_reward_rub,
            "relevance_reason": "Смешанный паттерн — несколько правдоподобных гипотез, широкий диапазон приемлемых ответов.",
            "abstain_is_correct": False,
        }

    if generation_class == "already_optimal_no_challenge":
        return {
            "acceptable_challenges": [],
            "acceptable_target_categories": [],
            "acceptable_mechanics": [],
            "forbidden_categories": forbidden,
            "max_reward_rub": 0.0,
            "relevance_reason": (
                f"Уже высокая частота покупок (baseline_visits_28d={truth['baseline_visits_28d']}, "
                f"frequency_headroom={truth['frequency_headroom']}) — доп. челлендж экономически не оправдан."
            ),
            "abstain_is_correct": True,
        }

    raise ValueError(f"unknown generation class: {generation_class}")


def build_answer_key(profiles: list[dict], config: SynthConfig) -> list[dict]:
    """Draft ground-truth answer key for hit-rate evaluation — one entry
    per reference profile, heuristically derived from the (hidden)
    generation class and simulation truth. Marked `draft: true`: per spec
    requirement, a teammate other than the generator's author must
    manually confirm or correct each row (via the CSV template) before
    it's used to score anything, to avoid the same circularity the blind
    labeling process exists to prevent.
    """
    entries = []
    for p in profiles:
        entry = _draft_answer_key_entry(p, config)
        entries.append({"user_id": p["user_id"], **entry, "draft": True})
    return entries


def write_answer_key_json(path: str | Path, answer_key: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(answer_key, f, ensure_ascii=False, indent=2)


_CSV_FIELDS = [
    "user_id",
    "draft",
    "acceptable_challenges",
    "acceptable_target_categories",
    "acceptable_mechanics",
    "forbidden_categories",
    "max_reward_rub",
    "relevance_reason",
    "abstain_is_correct",
    "confirmed_by",
    "corrected_challenge",
    "notes",
]


def write_answer_key_csv(path: str | Path, answer_key: list[dict]) -> None:
    """Human-editable CSV template: the drafted columns pre-filled, plus
    empty `confirmed_by`/`corrected_challenge`/`notes` columns for a
    teammate to fill in by hand."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for entry in answer_key:
            row = {
                "user_id": entry["user_id"],
                "draft": entry["draft"],
                "acceptable_challenges": "; ".join(entry["acceptable_challenges"]),
                "acceptable_target_categories": "; ".join(entry["acceptable_target_categories"]),
                "acceptable_mechanics": "; ".join(entry["acceptable_mechanics"]),
                "forbidden_categories": "; ".join(entry["forbidden_categories"]),
                "max_reward_rub": entry["max_reward_rub"],
                "relevance_reason": entry["relevance_reason"],
                "abstain_is_correct": entry["abstain_is_correct"],
                "confirmed_by": "",
                "corrected_challenge": "",
                "notes": "",
            }
            writer.writerow(row)
