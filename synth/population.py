from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path

from synth.catalog import build_catalog, skus_by_category
from synth.config import SynthConfig
from synth.entities import assign_chains_and_segments, assign_households, build_districts
from synth.features import compute_observable_habitual_categories
from synth.receipts import generate_receipts_for_user
from synth.simulation_truth import generate_user_behavior


def population(n: int, seed: int, config: SynthConfig) -> tuple[list[dict], list[dict]]:
    """Generate a population of `n` synthetic users with receipt history
    over the full train+holdout window.

    Returns `(observable_users, simulation_truth_records)`:
    - `observable_users`: what a recommender may see — profile + receipts
      + an OBSERVABLE `habitual_categories` derived only from train-period
      receipts. This is what `write_population_jsonl` writes.
    - `simulation_truth_records`: hidden per-user behavioral parameters
      (baseline frequency, sensitivities, true category affinity, etc.)
      that must never reach a recommender — written separately by
      `write_simulation_truth_jsonl`.
    """
    districts = build_districts(config.districts)
    users, households = assign_households(n, districts, config.household_size_weights, seed)
    households_by_id = {h.household_id: h for h in households}

    chain_segment_seed = seed * 1_000_003 + 900_000_001
    chain_segments = assign_chains_and_segments(n, config.chains, chain_segment_seed)
    chains_by_name = {c.name: c for c in config.chains}
    segments_by_name = {s.name: s for s in config.segments}

    catalog = build_catalog(config)
    catalog_by_category = skus_by_category(catalog)
    category_names = [c.name for c in config.categories]

    observable: list[dict] = []
    truth_records: list[dict] = []
    for i, user in enumerate(users):
        habit_seed = seed * 8 + i * 8 + 1
        behavior_seed = seed * 8 + i * 8 + 2
        receipt_seed = seed * 8 + i * 8 + 3

        habit_rng = random.Random(habit_seed)
        generation_habitual = habit_rng.sample(category_names, k=habit_rng.randint(3, 6))

        chain_name, segment_name = chain_segments[i]
        chain_price_multiplier = chains_by_name[chain_name].price_multiplier
        segment_behavior = segments_by_name[segment_name]
        family_size = households_by_id[user.household_id].family_size

        receipt_kwargs, truth = generate_user_behavior(
            user.user_id,
            config,
            segment_behavior,
            family_size,
            generation_habitual,
            behavior_seed,
        )

        receipts = generate_receipts_for_user(
            user.user_id,
            config,
            catalog,
            catalog_by_category,
            seed=receipt_seed,
            habitual_categories=generation_habitual,
            price_multiplier=chain_price_multiplier,
            **receipt_kwargs,
        )

        observable_habitual = compute_observable_habitual_categories(receipts, config)

        observable.append(
            {
                "user_id": user.user_id,
                "household_id": user.household_id,
                "district_id": user.district_id,
                "family_size": family_size,
                "chain": chain_name,
                "segment": segment_name,
                "habitual_categories": observable_habitual,
                "receipts": [
                    {**asdict(r), "lines": [asdict(l) for l in r.lines]} for r in receipts
                ],
            }
        )
        truth_records.append({"user_id": user.user_id, **asdict(truth)})

    return observable, truth_records


def _open_jsonl_writer(path: Path):
    """Plain text writer, or gzip-compressed if `path` ends in `.gz` — this
    dataset's JSON is repetitive (field names, Cyrillic category/item text)
    and compresses well (~10x observed), so `.gz` is the recommended way to
    keep it well under 100MB without dropping any fields."""
    if path.suffix == ".gz":
        import gzip

        return gzip.open(path, "wt", encoding="utf-8")
    return open(path, "w", encoding="utf-8")


def write_population_jsonl(path: str | Path, users: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _open_jsonl_writer(path) as f:
        for user in users:
            f.write(json.dumps(user, ensure_ascii=False) + "\n")


def write_simulation_truth_jsonl(path: str | Path, truth_records: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _open_jsonl_writer(path) as f:
        for record in truth_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
