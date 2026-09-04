from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from synth.challenges import (
    build_category_expansion_challenge,
    build_spend_threshold_challenge,
    compute_frequency_saturation,
    compute_receptiveness,
    estimate_max_reward_rub,
    pick_generic_challenge,
)
from synth.config import SynthConfig

# --- Unvalidated modeling assumptions, flagged explicitly (nothing here is
# calibrated against real X5 data — there is none available per
# CONTEXT_PACK.md §3/§4) ---
#
# How much less effective a generic partner offer is than a relevant
# personal challenge, in terms of response probability. Directionally
# matches this project's H2 hypothesis (personalized > generic engagement)
# but the exact number is an assumption, not a measurement.
GENERIC_RELEVANCE_MULTIPLIER = 0.4

# Of a responding user's available `frequency_headroom`, what fraction
# actually gets captured as extra visits, as a function of their
# (hidden) `reward_sensitivity`. 0.5 floor + up to 0.5 more from reward
# sensitivity — i.e. even a reward-insensitive responder captures SOME
# headroom just from the relevance/timing nudge, not zero.
HEADROOM_CAPTURE_BASE = 0.5
HEADROOM_CAPTURE_REWARD_WEIGHT = 0.5

# How much less likely a response is for a category_expansion challenge than
# for a fully-relevant personal one, purely from unfamiliarity — lower than
# GENERIC_RELEVANCE_MULTIPLIER, because a generic offer is merely
# non-personalized while an expansion offer actively targets a category the
# user has shown no interest in. Multiplies together with the user's own
# `novelty_receptiveness` (not just `challenge_sensitivity`, unlike the
# other two channels) — see `simulate_user_response`.
EXPANSION_RELEVANCE_MULTIPLIER = 0.25


@dataclass
class UserSimulationResult:
    user_id: str
    path: str
    channel: str
    response_probability: float
    responded: bool
    baseline_visits_28d: float
    projected_extra_visits_28d: float
    projected_basket_uplift_rub: float
    projected_expansion_trials_28d: float
    reward_paid_rub: float
    projected_extra_margin_rub: float
    net_value_rub: float


def route_for_simulation(profile: dict, config: SynthConfig, challenge_type: str = "llm") -> dict:
    """The same no_challenge/personal/generic routing decision one slot of
    `generate_challenge_for_user` makes (that function now builds all three
    slots — `llm`, `spend_threshold`, `category_expansion` — per user;
    `route_for_simulation` still evaluates a single channel at a time, via
    `challenge_type`), WITHOUT calling any LLM — routing itself never
    depended on the model, only the creative TEXT of a "personal" challenge
    does (and the simulation doesn't need that text, only which path a user
    landed on and what reward/mechanic it implies). Lets the simulation run
    over the full population without an API call per user.

    `challenge_type="spend_threshold"` routes a receptive user through
    `build_spend_threshold_challenge` instead of the flat LLM reward
    ceiling. `challenge_type="category_expansion"` routes through
    `build_category_expansion_challenge` instead. Both fall back to
    generic the same way `generate_challenge_for_user`'s matching slot does
    when there isn't enough train-period history to build the deterministic
    offer.
    """
    saturated, _ = compute_frequency_saturation(profile, config)
    if saturated:
        return {"path": "no_challenge", "reward_rub": 0.0, "challenge_type": challenge_type}

    receptive, _ = compute_receptiveness(profile, config)
    if not receptive:
        offer = pick_generic_challenge(profile["user_id"], config)
        return {"path": "generic", "reward_rub": offer["reward_rub"], "challenge_type": challenge_type}

    if challenge_type == "spend_threshold":
        challenge = build_spend_threshold_challenge(profile, config)
        if challenge is None:
            offer = pick_generic_challenge(profile["user_id"], config)
            return {"path": "generic_fallback", "reward_rub": offer["reward_rub"], "challenge_type": challenge_type}
        return {
            "path": "personal",
            "reward_rub": challenge["reward_rub"],
            "challenge_type": challenge_type,
            "spend_threshold_rub": challenge["spend_threshold_rub"],
            "baseline_mean_receipt_rub": challenge["baseline_mean_receipt_rub"],
        }

    if challenge_type == "category_expansion":
        challenge = build_category_expansion_challenge(profile, config)
        if challenge is None:
            offer = pick_generic_challenge(profile["user_id"], config)
            return {"path": "generic_fallback", "reward_rub": offer["reward_rub"], "challenge_type": challenge_type}
        return {
            "path": "personal",
            "reward_rub": challenge["reward_rub"],
            "challenge_type": challenge_type,
            "novel_category": challenge["novel_category"],
        }

    return {"path": "personal", "reward_rub": estimate_max_reward_rub(profile), "challenge_type": challenge_type}


def _compute_mean_margin_per_receipt(users: list[dict]) -> float:
    """Mean margin of a whole RECEIPT (a visit — every line item in that
    basket), not of a single line. `extra_visits_28d` in
    `simulate_user_response` represents extra VISITS, so it must be
    multiplied by what a whole visit's basket is worth, not by one item's
    margin — that mismatch was a real bug caught by the simulation's own
    output looking economically implausible on the first run (average
    reward exceeding average margin per responder by nearly the ratio of
    this project's own mean basket size)."""
    margins = [r["gross_margin_rub"] for u in users for r in u["receipts"]]
    return sum(margins) / len(margins) if margins else 0.0


def _compute_mean_margin_rate(users: list[dict]) -> float:
    """Blended margin as a fraction of revenue (sum margin / sum total)
    across every receipt in the population — used to convert a basket-size
    INCREASE (extra rubles spent in one trip) into margin, as opposed to
    `_compute_mean_margin_per_receipt`, which values a whole extra VISIT at
    the average basket. The two channels need different conversion factors:
    an extra visit brings a typical whole basket's margin; a bigger basket
    on a trip that would have happened anyway only brings margin on the
    INCREMENTAL spend, at whatever the average margin rate is."""
    total_margin = sum(r["gross_margin_rub"] for u in users for r in u["receipts"])
    total_revenue = sum(r["total_rub"] for u in users for r in u["receipts"])
    return total_margin / total_revenue if total_revenue else 0.0


def _zero_result(user_id: str, path: str, baseline: float) -> UserSimulationResult:
    return UserSimulationResult(
        user_id=user_id, path=path, channel="none", response_probability=0.0, responded=False,
        baseline_visits_28d=baseline, projected_extra_visits_28d=0.0, projected_basket_uplift_rub=0.0,
        projected_expansion_trials_28d=0.0,
        reward_paid_rub=0.0, projected_extra_margin_rub=0.0, net_value_rub=0.0,
    )


def _category_margin_estimate(config: SynthConfig, category: str) -> float:
    """Expected margin on ONE unit of `category`'s configured reference
    price — used for the expansion channel, which has no per-user observed
    price for a category the user doesn't buy (unlike the frequency/basket
    channels, which value margin off the user's own receipts or the
    population's own realized rates)."""
    for e in config.category_economics:
        if e.category == category:
            return e.base_price_rub * e.margin_pct
    return 0.0


def simulate_user_response(
    profile: dict,
    truth: dict,
    mean_margin_per_receipt: float,
    config: SynthConfig,
    challenge_type: str = "llm",
    mean_margin_rate: float = 0.0,
) -> UserSimulationResult:
    """Simulate whether ONE user responds to whatever challenge
    `route_for_simulation` would give them, and the resulting economics.

    This is the one place in the whole project where `simulation_truth`'s
    hidden fields (`challenge_sensitivity`, `reward_sensitivity`,
    `basket_uplift_sensitivity`, `app_open_probability`,
    `frequency_headroom`, `response_noise_seed`) are legitimately used —
    this IS the H1/H4 simulation those fields were generated for. Using
    them inside `synth/challenges.py`'s routing logic would be leakage;
    using them here, where the whole point is "what would happen if we
    gave this synthetic user a challenge," is exactly the intended
    purpose.

    Three distinct, non-overlapping economic channels, matched to the
    actual mechanic a responding user got:
    - **frequency** (personal-LLM or generic offers): the challenge is
      assumed to pull the user in for an EXTRA visit — valued at the
      population's average whole-basket margin (`mean_margin_per_receipt`).
      `response_probability = app_open_probability x challenge_sensitivity
      x relevance` (relevance = 1.0 personal, `GENERIC_RELEVANCE_MULTIPLIER`
      generic — see the module-level comment).
    - **basket** (spend_threshold offers only): the challenge doesn't add a
      visit, it stretches an EXISTING trip's spend up toward
      `spend_threshold_rub`. Extra margin only accrues on the incremental
      spend (`spend_threshold_rub - baseline_mean_receipt_rub`), converted
      via the blended margin RATE (`mean_margin_rate`), across the share of
      the user's normal trips they actually stretch on
      (`basket_uplift_sensitivity`) — a different hidden field from
      `reward_sensitivity`, which only governs the frequency channel.
    - **expansion** (category_expansion offers only): targets a category
      the user essentially never buys, on the premise that a habitual-
      category challenge mostly rewards a purchase that would have
      happened anyway (the "always-buyer" problem in uplift marketing) —
      see `build_category_expansion_challenge`'s docstring. Response
      probability additionally requires `novelty_receptiveness` (most
      users resist trying something unfamiliar even if generally
      challenge-receptive), and a response is modeled as exactly ONE
      trial purchase within the 28-day window — not a repeating pattern,
      since there is no basis to assume a single nudge creates an ongoing
      habit. Because it's a genuinely new purchase, none of it is
      "would have happened anyway" — the full per-unit margin counts, no
      headroom/capture-fraction discount like the other two channels.
    """
    route = route_for_simulation(profile, config, challenge_type)
    path = route["path"]
    baseline = truth["baseline_visits_28d"]

    if path == "no_challenge":
        return _zero_result(profile["user_id"], path, baseline)

    is_basket_channel = "spend_threshold_rub" in route
    is_expansion_channel = "novel_category" in route

    if is_expansion_channel:
        relevance = EXPANSION_RELEVANCE_MULTIPLIER * truth["novelty_receptiveness"]
    else:
        relevance = 1.0 if path == "personal" else GENERIC_RELEVANCE_MULTIPLIER
    response_probability = min(
        1.0, max(0.0, truth["app_open_probability"] * truth["challenge_sensitivity"] * relevance)
    )

    rng = random.Random(truth["response_noise_seed"])
    responded = rng.random() < response_probability

    if not responded:
        result = _zero_result(profile["user_id"], path, baseline)
        result.response_probability = round(response_probability, 4)
        return result

    reward_paid_rub = route["reward_rub"]  # only paid out on an actual (simulated) response

    if is_expansion_channel:
        margin_per_trial = _category_margin_estimate(config, route["novel_category"])
        extra_margin_rub = round(margin_per_trial, 2)
        net_value_rub = round(extra_margin_rub - reward_paid_rub, 2)
        return UserSimulationResult(
            user_id=profile["user_id"], path=path, channel="expansion",
            response_probability=round(response_probability, 4), responded=True,
            baseline_visits_28d=baseline, projected_extra_visits_28d=0.0,
            projected_basket_uplift_rub=0.0, projected_expansion_trials_28d=1.0,
            reward_paid_rub=round(reward_paid_rub, 2),
            projected_extra_margin_rub=extra_margin_rub,
            net_value_rub=net_value_rub,
        )

    if is_basket_channel:
        uplift_per_trip_rub = max(0.0, route["spend_threshold_rub"] - route["baseline_mean_receipt_rub"])
        uplifted_trips_28d = baseline * truth["basket_uplift_sensitivity"]
        basket_uplift_rub = round(uplifted_trips_28d * uplift_per_trip_rub, 2)
        extra_margin_rub = basket_uplift_rub * mean_margin_rate
        net_value_rub = round(extra_margin_rub - reward_paid_rub, 2)
        return UserSimulationResult(
            user_id=profile["user_id"], path=path, channel="basket",
            response_probability=round(response_probability, 4), responded=True,
            baseline_visits_28d=baseline, projected_extra_visits_28d=0.0,
            projected_basket_uplift_rub=basket_uplift_rub, projected_expansion_trials_28d=0.0,
            reward_paid_rub=round(reward_paid_rub, 2),
            projected_extra_margin_rub=round(extra_margin_rub, 2),
            net_value_rub=net_value_rub,
        )

    capture_fraction = HEADROOM_CAPTURE_BASE + HEADROOM_CAPTURE_REWARD_WEIGHT * truth["reward_sensitivity"]
    extra_visits_28d = truth["frequency_headroom"] * baseline * capture_fraction
    extra_margin_rub = extra_visits_28d * mean_margin_per_receipt
    net_value_rub = round(extra_margin_rub - reward_paid_rub, 2)

    return UserSimulationResult(
        user_id=profile["user_id"], path=path, channel="frequency",
        response_probability=round(response_probability, 4),
        responded=True, baseline_visits_28d=baseline,
        projected_extra_visits_28d=round(extra_visits_28d, 3),
        projected_basket_uplift_rub=0.0, projected_expansion_trials_28d=0.0,
        reward_paid_rub=round(reward_paid_rub, 2),
        projected_extra_margin_rub=round(extra_margin_rub, 2),
        net_value_rub=net_value_rub,
    )


def simulate_population(
    users: list[dict], truth_records: list[dict], config: SynthConfig, challenge_type: str = "llm"
) -> list[UserSimulationResult]:
    truth_by_id = {t["user_id"]: t for t in truth_records}
    mean_margin_per_receipt = _compute_mean_margin_per_receipt(users)
    mean_margin_rate = _compute_mean_margin_rate(users)

    results = []
    for u in users:
        truth = truth_by_id.get(u["user_id"])
        if truth is None:
            continue
        results.append(
            simulate_user_response(u, truth, mean_margin_per_receipt, config, challenge_type, mean_margin_rate)
        )
    return results


def _path_stats(results: list[UserSimulationResult]) -> dict:
    n = len(results)
    if n == 0:
        return {"n_users": 0}
    n_responded = sum(1 for r in results if r.responded)
    mean_baseline = sum(r.baseline_visits_28d for r in results) / n
    mean_extra = sum(r.projected_extra_visits_28d for r in results) / n
    mean_basket_uplift = sum(r.projected_basket_uplift_rub for r in results) / n
    mean_expansion_trials = sum(r.projected_expansion_trials_28d for r in results) / n
    total_extra_margin = sum(r.projected_extra_margin_rub for r in results)
    total_reward = sum(r.reward_paid_rub for r in results)
    return {
        "n_users": n,
        "n_responded": n_responded,
        "response_rate": round(n_responded / n, 4),
        "mean_baseline_visits_28d": round(mean_baseline, 2),
        "mean_extra_visits_28d": round(mean_extra, 3),
        "frequency_uplift_pct": round((mean_extra / mean_baseline * 100), 3) if mean_baseline else 0.0,
        "mean_basket_uplift_rub": round(mean_basket_uplift, 2),
        "mean_expansion_trials_28d": round(mean_expansion_trials, 4),
        "total_extra_margin_rub": round(total_extra_margin, 2),
        "total_reward_paid_rub": round(total_reward, 2),
        "net_value_rub": round(total_extra_margin - total_reward, 2),
    }


def summarize_simulation(results: list[UserSimulationResult]) -> dict:
    by_path: dict[str, list[UserSimulationResult]] = defaultdict(list)
    by_channel: dict[str, list[UserSimulationResult]] = defaultdict(list)
    for r in results:
        by_path[r.path].append(r)
        by_channel[r.channel].append(r)

    return {
        "n_total_users": len(results),
        "overall": _path_stats(results),
        "by_path": {path: _path_stats(rs) for path, rs in by_path.items()},
        "by_channel": {channel: _path_stats(rs) for channel, rs in by_channel.items()},
        "assumptions": {
            "generic_relevance_multiplier": GENERIC_RELEVANCE_MULTIPLIER,
            "expansion_relevance_multiplier": EXPANSION_RELEVANCE_MULTIPLIER,
            "headroom_capture_base": HEADROOM_CAPTURE_BASE,
            "headroom_capture_reward_weight": HEADROOM_CAPTURE_REWARD_WEIGHT,
            "note": (
                "These numbers are unvalidated modeling assumptions, not "
                "measured from real data (none is available — see CONTEXT_PACK.md "
                "§3/§4). The DIRECTION they encode (personal > generic > expansion "
                "for response probability; higher reward_sensitivity captures more "
                "frequency headroom; higher basket_uplift_sensitivity captures more "
                "of a spend-threshold challenge's target; higher novelty_receptiveness "
                "raises expansion response) matches this project's stated hypotheses "
                "(H2) and the standard uplift-marketing incrementality principle; the "
                "exact magnitudes do not come from anywhere and should be treated as "
                "a starting point to sensitivity-test, not a forecast. Three channels "
                "exist: 'frequency' (personal-LLM/generic offers, valued at an extra "
                "visit's average basket margin), 'basket' (spend_threshold offers, "
                "valued at the margin on incremental spend within an existing trip), "
                "and 'expansion' (category_expansion offers, valued at the full "
                "margin of one trial purchase in a category the user doesn't "
                "normally buy — no headroom discount, since by construction it "
                "isn't a purchase that would have happened anyway) — mutually "
                "exclusive per user, selected by which challenge_type routed them."
            ),
        },
    }


def write_simulation_report(path: str | Path, report: dict) -> None:
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def write_simulation_details_jsonl(path: str | Path, results: list[UserSimulationResult]) -> None:
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
