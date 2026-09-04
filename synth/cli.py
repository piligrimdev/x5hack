from __future__ import annotations

import argparse
import json
import os

from dotenv import load_dotenv

from synth.challenges import (
    generate_challenges,
    load_profiles,
    score_against_answer_key,
    write_challenges_json,
)
from synth.config import load_config
from synth.population import population, write_population_jsonl, write_simulation_truth_jsonl
from synth.reference_profiles import (
    build_answer_key,
    default_class_list,
    reference_profiles,
    write_answer_key_csv,
    write_answer_key_json,
    write_blind_reference_profiles_json,
    write_reference_profiles_json,
)
from synth.simulation import (
    simulate_population,
    summarize_simulation,
    write_simulation_details_jsonl,
    write_simulation_report,
)

load_dotenv()  # reads .env in the current directory (if present) into os.environ


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synth", description="Generate synthetic loyalty-program data.")
    parser.add_argument(
        "--config", default="config/synth_schema.yaml", help="Path to the frozen schema config."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pop_parser = subparsers.add_parser("population", help="Generate the 1-10k user population for simulation.")
    pop_parser.add_argument("--n", type=int, required=True, help="Number of users to generate.")
    pop_parser.add_argument("--seed", type=int, required=True)
    pop_parser.add_argument("--out", default="data/population_1k-10k.jsonl")
    pop_parser.add_argument(
        "--truth-out",
        default=None,
        help="Optional path to write the hidden simulation_truth.jsonl (never feed this to a recommender).",
    )

    ref_parser = subparsers.add_parser("reference", help="Generate the 30-50 reference profiles for hit-rate eval.")
    ref_parser.add_argument("--count", type=int, default=40, help="Number of reference profiles to generate.")
    ref_parser.add_argument("--seed", type=int, required=True)
    ref_parser.add_argument("--out", default="data/reference_profiles.json")
    ref_parser.add_argument(
        "--blind-out",
        default=None,
        help="Optional path to also write a blind-labeling copy (no generation_class/simulation_truth, shuffled order).",
    )
    ref_parser.add_argument(
        "--answer-key-out",
        default=None,
        help="Optional path to write the draft ground-truth answer key (JSON).",
    )
    ref_parser.add_argument(
        "--answer-key-csv-out",
        default=None,
        help="Optional path to write the draft answer key as an editable CSV template.",
    )

    chal_parser = subparsers.add_parser(
        "challenges",
        help="Generate personal (LLM via OpenRouter) or generic (partner catalog) challenges for a set of profiles.",
    )
    chal_parser.add_argument(
        "--profiles", required=True,
        help="Path to a reference_profiles*.json (array) or population*.jsonl(.gz) file.",
    )
    chal_parser.add_argument(
        "--model", default="deepseek/deepseek-chat",
        help="OpenRouter model slug — verify the exact current slug at https://openrouter.ai/models before a real run.",
    )
    chal_parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    chal_parser.add_argument(
        "--challenge-type", choices=["llm", "spend_threshold", "category_expansion"], default="llm",
        help="'llm': free-form challenge via OpenRouter. "
             "'spend_threshold': deterministic 'spend >= N rub, get a discount on your favorite product' — no API call, no cost. "
             "'category_expansion': deterministic discount on a category the user essentially never buys — no API call, no cost.",
    )
    chal_parser.add_argument(
        "--dry-run", action="store_true",
        help="Classify receptiveness and pick generic offers, but make no real LLM calls (ignored for --challenge-type spend_threshold/category_expansion, which never call an LLM).",
    )
    chal_parser.add_argument("--delay", type=float, default=0.0, help="Seconds to sleep between LLM calls.")
    chal_parser.add_argument("--limit", type=int, default=None, help="Only process the first N profiles.")
    chal_parser.add_argument("--out", default="data/v2/challenges.json")

    score_parser = subparsers.add_parser(
        "score-challenges", help="Score a generated challenges.json against the reference answer key."
    )
    score_parser.add_argument("--challenges", required=True)
    score_parser.add_argument("--answer-key", required=True)

    sim_parser = subparsers.add_parser(
        "simulate",
        help="Simulate H1/H4 effect: for each population user, route a challenge (no LLM calls) "
             "and simulate whether/how much it shifts purchase frequency, using simulation_truth.jsonl.",
    )
    sim_parser.add_argument("--population", required=True, help="population*.jsonl(.gz) file.")
    sim_parser.add_argument("--truth", required=True, help="simulation_truth.jsonl file (same run as --population).")
    sim_parser.add_argument(
        "--challenge-type", choices=["llm", "spend_threshold", "category_expansion"], default="llm",
        help="'llm': personal challenges valued via the frequency (extra-visit) channel, same as the "
             "'challenges' subcommand's default. 'spend_threshold': personal challenges valued via the "
             "basket-uplift (bigger-trip) channel instead. 'category_expansion': personal challenges valued "
             "via the fully-incremental expansion (new-category-trial) channel instead.",
    )
    sim_parser.add_argument("--report-out", default="data/v2/simulation_report.json")
    sim_parser.add_argument(
        "--details-out", default=None,
        help="Optional path to write per-user simulation results as JSONL.",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)

    if args.command == "population":
        users, truth_records = population(n=args.n, seed=args.seed, config=config)
        write_population_jsonl(args.out, users)
        print(f"Wrote {len(users)} users to {args.out}")
        if args.truth_out:
            write_simulation_truth_jsonl(args.truth_out, truth_records)
            print(f"Wrote {len(truth_records)} simulation-truth records to {args.truth_out}")
    elif args.command == "reference":
        classes = default_class_list(args.count, seed=args.seed)
        profiles = reference_profiles(classes, seed=args.seed, config=config)
        write_reference_profiles_json(args.out, profiles)
        print(f"Wrote {len(profiles)} reference profiles to {args.out}")
        if args.blind_out:
            write_blind_reference_profiles_json(args.blind_out, profiles, seed=args.seed)
            print(f"Wrote {len(profiles)} blind reference profiles to {args.blind_out}")
        if args.answer_key_out or args.answer_key_csv_out:
            answer_key = build_answer_key(profiles, config)
            if args.answer_key_out:
                write_answer_key_json(args.answer_key_out, answer_key)
                print(f"Wrote draft answer key ({len(answer_key)} entries) to {args.answer_key_out}")
            if args.answer_key_csv_out:
                write_answer_key_csv(args.answer_key_csv_out, answer_key)
                print(f"Wrote draft answer key CSV template to {args.answer_key_csv_out}")
    elif args.command == "challenges":
        profiles = load_profiles(args.profiles)
        if args.limit:
            profiles = profiles[: args.limit]
        api_key = os.environ.get(args.api_key_env)
        if args.challenge_type == "llm" and not args.dry_run and not api_key:
            raise SystemExit(
                f"{args.api_key_env} is not set and --dry-run was not passed — "
                "either export the key, add --dry-run, or use --challenge-type spend_threshold / "
                "category_expansion (no API call needed)."
            )
        challenges = generate_challenges(
            profiles, config, model=args.model, api_key=api_key, dry_run=args.dry_run,
            delay_seconds=args.delay, challenge_type=args.challenge_type,
        )
        write_challenges_json(args.out, challenges)
        n_none = sum(1 for c in challenges if c["path"] == "no_challenge")
        n_personal = sum(1 for c in challenges if c["path"] in ("personal", "personal_dry_run"))
        n_generic = sum(1 for c in challenges if c["path"] in ("generic", "generic_fallback"))
        n_fallback = sum(1 for c in challenges if c["path"] == "generic_fallback")
        print(
            f"Wrote {len(challenges)} challenges to {args.out} "
            f"({n_none} no-challenge, {n_personal} personal-path, {n_generic} generic-path, "
            f"{n_fallback} of those were fallbacks)"
        )
    elif args.command == "score-challenges":
        with open(args.challenges, encoding="utf-8") as f:
            challenges = json.load(f)
        with open(args.answer_key, encoding="utf-8") as f:
            answer_key = json.load(f)
        result = score_against_answer_key(challenges, answer_key)
        print(f"Hit rate: {result['hit_rate']:.1%} ({result['hits']}/{result['scored']})")
    elif args.command == "simulate":
        users = load_profiles(args.population)
        truth_records = load_profiles(args.truth)
        results = simulate_population(users, truth_records, config, challenge_type=args.challenge_type)
        report = summarize_simulation(results)
        write_simulation_report(args.report_out, report)
        if args.details_out:
            write_simulation_details_jsonl(args.details_out, results)
        overall = report["overall"]
        print(
            f"Simulated {report['n_total_users']} users. "
            f"Response rate: {overall['response_rate']:.1%}, "
            f"frequency uplift: {overall['frequency_uplift_pct']:.2f}%, "
            f"net value: {overall['net_value_rub']:,.0f} rub "
            f"(+{overall['total_extra_margin_rub']:,.0f} margin - {overall['total_reward_paid_rub']:,.0f} reward). "
            f"Full report: {args.report_out}"
        )


if __name__ == "__main__":
    main()
