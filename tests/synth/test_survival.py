import pytest

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
