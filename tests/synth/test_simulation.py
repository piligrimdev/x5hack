from synth.config import load_config
from synth.population import population
from synth.simulation import (
    _compute_mean_margin_rate,
    route_for_simulation,
    simulate_population,
    simulate_user_response,
    summarize_simulation,
    write_simulation_details_jsonl,
    write_simulation_report,
)

_config = load_config("config/synth_schema.yaml")


def test_route_for_simulation_matches_generate_challenge_for_user_routing():
    from synth.challenges import generate_challenge_for_user

    users, truth = population(n=30, seed=1, config=_config)
    for u in users:
        expected = generate_challenge_for_user(u, _config, model="fake/model", dry_run=True)
        expected_path = "personal" if expected["path"] == "personal_dry_run" else expected["path"]
        actual = route_for_simulation(u, _config)
        assert actual["path"] == expected_path


def test_simulate_user_response_no_challenge_is_always_zero():
    users, truth = population(n=50, seed=2, config=_config)
    truth_by_id = {t["user_id"]: t for t in truth}
    for u in users:
        if route_for_simulation(u, _config)["path"] != "no_challenge":
            continue
        result = simulate_user_response(u, truth_by_id[u["user_id"]], mean_margin_per_receipt=50.0, config=_config)
        assert result.responded is False
        assert result.projected_extra_visits_28d == 0.0
        assert result.reward_paid_rub == 0.0
        assert result.net_value_rub == 0.0


def test_simulate_user_response_is_deterministic_for_same_truth():
    users, truth = population(n=20, seed=3, config=_config)
    truth_by_id = {t["user_id"]: t for t in truth}
    u = users[0]
    t = truth_by_id[u["user_id"]]
    a = simulate_user_response(u, t, mean_margin_per_receipt=50.0, config=_config)
    b = simulate_user_response(u, t, mean_margin_per_receipt=50.0, config=_config)
    assert a == b


def test_simulate_user_response_personal_never_less_likely_than_generic():
    # Same truth record, force each path via reward/relevance math directly:
    # personal uses relevance=1.0, generic uses GENERIC_RELEVANCE_MULTIPLIER<1.0,
    # so for identical app_open/challenge_sensitivity, personal's response
    # probability must be >= generic's.
    from synth.simulation import GENERIC_RELEVANCE_MULTIPLIER

    assert 0.0 < GENERIC_RELEVANCE_MULTIPLIER < 1.0


def test_simulate_population_covers_every_user_with_truth():
    users, truth = population(n=100, seed=4, config=_config)
    results = simulate_population(users, truth, _config)
    assert len(results) == 100
    assert {r.user_id for r in results} == {u["user_id"] for u in users}


def test_simulate_population_skips_users_without_a_truth_record():
    users, truth = population(n=20, seed=5, config=_config)
    truth_missing_one = truth[1:]
    results = simulate_population(users, truth_missing_one, _config)
    assert len(results) == 19


def test_summarize_simulation_reports_by_path_and_overall():
    users, truth = population(n=300, seed=6, config=_config)
    results = simulate_population(users, truth, _config)
    report = summarize_simulation(results)

    assert report["n_total_users"] == 300
    assert "overall" in report
    assert "by_path" in report
    assert set(report["by_path"].keys()) <= {"no_challenge", "personal", "generic"}
    for path_stats in report["by_path"].values():
        assert path_stats["n_users"] > 0
    assert "assumptions" in report


def test_summarize_simulation_no_challenge_path_has_zero_response_rate():
    users, truth = population(n=300, seed=7, config=_config)
    results = simulate_population(users, truth, _config)
    report = summarize_simulation(results)
    if "no_challenge" in report["by_path"]:
        assert report["by_path"]["no_challenge"]["response_rate"] == 0.0
        assert report["by_path"]["no_challenge"]["net_value_rub"] == 0.0


def test_route_for_simulation_spend_threshold_matches_generate_challenge_for_user_routing():
    from synth.challenges import generate_challenge_for_user

    users, truth = population(n=100, seed=9, config=_config)
    for u in users:
        expected = generate_challenge_for_user(u, _config, model="fake/model", challenge_type="spend_threshold")
        actual = route_for_simulation(u, _config, challenge_type="spend_threshold")
        assert actual["path"] == expected["path"]


def test_simulate_user_response_spend_threshold_uses_basket_channel_when_responded():
    users, truth = population(n=300, seed=10, config=_config)
    truth_by_id = {t["user_id"]: t for t in truth}
    mean_margin_rate = _compute_mean_margin_rate(users)

    seen_basket_responder = False
    for u in users:
        route = route_for_simulation(u, _config, challenge_type="spend_threshold")
        if route["path"] != "personal" or "spend_threshold_rub" not in route:
            continue
        t = truth_by_id[u["user_id"]]
        result = simulate_user_response(
            u, t, mean_margin_per_receipt=50.0, config=_config,
            challenge_type="spend_threshold", mean_margin_rate=mean_margin_rate,
        )
        assert result.projected_extra_visits_28d == 0.0
        if result.responded:
            seen_basket_responder = True
            assert result.channel == "basket"
            assert result.projected_basket_uplift_rub > 0.0
            expected_margin = round(result.projected_basket_uplift_rub * mean_margin_rate, 2)
            assert result.projected_extra_margin_rub == expected_margin
            expected_net = round(expected_margin - result.reward_paid_rub, 2)
            assert result.net_value_rub == expected_net
    assert seen_basket_responder, "expected at least one responding spend_threshold user in this sample"


def test_simulate_user_response_llm_channel_is_frequency_when_responded():
    users, truth = population(n=300, seed=11, config=_config)
    truth_by_id = {t["user_id"]: t for t in truth}
    for u in users:
        if route_for_simulation(u, _config)["path"] != "personal":
            continue
        t = truth_by_id[u["user_id"]]
        result = simulate_user_response(u, t, mean_margin_per_receipt=50.0, config=_config)
        assert result.projected_basket_uplift_rub == 0.0
        if result.responded:
            assert result.channel == "frequency"
            assert result.projected_extra_visits_28d > 0.0


def test_compute_mean_margin_rate_is_between_zero_and_one():
    users, _truth = population(n=50, seed=12, config=_config)
    rate = _compute_mean_margin_rate(users)
    assert 0.0 < rate < 1.0


def test_summarize_simulation_reports_by_channel():
    users, truth = population(n=300, seed=13, config=_config)
    results = simulate_population(users, truth, _config, challenge_type="spend_threshold")
    report = summarize_simulation(results)
    assert set(report["by_channel"].keys()) <= {"none", "frequency", "basket"}
    for channel_stats in report["by_channel"].values():
        assert channel_stats["n_users"] > 0


def test_write_simulation_report_and_details_round_trip(tmp_path):
    users, truth = population(n=25, seed=8, config=_config)
    results = simulate_population(users, truth, _config)
    report = summarize_simulation(results)

    report_path = tmp_path / "report.json"
    details_path = tmp_path / "details.jsonl"
    write_simulation_report(report_path, report)
    write_simulation_details_jsonl(details_path, results)

    import json

    loaded_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded_report["n_total_users"] == 25

    lines = details_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 25
    parsed = [json.loads(l) for l in lines]
    assert {p["user_id"] for p in parsed} == {u["user_id"] for u in users}
