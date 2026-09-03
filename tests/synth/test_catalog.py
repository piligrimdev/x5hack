from synth.catalog import build_catalog, skus_by_category
from synth.config import load_config


def test_build_catalog_creates_one_sku_per_item():
    config = load_config("config/synth_schema.yaml")
    catalog = build_catalog(config)
    assert len(catalog) == sum(len(c.items) for c in config.categories)


def test_build_catalog_is_deterministic_and_seed_independent():
    config = load_config("config/synth_schema.yaml")
    a = build_catalog(config)
    b = build_catalog(config)
    assert {k: (v.regular_unit_price_rub, v.unit_cost_rub) for k, v in a.items()} == {
        k: (v.regular_unit_price_rub, v.unit_cost_rub) for k, v in b.items()
    }


def test_items_within_a_category_have_different_prices():
    config = load_config("config/synth_schema.yaml")
    catalog = build_catalog(config)
    by_cat = skus_by_category(catalog)
    dairy = by_cat["молочные продукты и яйца"]
    prices = {sku.regular_unit_price_rub for sku in dairy}
    assert len(prices) > 1, "every item in a category had the same price — jitter isn't working"


def test_cost_never_exceeds_price_at_the_cheapest_chain():
    config = load_config("config/synth_schema.yaml")
    catalog = build_catalog(config)
    min_multiplier = min(c.price_multiplier for c in config.chains)
    for sku in catalog.values():
        cheapest_price = round(sku.regular_unit_price_rub * min_multiplier, 2)
        assert cheapest_price >= sku.unit_cost_rub - 0.01, (
            f"{sku.sku_id} ({sku.category}/{sku.item}): cheapest-chain price {cheapest_price} "
            f"below cost {sku.unit_cost_rub}"
        )


def test_categories_have_different_price_tiers():
    config = load_config("config/synth_schema.yaml")
    catalog = build_catalog(config)
    by_cat = skus_by_category(catalog)
    salt_category_mean = sum(s.regular_unit_price_rub for s in by_cat["бакалея"]) / len(by_cat["бакалея"])
    alcohol_mean = sum(s.regular_unit_price_rub for s in by_cat["алкоголь"]) / len(by_cat["алкоголь"])
    assert alcohol_mean > salt_category_mean * 2
