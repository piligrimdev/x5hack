from synth.catalog import build_catalog, skus_by_category
from synth.config import load_config
from synth.features import compute_observable_habitual_categories
from synth.receipts import generate_receipts_for_user

_config = load_config("config/synth_schema.yaml")
_catalog = build_catalog(_config)
_by_category = skus_by_category(_catalog)


def test_observable_habitual_categories_ignores_holdout_receipts():
    receipts = generate_receipts_for_user(
        "u1", _config, _catalog, _by_category, seed=1,
        habitual_categories=["овощи", "фрукты"], habitual_bias_strength=0.9,
    )
    train_end = _config.temporal_split.train_end.isoformat()
    train_only = [r for r in receipts if r.purchase_date <= train_end]
    all_receipts_result = compute_observable_habitual_categories(receipts, _config)

    # Manually recompute using only train receipts and confirm it's the
    # same result the function itself produces (i.e. it isn't secretly
    # using holdout receipts even though they're present in the input list)
    from collections import Counter

    counts = Counter(l.category for r in train_only for l in r.lines)
    expected = [c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
    assert all_receipts_result == expected


def test_observable_habitual_categories_returns_at_most_top_k():
    receipts = generate_receipts_for_user("u2", _config, _catalog, _by_category, seed=2)
    result = compute_observable_habitual_categories(receipts, _config, top_k=3)
    assert len(result) <= 3
