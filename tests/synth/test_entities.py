from synth.config import ChainConfig
from synth.entities import build_districts, assign_households, assign_chains_and_segments


def _sample_chains() -> list[ChainConfig]:
    return [
        ChainConfig(
            name="Пятёрочка",
            price_multiplier=1.0,
            segment_weights={"Молодёжь": 0.7, "Старшие": 0.3},
        ),
        ChainConfig(
            name="Чижик",
            price_multiplier=0.75,
            segment_weights={"Молодёжь": 0.2, "Старшие": 0.8},
        ),
    ]


def test_build_districts_creates_one_per_name():
    districts = build_districts(["Район-01", "Район-02"])
    assert [d.district_id for d in districts] == ["d_01", "d_02"]
    assert districts[0].name == "Район-01"


def test_assign_households_covers_all_users_exactly_once():
    districts = build_districts(["Район-01", "Район-02", "Район-03"])
    users, households = assign_households(
        n_users=50,
        districts=districts,
        household_size_weights={1: 0.5, 2: 0.5},
        seed=42,
    )
    assert len(users) == 50
    assert len({u.user_id for u in users}) == 50
    household_ids = {h.household_id for h in households}
    district_ids = {d.district_id for d in districts}
    assert all(u.household_id in household_ids for u in users)
    assert all(u.district_id in district_ids for u in users)


def test_assign_households_is_deterministic_for_same_seed():
    districts = build_districts(["Район-01", "Район-02"])
    users_a, _ = assign_households(30, districts, {1: 1.0}, seed=7)
    users_b, _ = assign_households(30, districts, {1: 1.0}, seed=7)
    assert [u.user_id for u in users_a] == [u.user_id for u in users_b]
    assert [u.household_id for u in users_a] == [u.household_id for u in users_b]


def test_assign_chains_and_segments_covers_all_users():
    result = assign_chains_and_segments(n_users=200, chains=_sample_chains(), seed=1)
    assert len(result) == 200
    chain_names = {"Пятёрочка", "Чижик"}
    segment_names = {"Молодёжь", "Старшие"}
    assert all(chain in chain_names for chain, _ in result)
    assert all(segment in segment_names for _, segment in result)


def test_assign_chains_and_segments_is_deterministic_for_same_seed():
    a = assign_chains_and_segments(100, _sample_chains(), seed=7)
    b = assign_chains_and_segments(100, _sample_chains(), seed=7)
    assert a == b


def test_assign_chains_and_segments_respects_segment_weights_per_chain():
    result = assign_chains_and_segments(n_users=5000, chains=_sample_chains(), seed=42)
    pyaterochka_segments = [seg for chain, seg in result if chain == "Пятёрочка"]
    chizhik_segments = [seg for chain, seg in result if chain == "Чижик"]

    pyaterochka_young_share = pyaterochka_segments.count("Молодёжь") / len(pyaterochka_segments)
    chizhik_young_share = chizhik_segments.count("Молодёжь") / len(chizhik_segments)

    # Пятёрочка's weights give 70% Молодёжь, Чижик's give 20% — should be
    # clearly separated, not just "roughly random"
    assert pyaterochka_young_share > 0.6
    assert chizhik_young_share < 0.3
