import pytest

from synth.survival import fit_km_curve


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


from datetime import date

from synth.survival import fit_population_curves, purchase_dates_from_profiles


def test_fit_population_curves_builds_intervals_and_censoring_per_category():
    # u1: молоко on Jan1, Jan11 (interval 10, uncensored), then censored
    #     Jan11 -> as_of Jan21 (interval 10, censored).
    # u2: молоко on Jan5 only -> censored Jan5 -> as_of Jan21 (interval 16).
    purchase_dates_by_user = {
        "u1": {"молоко": [date(2026, 1, 1), date(2026, 1, 11)]},
        "u2": {"молоко": [date(2026, 1, 5)]},
    }
    curves = fit_population_curves(purchase_dates_by_user, as_of=date(2026, 1, 21))

    assert "молоко" in curves
    # One uncensored event at t=10 (u1's first interval), at risk n=3
    # (u1's two intervals + u2's one), so S(10) = 1 - 1/3.
    assert curves["молоко"].survival_at(10) == pytest.approx(2 / 3)


def test_fit_population_curves_single_purchase_gives_only_a_censored_observation():
    purchase_dates_by_user = {"u1": {"овощи": [date(2026, 1, 1)]}}
    curves = fit_population_curves(purchase_dates_by_user, as_of=date(2026, 1, 8))
    # A single censored observation produces no event -> flat curve at 1.0.
    assert curves["овощи"].times == ()
    assert curves["овощи"].survival_at(100) == 1.0


def test_fit_population_curves_skips_categories_with_no_observations():
    assert fit_population_curves({}, as_of=date(2026, 1, 1)) == {}


def test_purchase_dates_from_profiles_groups_dates_by_user_and_category():
    profiles = [
        {
            "user_id": "u1",
            "receipts": [
                {"purchase_date": "2026-01-01", "lines": [{"category": "молоко"}, {"category": "хлеб"}]},
                {"purchase_date": "2026-01-01", "lines": [{"category": "молоко"}]},  # same-day dup
                {"purchase_date": "2026-01-11", "lines": [{"category": "молоко"}]},
            ],
        },
    ]
    result = purchase_dates_from_profiles(profiles)
    assert result["u1"]["молоко"] == [date(2026, 1, 1), date(2026, 1, 11)]
    assert result["u1"]["хлеб"] == [date(2026, 1, 1)]
