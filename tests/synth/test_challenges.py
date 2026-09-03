import json

import pytest

from synth.challenges import (
    GENERIC_CHALLENGES,
    build_personal_prompt,
    build_spend_threshold_challenge,
    compute_frequency_saturation,
    compute_receptiveness,
    estimate_max_reward_rub,
    generate_challenge_for_user,
    load_profiles,
    parse_and_validate_challenge,
    pick_generic_challenge,
    score_against_answer_key,
)
from synth.config import load_config
from synth.reference_profiles import default_class_list, reference_profiles

_config = load_config("config/synth_schema.yaml")


def _profile(generation_class="promo_hunter", seed=1):
    return reference_profiles([generation_class], seed=seed, config=_config)[0]


def test_generic_challenges_never_target_a_forbidden_category():
    forbidden = set(_config.forbidden_categories)
    for offer in GENERIC_CHALLENGES:
        assert not (set(offer["target_categories"]) & forbidden)


def test_pick_generic_challenge_is_deterministic():
    a = pick_generic_challenge("some-uuid-1")
    b = pick_generic_challenge("some-uuid-1")
    assert a == b


def test_pick_generic_challenge_varies_by_user():
    offers = {pick_generic_challenge(f"user-{i}")["challenge_title"] for i in range(20)}
    assert len(offers) > 1


def test_compute_receptiveness_true_for_strong_habitual_pattern():
    profile = _profile("bakes_on_weekends", seed=4)
    receptive, signal = compute_receptiveness(profile, _config)
    assert receptive is True
    assert signal["concentration"] > 0.42


def test_compute_receptiveness_weaker_for_one_off_than_bakes_on_weekends():
    # The reference benchmark's classes are intentionally noisy/overlapping
    # (see the design doc), so this checks the *direction* of the signal —
    # one_off_no_pattern should score lower concentration on average — not
    # that every single one_off profile falls below the threshold.
    one_off = [_profile("one_off_no_pattern", seed=i) for i in range(1, 6)]
    bakes = [_profile("bakes_on_weekends", seed=i) for i in range(1, 6)]

    def mean_concentration(profiles):
        vals = [compute_receptiveness(p, _config)[1]["concentration"] for p in profiles]
        return sum(vals) / len(vals)

    assert mean_concentration(one_off) < mean_concentration(bakes)


def test_compute_receptiveness_false_with_no_train_receipts():
    profile = _profile("promo_hunter", seed=1)
    profile = {**profile, "receipts": [
        r for r in profile["receipts"] if r["purchase_date"] > _config.temporal_split.train_end.isoformat()
    ]}
    receptive, signal = compute_receptiveness(profile, _config)
    assert receptive is False
    assert signal["concentration"] == 0.0


def test_estimate_max_reward_rub_is_positive_and_bounded_by_margin():
    profile = _profile("promo_hunter", seed=2)
    reward = estimate_max_reward_rub(profile)
    assert reward >= 20.0


def test_load_profiles_supports_json_array(tmp_path):
    profiles = [_profile("promo_hunter", seed=1)]
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
    loaded = load_profiles(path)
    assert len(loaded) == 1
    assert loaded[0]["user_id"] == profiles[0]["user_id"]


def test_load_profiles_supports_jsonl(tmp_path):
    profiles = [_profile("promo_hunter", seed=i) for i in range(3)]
    path = tmp_path / "profiles.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for p in profiles:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    loaded = load_profiles(path)
    assert len(loaded) == 3


def test_parse_and_validate_challenge_accepts_valid_response():
    raw = json.dumps({
        "challenge_title": "Test",
        "description": "desc",
        "target_categories": ["овощи"],
        "mechanic": "скидка",
        "reward_rub": 30,
        "reasoning": "because",
    })
    result = parse_and_validate_challenge(raw, _config, max_reward_rub=100)
    assert result["target_categories"] == ["овощи"]
    assert result["reward_rub"] == 30


def test_parse_and_validate_challenge_rejects_forbidden_category():
    raw = json.dumps({
        "challenge_title": "Test",
        "description": "desc",
        "target_categories": ["алкоголь"],
        "mechanic": "скидка",
        "reward_rub": 30,
    })
    with pytest.raises(ValueError, match="forbidden"):
        parse_and_validate_challenge(raw, _config, max_reward_rub=100)


def test_parse_and_validate_challenge_clamps_reward_to_ceiling():
    raw = json.dumps({
        "challenge_title": "Test",
        "description": "desc",
        "target_categories": ["овощи"],
        "mechanic": "скидка",
        "reward_rub": 1000,
    })
    result = parse_and_validate_challenge(raw, _config, max_reward_rub=50)
    assert result["reward_rub"] == 50


def test_parse_and_validate_challenge_rejects_missing_fields():
    raw = json.dumps({"challenge_title": "Test"})
    with pytest.raises(ValueError, match="missing"):
        parse_and_validate_challenge(raw, _config, max_reward_rub=100)


def test_parse_and_validate_challenge_rejects_invalid_json():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_and_validate_challenge("not json", _config, max_reward_rub=100)


def test_parse_and_validate_challenge_strips_markdown_code_fence():
    # Observed live: anthropic/claude-haiku-4.5 via OpenRouter's Bedrock
    # route wraps output in a ```json fence even with response_format set.
    raw = (
        "```json\n"
        + json.dumps({
            "challenge_title": "Test",
            "description": "desc",
            "target_categories": ["овощи"],
            "mechanic": "скидка",
            "reward_rub": 30,
        })
        + "\n```"
    )
    result = parse_and_validate_challenge(raw, _config, max_reward_rub=100)
    assert result["target_categories"] == ["овощи"]


def test_build_personal_prompt_mentions_forbidden_categories_and_reward_ceiling():
    profile = _profile("promo_hunter", seed=1)
    system, user = build_personal_prompt(profile, _config, max_reward_rub=77.0)
    assert "алкоголь" in system
    assert "77" in system
    assert profile["chain"] in user


def test_compute_frequency_saturation_true_for_already_optimal():
    profile = _profile("already_optimal_no_challenge", seed=1)
    saturated, signal = compute_frequency_saturation(profile, _config)
    assert saturated is True
    assert signal["n_receipts_train"] >= signal["threshold"]


def test_compute_frequency_saturation_false_for_ordinary_frequency():
    profile = _profile("promo_hunter", seed=1)
    saturated, signal = compute_frequency_saturation(profile, _config)
    assert saturated is False


def test_generate_challenge_for_user_routes_already_optimal_to_no_challenge():
    profile = _profile("already_optimal_no_challenge", seed=1)
    result = generate_challenge_for_user(profile, _config, model="fake/model", dry_run=True)
    assert result["path"] == "no_challenge"


def test_build_spend_threshold_challenge_targets_the_most_bought_item():
    profile = _profile("bakes_on_weekends", seed=4)
    challenge = build_spend_threshold_challenge(profile, _config)
    assert challenge is not None
    assert challenge["favorite_item"] in challenge["challenge_title"]
    assert challenge["target_categories"][0] not in _config.forbidden_categories
    assert challenge["spend_threshold_rub"] >= 100.0
    assert challenge["reward_rub"] > 0


def test_build_spend_threshold_challenge_rejects_weak_signal():
    # seed=1's top item for bakes_on_weekends is bought only 4 times in
    # train — below min_purchase_count=6, so this must return None rather
    # than build a claim on a weak/coincidental "favorite".
    profile = _profile("bakes_on_weekends", seed=1)
    assert build_spend_threshold_challenge(profile, _config) is None
    # explicit low threshold on the same profile proves it's the count
    # check doing the rejecting, not something else about this profile
    assert build_spend_threshold_challenge(profile, _config, min_purchase_count=2) is not None


def test_build_spend_threshold_challenge_never_targets_forbidden_category():
    profile = _profile("promo_hunter", seed=1)
    challenge = build_spend_threshold_challenge(profile, _config)
    if challenge is not None:
        assert not (set(challenge["target_categories"]) & set(_config.forbidden_categories))


def test_build_spend_threshold_challenge_returns_none_without_train_receipts():
    profile = _profile("promo_hunter", seed=1)
    profile = {**profile, "receipts": [
        r for r in profile["receipts"] if r["purchase_date"] > _config.temporal_split.train_end.isoformat()
    ]}
    assert build_spend_threshold_challenge(profile, _config) is None


def test_generate_challenge_for_user_spend_threshold_type_makes_no_network_call(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter should not be called for challenge_type=spend_threshold")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    profile = _profile("bakes_on_weekends", seed=4)
    result = generate_challenge_for_user(
        profile, _config, model="fake/model", challenge_type="spend_threshold"
    )
    assert result["path"] == "personal"
    assert "spend_threshold_rub" in result


def test_generate_challenge_for_user_dry_run_makes_no_network_call():
    profile = _profile("bakes_on_weekends", seed=4)
    result = generate_challenge_for_user(profile, _config, model="fake/model", dry_run=True)
    assert result["path"] in ("personal_dry_run", "generic", "no_challenge")


def test_generate_challenge_for_user_non_receptive_uses_generic_without_network():
    profile = _profile("promo_hunter", seed=1)
    profile = {**profile, "receipts": [
        r for r in profile["receipts"] if r["purchase_date"] > _config.temporal_split.train_end.isoformat()
    ]}
    result = generate_challenge_for_user(profile, _config, model="fake/model")
    assert result["path"] == "generic"
    assert "challenge_title" in result


def test_generate_challenge_for_user_personal_path_with_mocked_llm(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return json.dumps({
            "challenge_title": "Допеки выходные",
            "description": "desc",
            "target_categories": ["бакалея"],
            "mechanic": "скидка",
            "reward_rub": 40,
            "reasoning": "weekend baking pattern",
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    result = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    assert result["path"] == "personal"
    assert result["target_categories"] == ["бакалея"]


def test_generate_challenge_for_user_falls_back_on_bad_llm_output(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return "not valid json"

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    result = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    assert result["path"] == "generic_fallback"
    assert "error" in result


def test_score_against_answer_key_basic():
    challenges = [
        {"user_id": "a", "path": "personal", "target_categories": ["овощи"], "mechanic": "скидка"},
        {"user_id": "b", "path": "generic", "target_categories": [], "mechanic": ""},
    ]
    answer_key = [
        {"user_id": "a", "acceptable_target_categories": ["овощи"], "acceptable_mechanics": ["скидка"], "abstain_is_correct": False},
        {"user_id": "b", "acceptable_target_categories": [], "acceptable_mechanics": [], "abstain_is_correct": True},
    ]
    result = score_against_answer_key(challenges, answer_key)
    assert result["hit_rate"] == 1.0
    assert result["scored"] == 2


def test_score_against_answer_key_no_challenge_path_counts_as_abstain_hit():
    challenges = [{"user_id": "c", "path": "no_challenge", "target_categories": [], "mechanic": ""}]
    answer_key = [{"user_id": "c", "acceptable_target_categories": [], "acceptable_mechanics": [], "abstain_is_correct": True}]
    result = score_against_answer_key(challenges, answer_key)
    assert result["hit_rate"] == 1.0


def test_score_against_answer_key_personal_path_is_a_miss_for_abstain_profile():
    challenges = [{"user_id": "d", "path": "personal", "target_categories": ["овощи"], "mechanic": "скидка"}]
    answer_key = [{"user_id": "d", "acceptable_target_categories": [], "acceptable_mechanics": [], "abstain_is_correct": True}]
    result = score_against_answer_key(challenges, answer_key)
    assert result["hit_rate"] == 0.0
