from synth.config import load_config


def test_load_config_returns_expected_structure():
    config = load_config("config/synth_schema.yaml")
    assert config.version == "0.5.0"
    assert len(config.categories) == 22
    assert all(5 <= len(c.items) <= 10 for c in config.categories)
    assert 0.0 < config.calibration.offline_share <= 1.0
    assert config.calibration.avg_receipt_total_rub > 0
    assert len(config.districts) == 20
    assert abs(sum(config.household_size_weights.values()) - 1.0) < 1e-6


def test_all_items_returns_category_item_pairs():
    config = load_config("config/synth_schema.yaml")
    pairs = config.all_items()
    assert len(pairs) == sum(len(c.items) for c in config.categories)
    assert all(isinstance(p, tuple) and len(p) == 2 for p in pairs)
    assert ("овощи", "картофель") in pairs


def test_load_config_parses_chains_and_segments():
    config = load_config("config/synth_schema.yaml")
    assert len(config.chains) == 3
    assert len(config.segments) == 5

    chain_names = {c.name for c in config.chains}
    assert chain_names == {"Пятёрочка", "Перекрёсток", "Чижик"}

    segment_names = {s.name for s in config.segments}
    assert segment_names == {
        "Молодёжь",
        "Взрослые с вредными привычками",
        "Взрослые с детьми до 3х лет",
        "Зрелые",
        "Старшие",
    }

    pyaterochka = next(c for c in config.chains if c.name == "Пятёрочка")
    assert pyaterochka.price_multiplier == 1.0
    assert set(pyaterochka.segment_weights.keys()) == segment_names

    starshie = next(s for s in config.segments if s.name == "Старшие")
    assert starshie.visit_frequency_multiplier > 1.0
    zrelye = next(s for s in config.segments if s.name == "Зрелые")
    assert zrelye.basket_size_multiplier > 1.0


def test_load_config_parses_category_economics_and_forbidden_categories():
    config = load_config("config/synth_schema.yaml")
    assert len(config.category_economics) == 22
    econ_categories = {e.category for e in config.category_economics}
    assert econ_categories == {c.name for c in config.categories}
    assert "алкоголь" in config.forbidden_categories
    for e in config.category_economics:
        assert e.base_price_rub > 0
        assert 0 < e.margin_pct < 1
        assert e.popularity_weight > 0


def test_load_config_parses_temporal_split():
    config = load_config("config/synth_schema.yaml")
    ts = config.temporal_split
    assert ts.train_start < ts.train_end < ts.holdout_start < ts.holdout_end
    assert ts.window_days == 90
