import json

from synth.config import load_config
from synth.population import population, write_population_jsonl, write_simulation_truth_jsonl

_config = load_config("config/synth_schema.yaml")


def test_population_generates_n_users_with_receipts():
    users, truth = population(n=25, seed=100, config=_config)
    assert len(users) == 25
    assert len(truth) == 25
    assert len({u["user_id"] for u in users}) == 25
    assert all(u["receipts"] for u in users)
    assert all("habitual_categories" in u for u in users)


def test_population_is_deterministic_for_same_seed():
    a, ta = population(n=10, seed=3, config=_config)
    b, tb = population(n=10, seed=3, config=_config)
    assert a == b
    assert ta == tb


def test_write_population_jsonl_writes_one_json_object_per_line(tmp_path):
    users, _ = population(n=5, seed=1, config=_config)
    out_path = tmp_path / "population.jsonl"
    write_population_jsonl(out_path, users)

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5
    parsed = [json.loads(l) for l in lines]
    assert {p["user_id"] for p in parsed} == {u["user_id"] for u in users}


def test_write_population_jsonl_supports_gzip_output(tmp_path):
    import gzip

    users, _ = population(n=5, seed=1, config=_config)
    out_path = tmp_path / "population.jsonl.gz"
    write_population_jsonl(out_path, users)

    with gzip.open(out_path, "rt", encoding="utf-8") as f:
        lines = f.read().strip().split("\n")
    assert len(lines) == 5
    parsed = [json.loads(l) for l in lines]
    assert {p["user_id"] for p in parsed} == {u["user_id"] for u in users}


def test_write_simulation_truth_jsonl_round_trips(tmp_path):
    _, truth = population(n=5, seed=1, config=_config)
    out_path = tmp_path / "truth.jsonl"
    write_simulation_truth_jsonl(out_path, truth)

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    parsed = [json.loads(l) for l in lines]
    assert {p["user_id"] for p in parsed} == {t["user_id"] for t in truth}
    assert "baseline_visits_28d" in parsed[0]
    assert "category_affinity" in parsed[0]


_HIDDEN_FIELDS = {
    "baseline_visits_28d",
    "frequency_headroom",
    "promo_sensitivity",
    "challenge_sensitivity",
    "reward_sensitivity",
    "app_open_probability",
    "fatigue_sensitivity",
    "category_affinity",
    "repurchase_intervals",
    "response_noise_seed",
}


def test_population_output_has_no_hidden_simulation_truth_fields():
    users, _ = population(n=10, seed=1, config=_config)
    for u in users:
        assert not (_HIDDEN_FIELDS & u.keys())


def test_population_users_have_chain_and_segment():
    users, _ = population(n=50, seed=1, config=_config)

    chain_names = {c.name for c in _config.chains}
    segment_names = {s.name for s in _config.segments}

    assert all("chain" in u and "segment" in u for u in users)
    assert all(u["chain"] in chain_names for u in users)
    assert all(u["segment"] in segment_names for u in users)


def test_population_segment_distribution_matches_chain_weights():
    users, _ = population(n=2500, seed=2, config=_config)

    pyaterochka_users = [u for u in users if u["chain"] == "Пятёрочка"]
    pyaterochka_young_share = (
        sum(1 for u in pyaterochka_users if u["segment"] == "Молодёжь") / len(pyaterochka_users)
    )
    assert 0.28 < pyaterochka_young_share < 0.46


def test_population_visit_frequency_differs_by_segment():
    users, _ = population(n=1500, seed=3, config=_config)

    def mean_receipts(segment: str) -> float:
        counts = [len(u["receipts"]) for u in users if u["segment"] == segment]
        return sum(counts) / len(counts)

    starshie_mean = mean_receipts("Старшие")
    molodezh_mean = mean_receipts("Молодёжь")
    assert starshie_mean > molodezh_mean


def test_population_price_multiplier_matches_catalog_formula_for_pyaterochka():
    """Regression check: at Пятёрочка (chain multiplier 1.0), mean paid
    receipt total should be in the right ballpark of the configured
    avg_receipt_total_rub — a loose statistical sanity check, not exact
    arithmetic (frequency/basket-size now vary per segment/user too)."""
    users, _ = population(n=1500, seed=54321, config=_config)
    pyaterochka_totals = [
        r["total_rub"] for u in users if u["chain"] == "Пятёрочка" for r in u["receipts"]
    ]
    assert pyaterochka_totals
    mean_total = sum(pyaterochka_totals) / len(pyaterochka_totals)
    assert 200 < mean_total < 2000  # broad sanity band, not a tight calibration lock


def test_population_gross_margin_never_negative():
    users, _ = population(n=200, seed=5, config=_config)
    for u in users:
        for r in u["receipts"]:
            assert r["gross_margin_rub"] >= -0.01
            for l in r["lines"]:
                assert l["gross_margin_rub"] >= -0.01
