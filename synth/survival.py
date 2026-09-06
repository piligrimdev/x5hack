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
