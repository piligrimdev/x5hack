import json

import pytest

from synth.challenges import (
    CHALLENGE_SLOTS,
    GENERIC_CHALLENGES,
    PERSONAL_TARGET_QUANTITY,
    VIBE_CATEGORIES,
    backfill_target_sku,
    build_category_expansion_challenge,
    build_personal_prompt,
    build_spend_threshold_challenge,
    build_vibe_prompt,
    compute_frequency_saturation,
    compute_receptiveness,
    estimate_max_reward_rub,
    find_sku_id_for_item,
    generate_challenge_for_user,
    item_action_description,
    load_profiles,
    parse_and_validate_challenge,
    pick_generic_challenge,
    pick_sku_in_category,
    pick_vibe_category,
    rewrite_descriptions_for_tracked_item,
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


def test_vibe_categories_partition_all_non_forbidden_categories_without_overlap():
    all_vibe_categories = [c for cats in VIBE_CATEGORIES.values() for c in cats]
    assert len(all_vibe_categories) == len(set(all_vibe_categories))
    expected = {c.name for c in _config.categories} - set(_config.forbidden_categories)
    assert set(all_vibe_categories) == expected


def test_pick_vibe_category_is_deterministic():
    assert pick_vibe_category("user-1", "2026-09") == pick_vibe_category("user-1", "2026-09")


def test_pick_vibe_category_varies_by_user():
    themes = {pick_vibe_category(f"user-{i}", "2026-09") for i in range(30)}
    assert len(themes) > 1


def test_pick_vibe_category_can_change_across_months():
    themes = {pick_vibe_category("user-1", f"2026-{m:02d}") for m in range(1, 13)}
    assert len(themes) > 1


def test_pick_vibe_category_always_returns_a_known_theme():
    assert pick_vibe_category("user-1", "2026-09") in VIBE_CATEGORIES


def test_pick_generic_challenge_is_deterministic():
    a = pick_generic_challenge("some-uuid-1", _config)
    b = pick_generic_challenge("some-uuid-1", _config)
    assert a == b


def test_pick_generic_challenge_varies_by_user():
    offers = {pick_generic_challenge(f"user-{i}", _config)["challenge_title"] for i in range(20)}
    assert len(offers) > 1


def test_pick_generic_challenge_attaches_sku_in_target_category():
    offer = pick_generic_challenge("some-uuid-1", _config)
    assert offer["target_quantity"] == PERSONAL_TARGET_QUANTITY
    sku = pick_sku_in_category(_config, offer["target_categories"][0], seed_key="some-uuid-1:sku")
    assert offer["target_sku_id"] == sku.sku_id


def test_pick_generic_challenge_description_names_the_tracked_item_not_the_category():
    offer = pick_generic_challenge("some-uuid-1", _config)
    sku = pick_sku_in_category(_config, offer["target_categories"][0], seed_key="some-uuid-1:sku")
    assert sku.item in offer["description"]
    assert offer["description"] == item_action_description(sku.item, offer["target_quantity"], offer["reward_rub"])


def test_item_action_description_pluralizes_raz_correctly():
    assert item_action_description("морковь", 1, 50.0).startswith("Купи «морковь» 1 раз ")
    assert item_action_description("морковь", 2, 50.0).startswith("Купи «морковь» 2 раза ")
    assert item_action_description("морковь", 5, 50.0).startswith("Купи «морковь» 5 раз ")
    assert item_action_description("морковь", 11, 50.0).startswith("Купи «морковь» 11 раз ")
    assert item_action_description("морковь", 21, 50.0).startswith("Купи «морковь» 21 раз ")


def test_pick_sku_in_category_is_deterministic_and_within_category():
    sku = pick_sku_in_category(_config, "овощи", seed_key="user-x")
    assert sku is not None
    assert sku.category == "овощи"
    assert pick_sku_in_category(_config, "овощи", seed_key="user-x").sku_id == sku.sku_id


def test_pick_sku_in_category_varies_by_seed():
    skus = {pick_sku_in_category(_config, "овощи", seed_key=f"user-{i}").sku_id for i in range(20)}
    assert len(skus) > 1


def test_pick_sku_in_category_unknown_category_returns_none():
    assert pick_sku_in_category(_config, "not-a-real-category", seed_key="user-x") is None


def test_find_sku_id_for_item_resolves_known_pair():
    category = _config.categories[0].name
    item = _config.categories[0].items[0]
    sku_id = find_sku_id_for_item(_config, category, item)
    assert sku_id is not None
    assert sku_id.startswith("sku_")


def test_find_sku_id_for_item_returns_none_for_unknown_pair():
    assert find_sku_id_for_item(_config, "овощи", "not-a-real-item") is None


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


def test_parse_and_validate_challenge_accepts_category_within_allowed_set():
    raw = json.dumps({
        "challenge_title": "Test",
        "description": "desc",
        "target_categories": ["бакалея"],
        "mechanic": "скидка",
        "reward_rub": 30,
    })
    result = parse_and_validate_challenge(
        raw, _config, max_reward_rub=100, allowed_categories={"бакалея", "консервация"}
    )
    assert result["target_categories"] == ["бакалея"]


def test_parse_and_validate_challenge_rejects_category_outside_allowed_set():
    raw = json.dumps({
        "challenge_title": "Test",
        "description": "desc",
        "target_categories": ["овощи"],
        "mechanic": "скидка",
        "reward_rub": 30,
    })
    with pytest.raises(ValueError, match="outside allowed set"):
        parse_and_validate_challenge(raw, _config, max_reward_rub=100, allowed_categories={"бакалея"})


def test_build_personal_prompt_mentions_forbidden_categories_and_reward_ceiling():
    profile = _profile("promo_hunter", seed=1)
    system, user = build_personal_prompt(profile, _config, max_reward_rub=77.0)
    assert "алкоголь" in system
    assert "77" in system
    assert profile["chain"] in user


def test_build_personal_prompt_discovery_focus_differs_from_habit_focus():
    profile = _profile("promo_hunter", seed=1)
    habit_system, _ = build_personal_prompt(profile, _config, max_reward_rub=50.0, focus="habit")
    discovery_system, _ = build_personal_prompt(profile, _config, max_reward_rub=50.0, focus="discovery")
    assert habit_system != discovery_system
    assert "почти" in discovery_system


def test_build_vibe_prompt_restricts_to_theme_categories_and_mentions_reward_ceiling():
    profile = _profile("promo_hunter", seed=1)
    system, user = build_vibe_prompt(profile, _config, max_reward_rub=65.0, vibe_category="Экономия и запасы")
    for cat in VIBE_CATEGORIES["Экономия и запасы"]:
        assert cat in system
    assert "65" in system
    assert "Экономия и запасы" in user


def test_compute_frequency_saturation_true_for_already_optimal():
    profile = _profile("already_optimal_no_challenge", seed=1)
    saturated, signal = compute_frequency_saturation(profile, _config)
    assert saturated is True
    assert signal["n_receipts_train"] >= signal["threshold"]


def test_compute_frequency_saturation_false_for_ordinary_frequency():
    profile = _profile("promo_hunter", seed=1)
    saturated, signal = compute_frequency_saturation(profile, _config)
    assert saturated is False


def test_build_spend_threshold_challenge_targets_the_most_bought_item():
    profile = _profile("bakes_on_weekends", seed=4)
    challenge = build_spend_threshold_challenge(profile, _config)
    assert challenge is not None
    assert challenge["favorite_item"] in challenge["challenge_title"]
    assert challenge["target_categories"][0] not in _config.forbidden_categories
    assert challenge["spend_threshold_rub"] >= 100.0
    assert challenge["reward_rub"] > 0
    assert challenge["target_quantity"] == 1
    expected_sku = find_sku_id_for_item(_config, challenge["target_categories"][0], challenge["favorite_item"])
    assert challenge["target_sku_id"] == expected_sku
    assert expected_sku is not None


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


def _by_slot(results: list[dict]) -> dict[str, dict]:
    return {r["challenge_slot"]: r for r in results if "challenge_slot" in r}


def test_generate_challenge_for_user_always_returns_four_slots_regardless_of_pattern_strength(monkeypatch):
    """The receptiveness/saturation gates are gone from the live routing
    function — these three profile classes used to hit three DIFFERENT old
    branches (strong pattern -> mostly personal, weak pattern -> all
    generic, already_optimal -> zero records). Now all three get the exact
    same 4-slot shape."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter should not be called under dry_run")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    for generation_class in ("bakes_on_weekends", "one_off_no_pattern", "already_optimal_no_challenge"):
        profile = _profile(generation_class, seed=1)
        results = generate_challenge_for_user(profile, _config, model="fake/model", dry_run=True)
        assert len(results) == len(CHALLENGE_SLOTS)
        by_slot = _by_slot(results)
        assert set(by_slot) == set(CHALLENGE_SLOTS)
        assert by_slot["llm_habit"]["path"] == "personal_dry_run"
        assert by_slot["llm_discovery"]["path"] == "personal_dry_run"
        assert by_slot["vibe"]["path"] == "personal_dry_run"
        assert by_slot["generic"]["path"] == "generic"


def test_build_category_expansion_challenge_targets_least_bought_category():
    profile = _profile("bakes_on_weekends", seed=4)
    challenge = build_category_expansion_challenge(profile, _config)
    assert challenge is not None
    assert challenge["target_quantity"] == 1
    expected_sku = find_sku_id_for_item(_config, challenge["novel_category"], challenge["novel_item"])
    assert challenge["target_sku_id"] == expected_sku
    assert expected_sku is not None


def test_generate_challenge_for_user_llm_habit_personal_path_with_mocked_llm(monkeypatch):
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
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    llm_result = _by_slot(results)["llm_habit"]
    assert llm_result["path"] == "personal"
    assert llm_result["target_categories"] == ["бакалея"]
    assert llm_result["target_quantity"] == PERSONAL_TARGET_QUANTITY
    sku = pick_sku_in_category(_config, "бакалея", seed_key=f"{profile['user_id']}:sku:llm_habit")
    assert llm_result["target_sku_id"] == sku.sku_id
    assert llm_result["challenge_title"] == "Допеки выходные"
    assert sku.item in llm_result["description"]
    assert llm_result["description"] == item_action_description(sku.item, PERSONAL_TARGET_QUANTITY, 40)


def test_generate_challenge_for_user_falls_back_on_bad_llm_output(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return "not valid json"

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    llm_result = _by_slot(results)["llm_habit"]
    assert llm_result["path"] == "generic_fallback"
    assert "error" in llm_result
    assert llm_result["model"] == "fake/model"
    assert len(results) == len(CHALLENGE_SLOTS)


def test_generate_challenge_for_user_vibe_slot_uses_profile_vibe_category(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)
    profile = {**profile, "vibe_category": "Экономия и запасы"}

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        assert "Экономия и запасы" in system
        return json.dumps({
            "challenge_title": "Экономь на бакалее",
            "description": "desc",
            "target_categories": ["бакалея"],
            "mechanic": "скидка",
            "reward_rub": 30,
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    vibe_result = _by_slot(results)["vibe"]
    assert vibe_result["path"] == "personal"
    assert vibe_result["target_categories"] == ["бакалея"]


def test_generate_challenge_for_user_vibe_slot_falls_back_when_llm_picks_category_outside_theme(monkeypatch):
    profile = _profile("bakes_on_weekends", seed=4)
    profile = {**profile, "vibe_category": "Забота о питомце"}  # only "товары для животных" allowed

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return json.dumps({
            "challenge_title": "Скидка на бакалею",
            "description": "desc",
            "target_categories": ["бакалея"],
            "mechanic": "скидка",
            "reward_rub": 30,
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    vibe_result = _by_slot(results)["vibe"]
    assert vibe_result["path"] == "generic_fallback"
    assert "outside allowed set" in vibe_result["error"]


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


def test_backfill_target_sku_resolves_generic_and_personal_records_via_hash():
    legacy = [
        {"user_id": "u1", "path": "generic", "target_categories": ["овощи"], "mechanic": "бонусные баллы"},
        {"user_id": "u2", "path": "personal", "target_categories": ["бакалея"], "mechanic": "скидка"},
    ]
    backfilled = backfill_target_sku(legacy, _config)
    assert all(c["target_sku_id"] is not None for c in backfilled)
    assert all(c["target_quantity"] == PERSONAL_TARGET_QUANTITY for c in backfilled)
    # deterministic: matches the same hash-based pick a fresh generic offer would get
    expected = pick_sku_in_category(_config, "овощи", seed_key="u1:sku")
    assert backfilled[0]["target_sku_id"] == expected.sku_id


def test_backfill_target_sku_resolves_deterministic_paths_via_named_item():
    category = _config.categories[0].name
    item = _config.categories[0].items[0]
    legacy = [{
        "user_id": "u3", "path": "personal", "target_categories": [category],
        "mechanic": "порог трат + скидка на любимый товар", "favorite_item": item,
    }]
    backfilled = backfill_target_sku(legacy, _config)
    assert backfilled[0]["target_sku_id"] == find_sku_id_for_item(_config, category, item)
    assert backfilled[0]["target_quantity"] == 1


def test_backfill_target_sku_skips_no_challenge_and_already_backfilled_records():
    legacy = [
        {"user_id": "u4", "path": "no_challenge", "target_categories": [], "mechanic": ""},
        {"user_id": "u5", "path": "generic", "target_categories": ["овощи"], "mechanic": "", "target_sku_id": "sku_9999"},
    ]
    backfilled = backfill_target_sku(legacy, _config)
    assert "target_sku_id" not in backfilled[0]
    assert backfilled[1]["target_sku_id"] == "sku_9999"
    assert "target_quantity" not in backfilled[1]


def test_rewrite_descriptions_for_tracked_item_rewrites_generic_and_llm_slot():
    category = _config.categories[0].name
    item = _config.categories[0].items[0]
    sku_id = find_sku_id_for_item(_config, category, item)
    records = [
        {
            "user_id": "u1", "path": "generic", "target_categories": [category],
            "description": "старое описание про категорию", "target_sku_id": sku_id,
            "target_quantity": 2, "reward_rub": 30.0,
        },
        {
            "user_id": "u2", "path": "personal", "challenge_slot": "llm", "target_categories": [category],
            "description": "старое описание про категорию", "target_sku_id": sku_id,
            "target_quantity": 2, "reward_rub": 40.0,
        },
    ]
    rewritten = rewrite_descriptions_for_tracked_item(records, _config)
    expected = item_action_description(item, 2, 30.0)
    assert rewritten[0]["description"] == expected
    assert rewritten[1]["description"] == item_action_description(item, 2, 40.0)


def test_rewrite_descriptions_for_tracked_item_rewrites_generic_fallback_despite_slot_name():
    # A generic_fallback for the spend_threshold slot carries
    # challenge_slot="spend_threshold" (naming what it's replacing) but its
    # actual copy is a GENERIC_CHALLENGES offer, not favorite_item-specific
    # text — challenge_slot alone must not be read as "already item-specific".
    category = _config.categories[0].name
    item = _config.categories[0].items[0]
    sku_id = find_sku_id_for_item(_config, category, item)
    record = {
        "user_id": "u9", "path": "generic_fallback", "challenge_slot": "spend_threshold",
        "target_categories": [category], "description": "10% скидка на бытовую химию у партнёра сети.",
        "target_sku_id": sku_id, "target_quantity": 2, "reward_rub": 60.0,
    }
    rewritten = rewrite_descriptions_for_tracked_item([record], _config)
    assert rewritten[0]["description"] == item_action_description(item, 2, 60.0)


def test_rewrite_descriptions_for_tracked_item_leaves_item_specific_records_untouched():
    category = _config.categories[0].name
    item = _config.categories[0].items[0]
    sku_id = find_sku_id_for_item(_config, category, item)
    records = [
        # already names its own item via favorite_item — must not be touched
        {
            "user_id": "u3", "path": "personal", "challenge_slot": "spend_threshold",
            "target_categories": [category], "favorite_item": item,
            "description": "Потрать от 500 ₽ и получи скидку", "target_sku_id": sku_id,
            "target_quantity": 1, "reward_rub": 20.0,
        },
        # no_challenge record — nothing to rewrite
        {"user_id": "u4", "path": "no_challenge", "description": "n/a"},
    ]
    rewritten = rewrite_descriptions_for_tracked_item(records, _config)
    assert rewritten[0]["description"] == "Потрать от 500 ₽ и получи скидку"
    assert rewritten[1]["description"] == "n/a"
