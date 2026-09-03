from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta

from synth.catalog import SKU
from synth.config import SynthConfig

_BASKET_SIZES = [1, 2, 3, 4, 5, 6, 7, 8]
_BASKET_WEIGHTS = [30, 25, 18, 12, 8, 4, 2, 1]  # right-skewed: mode at 1-2, long thin tail to 8
_QTY_VALUES = [1, 2, 3, 4]
_QTY_WEIGHTS = [0.55, 0.28, 0.12, 0.05]  # qty=1 > qty=2 > qty>=3, by construction


@dataclass
class ReceiptLine:
    sku_id: str
    category: str
    item: str
    regular_unit_price_rub: float
    paid_unit_price_rub: float
    discount_pct: float
    savings_rub: float
    unit_cost_rub: float
    gross_margin_rub: float
    qty: int
    on_promo: bool


@dataclass
class Receipt:
    receipt_id: str
    user_id: str
    purchase_date: str  # ISO date
    channel: str  # "offline" or "online"
    lines: list[ReceiptLine]
    regular_total_rub: float
    total_rub: float  # paid total
    savings_rub: float
    gross_margin_rub: float


def _make_line(
    rng: random.Random, sku: SKU, price_multiplier: float, promo_affinity: float
) -> ReceiptLine:
    price_jitter = rng.uniform(-0.05, 0.05)  # moderate purchase-to-purchase price movement
    regular_unit_price = round(sku.regular_unit_price_rub * price_multiplier * (1 + price_jitter), 2)

    on_promo = rng.random() < promo_affinity
    if on_promo:
        discount_frac = rng.uniform(0.10, 0.30)
        paid_unit_price = round(regular_unit_price * (1 - discount_frac), 2)
    else:
        paid_unit_price = regular_unit_price

    unit_cost = sku.unit_cost_rub
    paid_unit_price = max(paid_unit_price, unit_cost)  # never sell below cost

    discount_pct = round((1 - paid_unit_price / regular_unit_price) * 100, 2) if regular_unit_price else 0.0
    qty = rng.choices(_QTY_VALUES, weights=_QTY_WEIGHTS, k=1)[0]
    savings_rub = round((regular_unit_price - paid_unit_price) * qty, 2)
    gross_margin_rub = round((paid_unit_price - unit_cost) * qty, 2)

    return ReceiptLine(
        sku_id=sku.sku_id,
        category=sku.category,
        item=sku.item,
        regular_unit_price_rub=regular_unit_price,
        paid_unit_price_rub=paid_unit_price,
        discount_pct=discount_pct,
        savings_rub=savings_rub,
        unit_cost_rub=unit_cost,
        gross_margin_rub=gross_margin_rub,
        qty=qty,
        on_promo=on_promo,
    )


def generate_receipts_for_user(
    user_id: str,
    config: SynthConfig,
    catalog: dict[str, SKU],
    skus_by_category: dict[str, list[SKU]],
    seed: int,
    habitual_categories: list[str] | None = None,
    habitual_bias_strength: float = 0.8,
    promo_affinity: float = 0.15,
    weekend_bias: float = 0.0,
    price_multiplier: float = 1.0,
    frequency_multiplier: float = 1.0,
    basket_size_multiplier: float = 1.0,
) -> list[Receipt]:
    """Generate one user's receipt history over the full train+holdout window
    (`config.temporal_split`, 90 days by default: 2026-06-03 to 2026-08-31).

    `price_multiplier` is the CHAIN's price multiplier only — segments no
    longer scale price (see config comment); segment behavior instead
    scales `frequency_multiplier`/`basket_size_multiplier`. Both are fully
    composed by the caller (segment multiplier × per-user latent factor,
    plus family_size for basket size — see `synth/simulation_truth.py`)
    before being passed in; this function treats them as the final
    effective multiplier, not a base to combine with its own randomness.

    `habitual_categories`, if given, are drawn from with probability
    `habitual_bias_strength` per line; the rest of the time a category is
    drawn from ALL categories weighted by `category_economics.popularity_weight`
    (not uniformly — some categories are just more commonly bought).

    Target receipt count is `effective_rate_28d` scaled to the window, with
    NO hard cap at `window_days`. When the target fits within the window
    (the common case for every segment/user at this config's calibration),
    days are sampled WITHOUT replacement — zero multi-receipt days, exactly
    like a simple "one shopping trip, one day" model. Only when the target
    genuinely exceeds the number of days available (a small minority: very
    high per-user frequency, or `already_optimal_no_challenge`'s explicit
    override — see `synth/reference_profiles.py`) does every day get one
    receipt AND the excess get distributed across randomly re-picked days
    (with replacement), so those receipts aren't silently thrown away or
    artificially clamped to `window_days` — the two states (a normal user
    who fits in the window vs. a genuinely saturated one who doesn't) stay
    distinguishable in the resulting receipt count instead of both landing
    on the same day-count ceiling.

    An earlier version used `Poisson(per_day_rate)` receipts on every day
    unconditionally — abandoned because at this config's calibration
    (per_day_rate ~0.6-0.85 for most users), that gives every user a
    17-30% chance of a two-receipt day, blowing well past the "≤5% of
    purchase days have multiple receipts" requirement; the hybrid above
    keeps that near 0% for the common case and only allows overflow for
    the minority that actually needs it.
    """
    rng = random.Random(seed)
    cal = config.calibration
    all_categories = [c.name for c in config.categories]
    popularity_by_category = {e.category: e.popularity_weight for e in config.category_economics}
    popularity_weights = [popularity_by_category[c] for c in all_categories]

    ts = config.temporal_split
    window_start = ts.train_start
    window_days = ts.window_days

    base_rate_28d = cal.purchases_per_month_mean * (28 / 30)
    effective_rate_28d = min(max(base_rate_28d * frequency_multiplier, 2.0), 40.0)
    target_receipts = max(1, round(effective_rate_28d * window_days / 28))

    if target_receipts <= window_days:
        day_offsets = rng.sample(range(window_days), k=target_receipts)
    else:
        day_offsets = list(range(window_days))
        overflow = target_receipts - window_days
        day_offsets.extend(rng.choices(range(window_days), k=overflow))

    receipts: list[Receipt] = []
    for i, offset in enumerate(day_offsets):
        purchase_date = window_start + timedelta(days=offset)
        if weekend_bias > 0.0 and rng.random() < weekend_bias:
            for _ in range(5):
                if purchase_date.weekday() >= 5:  # Saturday=5, Sunday=6
                    break
                offset = rng.randint(0, window_days - 1)
                purchase_date = window_start + timedelta(days=offset)

        channel = "offline" if rng.random() < cal.offline_share else "online"

        raw_basket = rng.choices(_BASKET_SIZES, weights=_BASKET_WEIGHTS, k=1)[0]
        n_lines = max(1, round(raw_basket * basket_size_multiplier))

        lines: list[ReceiptLine] = []
        for _ in range(n_lines):
            if habitual_categories and rng.random() < habitual_bias_strength:
                category = rng.choice(habitual_categories)
            else:
                category = rng.choices(all_categories, weights=popularity_weights, k=1)[0]
            sku = rng.choice(skus_by_category[category])
            lines.append(_make_line(rng, sku, price_multiplier, promo_affinity))

        regular_total = round(sum(l.regular_unit_price_rub * l.qty for l in lines), 2)
        paid_total = round(sum(l.paid_unit_price_rub * l.qty for l in lines), 2)
        savings_total = round(regular_total - paid_total, 2)
        margin_total = round(sum(l.gross_margin_rub for l in lines), 2)

        receipts.append(
            Receipt(
                receipt_id=f"r_{user_id}_{i:04d}",
                user_id=user_id,
                purchase_date=purchase_date.isoformat(),
                channel=channel,
                lines=lines,
                regular_total_rub=regular_total,
                total_rub=paid_total,
                savings_rub=savings_total,
                gross_margin_rub=margin_total,
            )
        )

    receipts.sort(key=lambda r: r.purchase_date)
    return receipts
