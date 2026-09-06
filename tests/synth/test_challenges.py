import json
from collections import Counter
from datetime import date

import pytest

from synth.challenges import (
    CHALLENGE_SLOTS,
    GENERIC_CHALLENGES,
    PERSONAL_TARGET_QUANTITY,
    SLOT_TARGET_QUANTITY,
    VIBE_CATEGORIES,
    _pick_distinct_generic_offer,
    backfill_target_sku,
    build_basket_prompt,
    build_basket_spend_challenge,
    build_category_expansion_challenge,
    build_personal_prompt,
    build_spend_threshold_challenge,
    build_survival_risk_challenge,
    build_vibe_prompt,
    compute_frequency_saturation,
    compute_receptiveness,
    estimate_max_reward_rub,
    find_sku_id_for_item,
    generate_challenge_for_user,
    generate_challenges,
    item_action_description,
    load_profiles,
    non_forbidden_category_names,
    parse_and_validate_challenge,
    pick_generic_challenge,
    pick_sku_in_category,
    pick_vibe_category,
    rewrite_descriptions_for_tracked_item,
    score_against_answer_key,
)
from synth.config import load_config
from synth.reference_profiles import default_class_list, reference_profiles
from synth.survival import SurvivalCurve, fit_km_curve

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


def test_item_action_description_defaults_to_generic_phrasing():
    assert item_action_description("морковь", 2, 50.0) == item_action_description("морковь", 2, 50.0, slot="generic")


def test_item_action_description_varies_phrasing_by_slot():
    """Each of the 5 challenge_slot values gets its own distinct phrasing —
    otherwise every challenge's description collapses into the identical
    sentence regardless of slot, which read as repetitive in production
    even though title/mechanic varied per slot."""
    descriptions = {
        slot: item_action_description("морковь", 2, 50.0, slot=slot)
        for slot in CHALLENGE_SLOTS
    }
    assert len(set(descriptions.values())) == len(CHALLENGE_SLOTS)
    for slot, description in descriptions.items():
        assert "морковь" in description
        assert "50" in description


def test_item_action_description_unknown_slot_falls_back_to_generic():
    assert item_action_description("морковь", 2, 50.0, slot="spend_threshold") == item_action_description(
        "морковь", 2, 50.0, slot="generic"
    )


def test_pick_sku_in_category_is_deterministic_and_within_category():
    sku = pick_sku_in_category(_config, "овощи", seed_key="user-x")
    assert sku is not None
    assert sku.category == "овощи"
    assert pick_sku_in_category(_config, "овощи", seed_key="user-x").sku_id == sku.sku_id


def test_pick_sku_in_category_varies_by_seed():
    skus = {pick_sku_in_category(_config, "овощи", seed_key=f"user-{i}").sku_id for i in range(20)}
    assert len(skus) > 1


def test_pick_sku_in_category_advances_on_next_cycle():
    first = pick_sku_in_category(_config, "овощи", seed_key="user-x", cycle_index=0)
    second = pick_sku_in_category(_config, "овощи", seed_key="user-x", cycle_index=1)
    assert first is not None
    assert second is not None
    assert first.sku_id != second.sku_id


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


def test_build_personal_prompt_spells_out_allowed_category_names():
    """Without an explicit list of real category names in the prompt, the
    LLM has invented near-miss names (e.g. "мясо, птица, рыба") that pass
    parse_and_validate_challenge's forbidden-list check but then fail DB
    category resolution downstream — spelling every valid name out here is
    the same fix `build_vibe_prompt`/`build_basket_prompt` already apply to
    their own narrower category sets."""
    profile = _profile("promo_hunter", seed=1)
    system, _ = build_personal_prompt(profile, _config, max_reward_rub=77.0)
    for category in non_forbidden_category_names(_config):
        assert category in system


def test_non_forbidden_category_names_excludes_forbidden():
    names = non_forbidden_category_names(_config)
    assert not (set(names) & set(_config.forbidden_categories))
    assert set(names) == {c.name for c in _config.categories} - set(_config.forbidden_categories)


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


def test_build_basket_prompt_restricts_to_suggested_categories_and_mentions_reward_ceiling():
    profile = _profile("promo_hunter", seed=1)
    suggested = [
        {"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2},
        {"item": "Хлеб белый", "category": "хлеб и выпечка", "weekly_quantity": 1},
    ]
    system, user = build_basket_prompt(profile, _config, max_reward_rub=65.0, suggested_items=suggested)
    assert "Молоко 3.2%" in system
    assert "Хлеб белый" in system
    assert "65" in system
    assert "Молоко 3.2%" in user


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


def _with_suggested_basket_items(profile: dict, items: list[dict]) -> dict:
    return {**profile, "suggested_basket_items": items}


def test_build_basket_spend_challenge_thresholds_from_mean_receipt_rounded_to_100():
    profile = _profile("bakes_on_weekends", seed=4)
    profile = _with_suggested_basket_items(profile, [
        {"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2},
    ])
    train_end = _config.temporal_split.train_end.isoformat()
    train_receipts = [r for r in profile["receipts"] if r["purchase_date"] <= train_end]
    mean_receipt_total = sum(r["total_rub"] for r in train_receipts) / len(train_receipts)
    expected_threshold = max(100.0, round(mean_receipt_total * 1.3 / 100) * 100)

    challenge = build_basket_spend_challenge(profile, _config)
    assert challenge is not None
    assert challenge["spend_threshold_rub"] == expected_threshold
    assert challenge["spend_threshold_rub"] % 100 == 0
    assert challenge["reward_rub"] == round(expected_threshold * 0.05, 2)
    assert challenge["target_quantity"] == 1
    assert challenge["target_categories"] == ["молочные продукты и яйца"]


def test_build_basket_spend_challenge_uses_custom_markup_and_cashback_pct():
    profile = _profile("bakes_on_weekends", seed=4)
    profile = _with_suggested_basket_items(profile, [
        {"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2},
    ])
    default = build_basket_spend_challenge(profile, _config)
    custom = build_basket_spend_challenge(profile, _config, markup_pct=50.0, cashback_pct=10.0)
    assert custom["spend_threshold_rub"] >= default["spend_threshold_rub"]
    assert custom["reward_rub"] == round(custom["spend_threshold_rub"] * 0.10, 2)


def test_build_basket_spend_challenge_rotates_anchor_on_next_cycle():
    profile = _profile("bakes_on_weekends", seed=4)
    profile = _with_suggested_basket_items(profile, [
        {"item": "молоко", "category": "молочные продукты и яйца", "weekly_quantity": 2},
        {"item": "морковь", "category": "овощи", "weekly_quantity": 1},
    ])

    first = build_basket_spend_challenge(profile, _config, cycle_index=0)
    second = build_basket_spend_challenge(profile, _config, cycle_index=1)

    assert first["target_sku_id"] != second["target_sku_id"]
    assert "молоко" in first["description"]
    assert "морковь" in second["description"]


def test_build_basket_spend_challenge_returns_none_without_suggested_items():
    profile = _profile("bakes_on_weekends", seed=4)
    assert build_basket_spend_challenge(profile, _config) is None


def test_build_basket_spend_challenge_uses_live_receipts_when_train_split_is_empty():
    profile = _profile("bakes_on_weekends", seed=4)
    profile = _with_suggested_basket_items(profile, [
        {"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2},
    ])
    profile = {**profile, "receipts": [
        r for r in profile["receipts"] if r["purchase_date"] > _config.temporal_split.train_end.isoformat()
    ]}
    challenge = build_basket_spend_challenge(profile, _config)
    assert challenge is not None
    assert challenge["challenge_title"] == "Кэшбэк за полную корзину"
    assert "доступная история" in challenge["reasoning"]


def _by_slot(results: list[dict]) -> dict[str, dict]:
    return {r["challenge_slot"]: r for r in results if "challenge_slot" in r}


def test_generate_challenge_for_user_llm_habit_uses_survival_risk_not_llm(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter must not be called for llm_habit/llm_discovery/generic")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    profile = _profile("bakes_on_weekends", seed=4)
    lines = [l for r in profile["receipts"] for l in r["lines"]]
    top_category = Counter(l["category"] for l in lines).most_common(1)[0][0]
    profile = {
        **profile,
        "category_last_purchase": {top_category: profile["receipts"][0]["purchase_date"]},
    }
    curves = {top_category: fit_km_curve([5, 10], [False, True])}

    results = generate_challenge_for_user(
        profile, _config, model="fake/model", api_key="fake-key", category_curves=curves,
    )
    habit = _by_slot(results)["llm_habit"]
    assert habit["path"] == "personal"
    assert habit["model"] is None
    assert habit["target_categories"] == [top_category]
    assert "prompt" not in habit
    assert "response" not in habit


def test_generate_challenge_for_user_llm_habit_falls_back_without_category_curves():
    profile = _profile("bakes_on_weekends", seed=4)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    habit = _by_slot(results)["llm_habit"]
    discovery = _by_slot(results)["llm_discovery"]
    assert habit["path"] == "generic_fallback"
    assert discovery["path"] == "generic_fallback"


def test_generate_challenge_for_user_dry_run_no_longer_affects_llm_habit_or_discovery():
    """dry_run only ever meant 'skip LLM calls' — llm_habit/llm_discovery
    make none any more, so dry_run must not change their result at all."""
    profile = _profile("bakes_on_weekends", seed=4)
    top_category = Counter(l["category"] for r in profile["receipts"] for l in r["lines"]).most_common(1)[0][0]
    profile = {
        **profile,
        "category_last_purchase": {top_category: profile["receipts"][0]["purchase_date"]},
    }
    curves = {top_category: fit_km_curve([5, 10], [False, True])}

    live = generate_challenge_for_user(profile, _config, model="fake/model", category_curves=curves)
    dry = generate_challenge_for_user(profile, _config, model="fake/model", category_curves=curves, dry_run=True)
    assert _by_slot(live)["llm_habit"]["target_categories"] == _by_slot(dry)["llm_habit"]["target_categories"]
    assert _by_slot(dry)["llm_habit"]["path"] == "personal"


def test_generate_challenge_for_user_always_returns_five_slots_regardless_of_pattern_strength(monkeypatch):
    """The receptiveness/saturation gates are gone from the live routing
    function — these three profile classes used to hit three DIFFERENT old
    branches. Now all three get the exact same 5-slot shape. `llm_habit`/
    `llm_discovery`/`llm_basket` all fall back to generic here: no
    `category_curves` is passed (nothing to rank against) and `_profile()`
    never sets `suggested_basket_items` (cold start)."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter should not be called under dry_run")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    for generation_class in ("bakes_on_weekends", "one_off_no_pattern", "already_optimal_no_challenge"):
        profile = _profile(generation_class, seed=1)
        results = generate_challenge_for_user(profile, _config, model="fake/model", dry_run=True)
        assert len(results) == len(CHALLENGE_SLOTS)
        by_slot = _by_slot(results)
        assert set(by_slot) == set(CHALLENGE_SLOTS)
        assert by_slot["llm_habit"]["path"] == "generic_fallback"
        assert by_slot["llm_discovery"]["path"] == "generic_fallback"
        assert by_slot["generic"]["path"] == "generic"
        assert by_slot["vibe"]["path"] == "personal_dry_run"
        assert by_slot["llm_basket"]["path"] == "generic_fallback"


def test_generate_challenge_for_user_llm_basket_uses_deterministic_mechanic_not_llm(monkeypatch):
    """`llm_basket` no longer calls the LLM at all — it's
    `build_basket_spend_challenge`, a pure function of the user's own
    train-period receipts and suggested weekly-basket items (anchor item +
    spend threshold + cashback %). The fake LLM response below is a trap:
    if `generate_challenge_for_user` ever routed llm_basket through the LLM
    again, its reward_rub (999) would leak into the result."""
    profile = _profile("bakes_on_weekends", seed=4)
    profile = {**profile, "suggested_basket_items": [
        {"item": "Молоко 3.2%", "category": "молочные продукты и яйца", "weekly_quantity": 2},
    ]}

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return json.dumps({
            "challenge_title": "should never be used for llm_basket",
            "description": "trap",
            "target_categories": ["бакалея"],
            "mechanic": "trap",
            "reward_rub": 999,
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    expected = build_basket_spend_challenge(profile, _config)
    assert expected is not None

    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    basket_result = _by_slot(results)["llm_basket"]
    assert basket_result["path"] == "personal"
    assert basket_result["model"] is None
    assert basket_result["target_categories"] == ["молочные продукты и яйца"]
    assert basket_result["spend_threshold_rub"] == expected["spend_threshold_rub"]
    assert basket_result["reward_rub"] == expected["reward_rub"]
    assert basket_result["reward_rub"] != 999


def test_generate_challenge_for_user_llm_basket_falls_back_without_calling_llm_when_no_suggestions(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_openrouter should not be called with no suggested_basket_items")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    profile = _profile("bakes_on_weekends", seed=4)
    # no suggested_basket_items key at all — same as a brand-new user
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    basket_result = _by_slot(results)["llm_basket"]
    assert basket_result["path"] == "generic_fallback"


def test_build_category_expansion_challenge_targets_least_bought_category():
    profile = _profile("bakes_on_weekends", seed=4)
    challenge = build_category_expansion_challenge(profile, _config)
    assert challenge is not None
    assert challenge["target_quantity"] == 1
    expected_sku = find_sku_id_for_item(_config, challenge["novel_category"], challenge["novel_item"])
    assert challenge["target_sku_id"] == expected_sku
    assert expected_sku is not None


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


def test_generate_challenge_for_user_vibe_slot_title_is_prefixed_with_vibe_of_the_month(monkeypatch):
    """Product decision: a successful vibe card's title always starts with
    "Вайб месяца: " so it visibly reads as part of the month's themed
    selection, not an ordinary personal challenge."""
    profile = _profile("bakes_on_weekends", seed=4)
    profile = {**profile, "vibe_category": "Экономия и запасы"}

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
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
    assert vibe_result["challenge_title"] == "Вайб месяца: Экономь на бакалее"


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
    assert vibe_result["path"] == "personal"
    assert vibe_result["challenge_title"].startswith("Вайб месяца:")
    assert vibe_result["target_categories"] == ["товары для животных"]
    assert "outside allowed set" in vibe_result["error"]


def test_generate_challenge_for_user_recovers_from_unrecognized_vibe_category(monkeypatch):
    # profile["vibe_category"] is a nullable free-text column with no CHECK
    # constraint at the DB level (by design — flexible for a future
    # manual-selection feature), so nothing guarantees a persisted value is
    # still one of the 6 known VIBE_CATEGORIES keys. An unrecognized value
    # must not crash the whole function (dropping all 4 slots) — it must
    # fall back to a freshly-picked valid theme for the vibe slot only.
    profile = _profile("bakes_on_weekends", seed=4)
    profile = {**profile, "vibe_category": "not-a-real-theme"}

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return json.dumps({
            "challenge_title": "Test",
            "description": "desc",
            "target_categories": ["бакалея"],
            "mechanic": "скидка",
            "reward_rub": 30,
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    assert len(results) == len(CHALLENGE_SLOTS)
    vibe_result = _by_slot(results)["vibe"]
    assert vibe_result["path"] == "personal"
    assert vibe_result["challenge_title"].startswith("Вайб месяца:")
    if vibe_result["path"] == "personal":
        assert vibe_result["target_categories"] == ["бакалея"]


def test_generate_challenge_for_user_only_vibe_carries_prompt_and_response(monkeypatch):
    """Regression for the audit-log mismatch: only `vibe` still calls the
    LLM, so only it should carry prompt/response on its result dict —
    llm_habit/llm_discovery/generic are all deterministic risk picks now
    and must not carry stale/borrowed prompt+response fields."""
    profile = _profile("bakes_on_weekends", seed=4)

    def fake_call(model, system, user, api_key=None, timeout=60.0, max_retries=3):
        return json.dumps({
            "challenge_title": "Vibe title",
            "description": "vibe desc",
            "target_categories": ["бакалея"],
            "mechanic": "скидка",
            "reward_rub": 20,
        })

    monkeypatch.setattr("synth.challenges.call_openrouter", fake_call)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    by_slot = _by_slot(results)

    assert "prompt" in by_slot["vibe"] and "response" in by_slot["vibe"]
    for slot in ("llm_habit", "llm_discovery", "generic"):
        assert "prompt" not in by_slot[slot]
        assert "response" not in by_slot[slot]


def test_generate_challenge_for_user_without_curves_or_working_llm_keeps_vibe_slot(monkeypatch):
    """Every slot without personalization data (no category_curves for the
    three risk-ranked slots, no suggested_basket_items for llm_basket) or a
    working LLM call (vibe, mocked to fail here) still produces five records,
    and the failed vibe response remains a themed challenge instead of an
    unrelated generic card."""
    def fail_if_called(*args, **kwargs):
        raise RuntimeError("simulated LLM outage")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    profile = _profile("bakes_on_weekends", seed=4)
    results = generate_challenge_for_user(profile, _config, model="fake/model", api_key="fake-key")
    assert len(results) == len(CHALLENGE_SLOTS)
    vibe_result = _by_slot(results)["vibe"]
    assert vibe_result["path"] == "personal"
    assert vibe_result["challenge_title"].startswith("Вайб месяца:")


def test_generic_slot_rotates_offer_by_generic_cycle_index():
    profile = _profile("promo_hunter", seed=1)
    profile_cycle0 = {**profile, "generic_cycle_index": 0}
    profile_cycle1 = {**profile, "generic_cycle_index": 1}

    results0 = generate_challenge_for_user(profile_cycle0, _config, model="fake/model", dry_run=True)
    results1 = generate_challenge_for_user(profile_cycle1, _config, model="fake/model", dry_run=True)

    generic0 = _by_slot(results0)["generic"]
    generic1 = _by_slot(results1)["generic"]
    assert generic0["challenge_title"] != generic1["challenge_title"]


def test_generic_slot_defaults_to_cycle_zero_when_not_set():
    profile = _profile("promo_hunter", seed=1)
    profile_explicit_zero = {**profile, "generic_cycle_index": 0}

    results_default = generate_challenge_for_user(profile, _config, model="fake/model", dry_run=True)
    results_explicit = generate_challenge_for_user(profile_explicit_zero, _config, model="fake/model", dry_run=True)

    assert _by_slot(results_default)["generic"]["challenge_title"] == _by_slot(results_explicit)["generic"]["challenge_title"]


def test_pick_distinct_generic_offer_cycle_offset_rotates_the_pick():
    """Direct unit check of the rotation mechanism in isolation (no shared
    `used_indices` with another slot, which could otherwise mask or shift
    the effect via the pre-existing within-batch collision-avoidance)."""
    offer_cycle0 = _pick_distinct_generic_offer("user-1", _config, used_indices=[], cycle_offset=0)
    offer_cycle1 = _pick_distinct_generic_offer("user-1", _config, used_indices=[], cycle_offset=1)
    assert offer_cycle0["challenge_title"] != offer_cycle1["challenge_title"]


def test_pick_distinct_generic_offer_cycle_offset_defaults_to_zero():
    offer_default = _pick_distinct_generic_offer("user-1", _config, used_indices=[])
    offer_explicit_zero = _pick_distinct_generic_offer("user-1", _config, used_indices=[], cycle_offset=0)
    assert offer_default == offer_explicit_zero


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


def test_rewrite_descriptions_for_tracked_item_uses_personal_records_own_slot_phrasing():
    """A `path == "personal"` record with a recognized challenge_slot name
    (e.g. "vibe") gets that slot's phrasing, not the generic default —
    matching what the live generator does for a successful LLM slot."""
    category = _config.categories[0].name
    item = _config.categories[0].items[0]
    sku_id = find_sku_id_for_item(_config, category, item)
    record = {
        "user_id": "u10", "path": "personal", "challenge_slot": "vibe",
        "target_categories": [category], "description": "старое описание",
        "target_sku_id": sku_id, "target_quantity": 2, "reward_rub": 25.0,
    }
    rewritten = rewrite_descriptions_for_tracked_item([record], _config)
    assert rewritten[0]["description"] == item_action_description(item, 2, 25.0, slot="vibe")
    assert rewritten[0]["description"] != item_action_description(item, 2, 25.0, slot="generic")


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


def _curve(times, survival):
    return SurvivalCurve(times=tuple(times), survival=tuple(survival))


def test_build_survival_risk_challenge_picks_the_nth_riskiest_category():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {
            "молочные продукты и яйца": "2026-08-01",  # 30 days ago -> high risk
            "овощи": "2026-08-28",  # 3 days ago -> low risk
        },
    }
    curves = {
        "молочные продукты и яйца": _curve([5, 30], [0.9, 0.1]),
        "овощи": _curve([5, 30], [0.9, 0.1]),
    }
    result = build_survival_risk_challenge(
        profile, _config, curves, rank=0, slot="llm_habit", as_of=date(2026, 8, 31),
    )
    assert result is not None
    assert result["target_categories"] == ["молочные продукты и яйца"]
    assert result["target_quantity"] == SLOT_TARGET_QUANTITY["llm_habit"]
    assert result["deadline_days"] is not None

    second = build_survival_risk_challenge(
        profile, _config, curves, rank=1, slot="llm_discovery", as_of=date(2026, 8, 31),
    )
    assert second["target_categories"] == ["овощи"]


def test_build_survival_risk_challenge_rotates_product_on_next_cycle():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {"овощи": "2026-08-01"},
    }
    curves = {"овощи": _curve([5, 30], [0.9, 0.1])}
    first = build_survival_risk_challenge(
        profile, _config, curves, rank=0, slot="llm_habit", as_of=date(2026, 8, 31), cycle_index=0,
    )
    second = build_survival_risk_challenge(
        profile, _config, curves, rank=0, slot="llm_habit", as_of=date(2026, 8, 31), cycle_index=1,
    )
    assert first["target_sku_id"] != second["target_sku_id"]


def test_build_survival_risk_challenge_returns_none_without_purchase_history():
    profile = {"user_id": "u1", "receipts": [], "category_last_purchase": {}}
    assert build_survival_risk_challenge(profile, _config, {}, rank=0, slot="llm_habit") is None


def test_build_survival_risk_challenge_returns_none_when_rank_exceeds_available_categories():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {"овощи": "2026-08-01"},
    }
    curves = {"овощи": _curve([5], [0.5])}
    assert build_survival_risk_challenge(profile, _config, curves, rank=1, slot="generic") is None


def test_build_survival_risk_challenge_skips_forbidden_categories():
    forbidden = _config.forbidden_categories[0]
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {forbidden: "2026-08-01", "овощи": "2026-08-01"},
    }
    curves = {forbidden: _curve([5], [0.1]), "овощи": _curve([5], [0.9])}
    result = build_survival_risk_challenge(profile, _config, curves, rank=0, slot="generic")
    assert result["target_categories"] == ["овощи"]


def test_build_survival_risk_challenge_skips_categories_without_a_fitted_curve():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {"овощи": "2026-08-01", "фрукты": "2026-08-01"},
    }
    # Only "овощи" has a curve — "фрукты" must be ignored, not crash.
    curves = {"овощи": _curve([5], [0.5])}
    result = build_survival_risk_challenge(profile, _config, curves, rank=0, slot="generic")
    assert result["target_categories"] == ["овощи"]
    assert build_survival_risk_challenge(profile, _config, curves, rank=1, slot="generic") is None


def test_build_survival_risk_challenge_deadline_from_median_survival_capped_at_30():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {"овощи": "2026-08-01"},
    }
    curves = {"овощи": _curve([5, 60], [0.9, 0.1])}  # median never <= 0.5 within cap... see below
    result = build_survival_risk_challenge(profile, _config, curves, rank=0, slot="generic")
    # median_survival_days() -> None for this curve (never <= 0.5 at t=5 or 60... 0.1 IS <= 0.5)
    # so median is 60 -> deadline caps at 30.
    assert result["deadline_days"] == 30


def test_build_survival_risk_challenge_deadline_defaults_when_no_median():
    profile = {
        "user_id": "u1",
        "receipts": [],
        "category_last_purchase": {"овощи": "2026-08-01"},
    }
    curves = {"овощи": _curve([5], [0.9])}  # never drops to 0.5 -> median is None
    result = build_survival_risk_challenge(profile, _config, curves, rank=0, slot="generic")
    assert result["deadline_days"] == 14


def test_generate_challenges_fits_population_curves_once_and_uses_them(monkeypatch):
    """The CLI batch entry point must fit curves from ALL profiles passed
    to it and actually use them — otherwise re-running it for hit-rate
    scoring would silently exercise only the cold-start fallback path."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("no LLM call expected for llm_habit/llm_discovery/generic")

    monkeypatch.setattr("synth.challenges.call_openrouter", fail_if_called)
    profiles = [_profile("bakes_on_weekends", seed=s) for s in (1, 2, 3)]

    # Compute category_last_purchase from receipts for each profile
    for profile in profiles:
        last_purchase = {}
        for receipt in profile.get("receipts", []):
            for line in receipt.get("lines", []):
                category = line["category"]
                if category not in last_purchase or receipt["purchase_date"] > last_purchase[category]:
                    last_purchase[category] = receipt["purchase_date"]
        profile["category_last_purchase"] = last_purchase

    results = generate_challenges(profiles, _config, model="fake/model", dry_run=True)
    by_user = {}
    for r in results:
        by_user.setdefault(r["user_id"], {})[r["challenge_slot"]] = r

    # At least one profile has enough purchase history that llm_habit
    # should resolve to a real risk pick rather than the cold-start
    # fallback, now that curves are actually being fit and passed through.
    assert any(
        slots["llm_habit"]["path"] == "personal" for slots in by_user.values()
    )
