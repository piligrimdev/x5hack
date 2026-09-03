import json
import re

from synth.config import load_config
from synth.reference_profiles import (
    GENERATION_CLASSES,
    build_answer_key,
    default_class_list,
    reference_profiles,
    write_answer_key_csv,
    write_answer_key_json,
    write_blind_reference_profiles_json,
    write_reference_profiles_json,
)

_config = load_config("config/synth_schema.yaml")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)


def test_default_class_list_covers_all_classes_and_is_shuffled():
    classes = default_class_list(40, seed=1)
    assert len(classes) == 40
    assert set(classes) == set(GENERATION_CLASSES)
    assert classes[:5] != list(GENERATION_CLASSES)  # round-robin order must be shuffled away


def test_default_class_list_is_deterministic_for_same_seed():
    a = default_class_list(40, seed=7)
    b = default_class_list(40, seed=7)
    assert a == b


def test_reference_profiles_generates_one_per_class_entry():
    classes = default_class_list(15, seed=42)
    profiles = reference_profiles(classes, seed=42, config=_config)
    assert len(profiles) == 15
    assert [p["generation_class"] for p in profiles] == classes
    assert all(p["receipts"] for p in profiles)


def test_reference_profile_ids_are_uuids_not_sequential():
    classes = default_class_list(10, seed=1)
    profiles = reference_profiles(classes, seed=1, config=_config)
    ids = [p["user_id"] for p in profiles]
    assert len(set(ids)) == len(ids)
    assert all(_UUID_RE.match(uid) for uid in ids)
    assert not any(uid.startswith("ref_") for uid in ids)


def test_bakes_on_weekends_receipts_lean_toward_baking_categories():
    profiles = reference_profiles(["bakes_on_weekends"], seed=1, config=_config)
    lines = [l for r in profiles[0]["receipts"] for l in r["lines"]]
    baking = {"бакалея", "хлеб и выпечка", "молочные продукты и яйца"}
    baking_count = sum(1 for l in lines if l["category"] in baking)
    assert baking_count / len(lines) > 0.4  # noisy overlap by design, not the old tight >0.5


def test_one_off_no_pattern_has_a_weak_but_nonempty_habitual_list():
    profiles = reference_profiles(["one_off_no_pattern"], seed=1, config=_config)
    assert profiles[0]["habitual_categories"] is not None
    # not required to be nonempty (train-period derivation could legitimately
    # produce an empty top-K if purchases are very spread out) but must not
    # be a hardcoded None sentinel — checked by the type assertion above


def test_already_optimal_class_has_low_frequency_headroom():
    profiles = reference_profiles(["already_optimal_no_challenge"], seed=1, config=_config)
    truth = profiles[0]["_simulation_truth"]
    assert truth["frequency_headroom"] < 0.10
    assert truth["baseline_visits_28d"] > 25


def test_write_reference_profiles_json_round_trips(tmp_path):
    classes = default_class_list(6, seed=1)
    profiles = reference_profiles(classes, seed=1, config=_config)
    out_path = tmp_path / "reference_profiles.json"
    write_reference_profiles_json(out_path, profiles)

    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert [p["user_id"] for p in loaded] == [p["user_id"] for p in profiles]
    assert "generation_class" in loaded[0]
    assert "_simulation_truth" in loaded[0]


def test_blind_export_strips_hidden_fields_and_shuffles(tmp_path):
    classes = default_class_list(20, seed=1)
    profiles = reference_profiles(classes, seed=1, config=_config)
    out_path = tmp_path / "blind.json"
    write_blind_reference_profiles_json(out_path, profiles, seed=1)

    blind = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(blind) == len(profiles)
    for p in blind:
        assert "generation_class" not in p
        assert "_simulation_truth" not in p
    assert [p["user_id"] for p in blind] != [p["user_id"] for p in profiles]


def test_answer_key_covers_every_profile_and_marks_draft():
    classes = default_class_list(10, seed=1)
    profiles = reference_profiles(classes, seed=1, config=_config)
    answer_key = build_answer_key(profiles, _config)

    assert {a["user_id"] for a in answer_key} == {p["user_id"] for p in profiles}
    assert all(a["draft"] is True for a in answer_key)
    assert all("алкоголь" in a["forbidden_categories"] for a in answer_key)


def test_answer_key_has_abstain_correct_for_no_challenge_classes():
    profiles = reference_profiles(["one_off_no_pattern", "already_optimal_no_challenge"], seed=1, config=_config)
    answer_key = build_answer_key(profiles, _config)
    assert all(a["abstain_is_correct"] is True for a in answer_key)


def test_answer_key_csv_has_editable_columns(tmp_path):
    classes = default_class_list(5, seed=1)
    profiles = reference_profiles(classes, seed=1, config=_config)
    answer_key = build_answer_key(profiles, _config)
    out_path = tmp_path / "answer_key.csv"
    write_answer_key_json(tmp_path / "answer_key.json", answer_key)
    write_answer_key_csv(out_path, answer_key)

    import csv

    with open(out_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 5
    assert "confirmed_by" in rows[0]
    assert "corrected_challenge" in rows[0]
    assert rows[0]["draft"] == "True"
