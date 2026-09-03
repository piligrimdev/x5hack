import csv
import json

from synth.cli import main


def test_cli_population_writes_expected_file(tmp_path):
    out_path = tmp_path / "population.jsonl"
    main(["population", "--n", "5", "--seed", "1", "--out", str(out_path)])

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5
    assert all(json.loads(l)["user_id"] for l in lines)


def test_cli_population_writes_truth_file_when_requested(tmp_path):
    out_path = tmp_path / "population.jsonl"
    truth_path = tmp_path / "truth.jsonl"
    main(["population", "--n", "5", "--seed", "1", "--out", str(out_path), "--truth-out", str(truth_path)])

    lines = truth_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5
    assert "baseline_visits_28d" in json.loads(lines[0])


def test_cli_reference_writes_expected_file(tmp_path):
    out_path = tmp_path / "reference_profiles.json"
    main(["reference", "--count", "6", "--seed", "1", "--out", str(out_path)])

    profiles = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(profiles) == 6
    assert all("generation_class" in p for p in profiles)


def test_cli_reference_writes_blind_and_answer_key_files(tmp_path):
    out_path = tmp_path / "reference_profiles.json"
    blind_path = tmp_path / "blind.json"
    key_json_path = tmp_path / "answer_key.json"
    key_csv_path = tmp_path / "answer_key.csv"
    main([
        "reference", "--count", "6", "--seed", "1",
        "--out", str(out_path),
        "--blind-out", str(blind_path),
        "--answer-key-out", str(key_json_path),
        "--answer-key-csv-out", str(key_csv_path),
    ])

    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    assert len(blind) == 6
    assert all("generation_class" not in p for p in blind)

    answer_key = json.loads(key_json_path.read_text(encoding="utf-8"))
    assert len(answer_key) == 6

    with open(key_csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 6


def test_cli_challenges_dry_run_and_score(tmp_path):
    profiles_path = tmp_path / "reference_profiles.json"
    key_path = tmp_path / "answer_key.json"
    main([
        "reference", "--count", "6", "--seed", "1",
        "--out", str(profiles_path),
        "--answer-key-out", str(key_path),
    ])

    challenges_path = tmp_path / "challenges.json"
    main([
        "challenges", "--profiles", str(profiles_path),
        "--dry-run", "--out", str(challenges_path),
    ])
    challenges = json.loads(challenges_path.read_text(encoding="utf-8"))
    assert len(challenges) == 6

    main(["score-challenges", "--challenges", str(challenges_path), "--answer-key", str(key_path)])


def test_cli_challenges_requires_dry_run_or_api_key(tmp_path, monkeypatch):
    profiles_path = tmp_path / "reference_profiles.json"
    main(["reference", "--count", "2", "--seed", "1", "--out", str(profiles_path)])

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    try:
        main(["challenges", "--profiles", str(profiles_path), "--out", str(tmp_path / "out.json")])
        assert False, "expected SystemExit"
    except SystemExit:
        pass
