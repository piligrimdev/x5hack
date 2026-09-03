from synth.config import load_config
from synth.simulation_truth import generate_user_behavior

_config = load_config("config/synth_schema.yaml")
_segment = _config.segments[0]


def test_generate_user_behavior_is_deterministic():
    kw1, t1 = generate_user_behavior("u1", _config, _segment, 2, ["овощи"], seed=1)
    kw2, t2 = generate_user_behavior("u1", _config, _segment, 2, ["овощи"], seed=1)
    assert kw1 == kw2
    assert t1 == t2


def test_generate_user_behavior_respects_frequency_override():
    kw, truth = generate_user_behavior(
        "u1", _config, _segment, 2, None, seed=1, frequency_multiplier_override=2.5
    )
    assert kw["frequency_multiplier"] == 2.5
    assert truth.baseline_visits_28d > 20


def test_generate_user_behavior_respects_promo_override_and_stays_consistent():
    kw, truth = generate_user_behavior(
        "u1", _config, _segment, 2, None, seed=1, promo_affinity_override=0.5
    )
    assert kw["promo_affinity"] == 0.5
    assert 0.0 <= truth.promo_sensitivity <= 1.0


def test_category_affinity_covers_every_category():
    _, truth = generate_user_behavior("u1", _config, _segment, 2, ["овощи"], seed=1)
    category_names = {c.name for c in _config.categories}
    assert set(truth.category_affinity.keys()) == category_names


def test_habitual_categories_get_higher_affinity():
    _, truth = generate_user_behavior("u1", _config, _segment, 2, ["овощи"], seed=1)
    assert truth.category_affinity["овощи"] > truth.category_affinity["алкоголь"]
