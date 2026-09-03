from __future__ import annotations

import random
from dataclasses import dataclass

from synth.config import SynthConfig


@dataclass
class SKU:
    sku_id: str
    category: str
    item: str
    regular_unit_price_rub: float
    unit_cost_rub: float


def build_catalog(config: SynthConfig) -> dict[str, SKU]:
    """Build a stable SKU catalog: one entry per (category, item) in the
    frozen config, each with its own regular price and cost.

    Deliberately independent of any generation `seed` — the catalog (what
    a SKU costs) is a property of the store, not of which synthetic run is
    generating receipts, so the same config always produces the same
    catalog. Per-SKU price jitter is seeded from the SKU's fixed catalog
    position (its index in category/item iteration order), not from a
    run seed — this is what makes prices differ item-to-item within a
    category (previously every item in a category drew from the same
    price range) while staying identical across separate generation runs.

    `regular_unit_price_rub` is the reference (chain-multiplier=1.0) price;
    `synth/receipts.py` multiplies it by a chain's own `price_multiplier`
    at generation time. `unit_cost_rub` is anchored to the CHEAPEST chain's
    price for that SKU (not the reference price) — margin_pct is a target
    margin at the lowest price any chain actually charges, so a discount
    chain's price is guaranteed to stay at or above cost. Anchoring cost to
    the reference price instead would make margin_pct*base < (1 -
    cheapest_chain_multiplier) push the cheapest chain's price below cost
    for every category whose margin is thinner than that chain's discount
    — which was a real bug here (Чижик at 0.75x price undercut cost on
    categories with margin_pct < 0.25, silently forcing the sell-at-cost
    floor to price ABOVE the chain's own regular price).
    """
    econ_by_category = {e.category: e for e in config.category_economics}
    min_chain_multiplier = min(c.price_multiplier for c in config.chains) if config.chains else 1.0
    catalog: dict[str, SKU] = {}

    idx = 0
    for cat in config.categories:
        econ = econ_by_category[cat.name]
        for item in cat.items:
            sku_id = f"sku_{idx:04d}"
            jitter_rng = random.Random(idx)
            jitter = jitter_rng.uniform(-econ.price_jitter_pct, econ.price_jitter_pct)
            regular_price = round(econ.base_price_rub * (1 + jitter), 2)
            cheapest_price = regular_price * min_chain_multiplier
            unit_cost = round(cheapest_price * (1 - econ.margin_pct), 2)
            catalog[sku_id] = SKU(
                sku_id=sku_id,
                category=cat.name,
                item=item,
                regular_unit_price_rub=regular_price,
                unit_cost_rub=unit_cost,
            )
            idx += 1

    return catalog


def skus_by_category(catalog: dict[str, SKU]) -> dict[str, list[SKU]]:
    result: dict[str, list[SKU]] = {}
    for sku in catalog.values():
        result.setdefault(sku.category, []).append(sku)
    return result
