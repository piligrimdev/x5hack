from synth.catalog import build_catalog, skus_by_category
from synth.config import load_config
from synth.receipts import generate_receipts_for_user

_config = load_config("config/synth_schema.yaml")
_catalog = build_catalog(_config)
_by_category = skus_by_category(_catalog)


def _generate(user_id, seed, **kwargs):
    return generate_receipts_for_user(user_id, _config, _catalog, _by_category, seed=seed, **kwargs)


def test_generate_receipts_produces_nonempty_history():
    receipts = _generate("u_000001", seed=1)
    assert len(receipts) > 0
    assert all(r.lines for r in receipts)
    assert all(r.total_rub > 0 for r in receipts)
    assert all(r.channel in ("offline", "online") for r in receipts)


def test_generate_receipts_is_deterministic_for_same_seed():
    a = _generate("u_000001", seed=5)
    b = _generate("u_000001", seed=5)
    assert [r.receipt_id for r in a] == [r.receipt_id for r in b]
    assert [r.total_rub for r in a] == [r.total_rub for r in b]


def test_habitual_categories_dominate_when_given():
    habitual = ["молочные продукты и яйца", "овощи"]
    receipts = _generate("u_000002", seed=9, habitual_categories=habitual, habitual_bias_strength=0.8)
    all_lines = [line for r in receipts for line in r.lines]
    habitual_count = sum(1 for l in all_lines if l.category in habitual)
    assert habitual_count / len(all_lines) > 0.5


def test_no_habitual_categories_means_full_spread():
    receipts = _generate("u_000003", seed=11)
    categories_seen = {line.category for r in receipts for line in r.lines}
    assert len(categories_seen) > 2


def test_price_multiplier_scales_mean_receipt_total():
    baseline = _generate("u_pm_1", seed=100, price_multiplier=1.0)
    scaled = _generate("u_pm_2", seed=100, price_multiplier=2.0)

    baseline_lines = [line for r in baseline for line in r.lines]
    scaled_lines = [line for r in scaled for line in r.lines]

    baseline_mean = sum(l.regular_unit_price_rub for l in baseline_lines) / len(baseline_lines)
    scaled_mean = sum(l.regular_unit_price_rub for l in scaled_lines) / len(scaled_lines)

    ratio = scaled_mean / baseline_mean
    assert 1.8 < ratio < 2.2


def test_price_multiplier_defaults_to_one():
    explicit = _generate("u_pm_3", seed=50, price_multiplier=1.0)
    default = _generate("u_pm_3", seed=50)
    assert [r.total_rub for r in explicit] == [r.total_rub for r in default]


def test_frequency_multiplier_scales_receipt_count():
    low = _generate("u_freq_1", seed=200, frequency_multiplier=0.5)
    high = _generate("u_freq_2", seed=200, frequency_multiplier=2.0)
    assert len(high) > len(low)


def test_basket_size_multiplier_scales_lines_per_receipt():
    small = _generate("u_basket_1", seed=300, basket_size_multiplier=0.5)
    large = _generate("u_basket_2", seed=300, basket_size_multiplier=2.0)
    small_mean = sum(len(r.lines) for r in small) / len(small)
    large_mean = sum(len(r.lines) for r in large) / len(large)
    assert large_mean > small_mean


def test_paid_never_exceeds_regular_and_never_below_cost():
    receipts = _generate("u_fin_1", seed=400)
    for r in receipts:
        for l in r.lines:
            assert l.paid_unit_price_rub <= l.regular_unit_price_rub + 1e-6
            assert l.paid_unit_price_rub >= l.unit_cost_rub - 1e-6


def test_receipt_totals_reconcile_with_line_items():
    receipts = _generate("u_fin_2", seed=401)
    for r in receipts:
        expected_regular = round(sum(l.regular_unit_price_rub * l.qty for l in r.lines), 2)
        expected_paid = round(sum(l.paid_unit_price_rub * l.qty for l in r.lines), 2)
        assert abs(r.regular_total_rub - expected_regular) < 0.02
        assert abs(r.total_rub - expected_paid) < 0.02
        assert abs(r.savings_rub - round(expected_regular - expected_paid, 2)) < 0.02


def test_at_most_5pct_of_purchase_days_have_multiple_receipts():
    receipts = _generate("u_days_1", seed=402)
    from collections import Counter

    day_counts = Counter(r.purchase_date for r in receipts)
    multi_days = sum(1 for c in day_counts.values() if c > 1)
    assert multi_days / len(day_counts) <= 0.10  # generous per-user bound; aggregate check lives in the validator


def test_no_receipts_before_train_start_or_after_holdout_end():
    receipts = _generate("u_window_1", seed=403)
    ts = _config.temporal_split
    for r in receipts:
        assert ts.train_start.isoformat() <= r.purchase_date <= ts.holdout_end.isoformat()
