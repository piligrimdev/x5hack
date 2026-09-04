from __future__ import annotations

import random
from dataclasses import dataclass

from synth.config import SegmentConfig, SynthConfig


@dataclass
class SimulationTruth:
    """Hidden generative parameters for one user — NEVER written to the
    observable population/blind-reference files. A future recommender must
    not see these; they exist for whoever builds the H1/H4 simulation and
    for the reference-profile answer key.
    """

    user_id: str
    baseline_visits_28d: float
    frequency_headroom: float
    promo_sensitivity: float
    challenge_sensitivity: float
    reward_sensitivity: float
    basket_uplift_sensitivity: float
    novelty_receptiveness: float
    app_open_probability: float
    fatigue_sensitivity: float
    category_affinity: dict[str, float]
    repurchase_intervals: dict[str, float]
    forbidden_categories: list[str]
    response_noise_seed: int


def generate_user_behavior(
    user_id: str,
    config: SynthConfig,
    segment_behavior: SegmentConfig,
    family_size: int,
    habitual_categories: list[str] | None,
    seed: int,
    promo_affinity_override: float | None = None,
    frequency_multiplier_override: float | None = None,
    frequency_headroom_override: float | None = None,
) -> tuple[dict, SimulationTruth]:
    """Draw one user's hidden behavioral state, and derive the kwargs
    `generate_receipts_for_user` needs to actually produce matching
    receipts. Both outputs come from the same draws, so
    `simulation_truth.baseline_visits_28d` genuinely describes the rate
    used to generate that user's receipts, not an independent guess at it.

    `*_override` let a caller (reference_profiles.py's archetypes) pin a
    specific promo_affinity/frequency_multiplier instead of the generic
    per-user draw, while keeping the corresponding hidden-truth field
    internally consistent with what was actually used.
    """
    rng = random.Random(seed)
    cal = config.calibration
    all_categories = [c.name for c in config.categories]

    personal_frequency_factor = rng.lognormvariate(0, 0.3)
    frequency_multiplier = (
        frequency_multiplier_override
        if frequency_multiplier_override is not None
        else segment_behavior.visit_frequency_multiplier * personal_frequency_factor
    )
    base_rate_28d = cal.purchases_per_month_mean * (28 / 30)
    baseline_visits_28d = round(min(max(base_rate_28d * frequency_multiplier, 2.0), 40.0), 3)

    family_factor = 0.7 + 0.15 * family_size
    basket_size_multiplier = segment_behavior.basket_size_multiplier * family_factor

    frequency_headroom = (
        round(frequency_headroom_override, 3)
        if frequency_headroom_override is not None
        else round(rng.uniform(0.05, 0.40), 3)
    )
    promo_sensitivity_raw = rng.betavariate(2, 3)
    challenge_sensitivity = round(rng.betavariate(2, 4), 3)
    reward_sensitivity = round(rng.betavariate(2, 3), 3)
    # How consistently this user actually stretches a trip's spend to clear
    # a spend-threshold challenge's target, given they respond at all —
    # distinct from `reward_sensitivity` (used by the frequency-uplift
    # channel for personal/generic offers): this drives the basket-uplift
    # channel instead (see synth/simulation.py's spend_threshold handling).
    basket_uplift_sensitivity = round(rng.betavariate(2, 3), 3)
    # How willing this user is to try a category they don't normally buy,
    # given a category_expansion challenge — deliberately skewed low
    # (betavariate(2,5), mean ~0.29): trying something unfamiliar is harder
    # than repeating a habit, unlike challenge_sensitivity (general
    # receptiveness to any challenge) or basket_uplift_sensitivity
    # (stretching spend within an already-familiar pattern). Drives the
    # "expansion" channel in synth/simulation.py.
    novelty_receptiveness = round(rng.betavariate(2, 5), 3)
    app_open_probability = round(rng.uniform(0.10, 0.90), 3)
    fatigue_sensitivity = round(rng.betavariate(2, 4), 3)

    if promo_affinity_override is not None:
        promo_affinity = round(promo_affinity_override, 3)
        promo_sensitivity = round(min(max((promo_affinity - 0.08) / 0.27, 0.0), 1.0), 3)
    else:
        promo_sensitivity = round(promo_sensitivity_raw, 3)
        promo_affinity = round(0.08 + 0.27 * promo_sensitivity, 3)

    category_affinity: dict[str, float] = {}
    for cat in all_categories:
        if habitual_categories and cat in habitual_categories:
            category_affinity[cat] = round(rng.uniform(0.5, 1.0), 3)
        else:
            category_affinity[cat] = round(rng.uniform(0.0, 0.3), 3)

    source_categories = habitual_categories if habitual_categories else rng.sample(all_categories, k=3)
    repurchase_intervals = {cat: round(rng.uniform(3, 21), 1) for cat in source_categories}

    truth = SimulationTruth(
        user_id=user_id,
        baseline_visits_28d=baseline_visits_28d,
        frequency_headroom=frequency_headroom,
        promo_sensitivity=promo_sensitivity,
        challenge_sensitivity=challenge_sensitivity,
        reward_sensitivity=reward_sensitivity,
        basket_uplift_sensitivity=basket_uplift_sensitivity,
        novelty_receptiveness=novelty_receptiveness,
        app_open_probability=app_open_probability,
        fatigue_sensitivity=fatigue_sensitivity,
        category_affinity=category_affinity,
        repurchase_intervals=repurchase_intervals,
        forbidden_categories=list(config.forbidden_categories),
        response_noise_seed=seed * 7 + 3,
    )
    receipt_kwargs = {
        "frequency_multiplier": frequency_multiplier,
        "basket_size_multiplier": basket_size_multiplier,
        "promo_affinity": promo_affinity,
    }
    return receipt_kwargs, truth
