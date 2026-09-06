from __future__ import annotations

from dataclasses import dataclass
from datetime import date


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
