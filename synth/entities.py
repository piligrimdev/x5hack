from __future__ import annotations

import random
from dataclasses import dataclass

from synth.config import ChainConfig


@dataclass
class District:
    district_id: str
    name: str


@dataclass
class Household:
    household_id: str
    district_id: str
    family_size: int


@dataclass
class User:
    user_id: str
    household_id: str
    district_id: str


def build_districts(names: list[str]) -> list[District]:
    return [
        District(district_id=f"d_{i:02d}", name=name)
        for i, name in enumerate(names, start=1)
    ]


def assign_households(
    n_users: int,
    districts: list[District],
    household_size_weights: dict[int, float],
    seed: int,
) -> tuple[list[User], list[Household]]:
    """Group n_users into households of weighted-random size, each in a random district."""
    rng = random.Random(seed)
    sizes = list(household_size_weights.keys())
    weights = list(household_size_weights.values())

    users: list[User] = []
    households: list[Household] = []
    household_index = 0
    user_index = 0

    while user_index < n_users:
        household_index += 1
        size = min(rng.choices(sizes, weights=weights, k=1)[0], n_users - user_index)
        district = rng.choice(districts)
        household_id = f"h_{household_index:06d}"
        households.append(
            Household(household_id=household_id, district_id=district.district_id, family_size=size)
        )

        for _ in range(size):
            user_index += 1
            users.append(
                User(
                    user_id=f"u_{user_index:06d}",
                    household_id=household_id,
                    district_id=district.district_id,
                )
            )

    return users, households


def assign_chains_and_segments(
    n_users: int,
    chains: list[ChainConfig],
    seed: int,
) -> list[tuple[str, str]]:
    """For each of n_users, draw a chain uniformly, then a segment weighted
    by that chain's segment_weights. Returns (chain_name, segment_name)
    pairs, one per user index, in order."""
    rng = random.Random(seed)
    chain_names = [c.name for c in chains]
    chains_by_name = {c.name: c for c in chains}

    result: list[tuple[str, str]] = []
    for _ in range(n_users):
        chain_name = rng.choice(chain_names)
        chain = chains_by_name[chain_name]
        segment_names = list(chain.segment_weights.keys())
        weights = list(chain.segment_weights.values())
        segment_name = rng.choices(segment_names, weights=weights, k=1)[0]
        result.append((chain_name, segment_name))

    return result
