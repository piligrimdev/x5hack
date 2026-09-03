# Synthetic data: chains + demographic segments — design

Date: 2026-09-03
Owner: Дима
Status: approved, ready for implementation plan
Extends: `2026-09-03-synthetic-data-schema-design.md` (base schema) and its
`0.2.0` calibration (`2026-09-03-synthetic-data-math-notes.md` §6)

## Purpose

The generator currently produces one undifferentiated X5 population. This
extension splits that population across X5's three actual banners
(Пятёрочка, Перекрёсток, Чижик) and five proprietary customer
life-stage/demographic segments (Молодёжь, Взрослые с вредными
привычками, Взрослые с детьми до 3х лет, Зрелые, Старшие), so generated
users carry a chain + segment identity and their receipt totals are
calibrated per chain×segment instead of one flat average.

The five segments and their per-chain distribution (mobile-app users only
— "гости"/guests are out of scope, per instruction) are proprietary/case
data, supplied directly by the user, not derived from any public source:

| Segment | Пятёрочка (ТС5) | Перекрёсток (ТСХ) | Чижик (ТСЧ) |
|---|---|---|---|
| Молодёжь | 37% | 31% | 27% |
| Взрослые с вредными привычками | 5% | 3% | 4% |
| Взрослые с детьми до 3х лет | 26% | 26% | 28% |
| Зрелые | 21% | 32% | 24% |
| Старшие | 11% | 9% | 18% |

## Entities

- **Chain** — `name` (Пятёрочка / Перекрёсток / Чижик), `price_multiplier`,
  `segment_weights` (the table above, one row per chain).
- **Segment** — `name` (the five above), `price_multiplier`.
- **User** gains two fields: `chain`, `segment`. Independent of
  `household_id`/`district_id` — chain/segment is a shopping-habit axis,
  not a geography axis.

No new grocery-item categories and no per-segment/per-chain category
vocabulary — explicitly out of scope for this extension (see below).

## Sourcing: what's real, what's assumed

Same discipline as the base calibration (math-notes §6): every number below
is labeled by where it came from, not presented as uniformly authoritative.

**Real, sourced:**
- Chain business-format descriptions (Пятёрочка = "у дома"/convenience,
  Перекрёсток = supermarket, Чижик = hard discounter) — X5's own public
  positioning.
- Segment price multipliers for **Зрелые** (≈1.4, close to Rosstat's
  measured consumption peak at ages 35-39: 53,000₽/month total consumption
  vs. a 32,500₽/month population average = 1.63×, `Зрелые` set slightly
  below the exact peak since it likely spans a wider age band) and
  **Старшие** (≈0.78, derived from pensioner food spend ≈40-50% of the
  average 27,100₽/month pension ≈ 10,800-13,500₽/month, vs. the ≈15,300₽/month
  population-average food spend) — Rosstat 2025 consumer-expenditure
  releases.

**Estimated / no public source found (explicitly flagged, not silently
treated as equally solid):**
- **Молодёжь** ≈0.75 — no Rosstat breakdown matches this bracket
  precisely; reasoned as below-peak/early-career.
- **Взрослые с детьми до 3х лет** ≈1.0 — Rosstat publishes
  household-with-children data for children under 16, not under 3, and at
  household level, not per-capita food spend; no usable figure found, kept
  neutral.
- **Взрослые с вредными привычками** ≈1.0 — not a Rosstat category at
  all; no public data exists for this proprietary label, kept neutral.
- **Chain price multipliers** (Чижик ≈0.75, Пятёрочка =1.0 baseline,
  Перекрёсток ≈1.25) — no public per-banner average-check comparison was
  found; these are directional estimates from the discounter/convenience/
  supermarket format difference, not measured numbers.
- **Chain population share: 33/33/33** — a deliberate user choice, not a
  claim about real customer counts (X5's real 2025 net-sales split is
  ≈80/13/7 normalized across the three banners; the user chose equal
  thirds instead, e.g. for balanced per-chain evaluation coverage).

## Calibration formula

```
avg_receipt_total_rub(user) = base_avg_receipt_total_rub
                               × segment.price_multiplier
                               × chain.price_multiplier
```

`base_avg_receipt_total_rub` is the existing `0.2.0` config value (710₽).
`purchases_per_month_mean`/`stddev` are **not** scaled by segment or chain
— they stay the shared base for every user. Rationale: the only real data
available (Rosstat age-bracket and pension figures) measures *total*
monthly spend, which is check-size × frequency combined; splitting that
ratio between "buys more often" and "buys bigger baskets" would require
data this project doesn't have. Applying the multiplier to check size
alone already scales total monthly spend correctly without inventing a
frequency effect that isn't supported by any source.

## Assignment algorithm

For each generated user: draw `chain` uniformly (1/3 each, per the user's
choice above), then draw `segment` weighted by *that chain's*
`segment_weights` row. Both draws use their own seed stream, consistent
with the existing seed-hygiene design (math-notes §1) — no reuse of a
seed already claimed by habitual-category or receipt generation.

## Scope

Applies to both `population()` and `reference_profiles()` — every
generated user or reference profile carries `chain` + `segment` alongside
whatever else it already has (habitual categories, receipts, and, for
reference profiles, `persona_archetype`). The archetype and the
chain/segment identity are orthogonal: a reference profile still gets an
archetype-driven purchase pattern (bakes_on_weekends etc.) *and* a
chain/segment identity; the archetype doesn't determine or get determined
by which chain/segment it's assigned to.

**Out of scope for this extension:**
- Category-vocabulary or category-preference differences by chain or
  segment (all users still draw from the same 22-category, 132-item
  vocabulary from `config/synth_schema.yaml`).
- Frequency (`purchases_per_month`) varying by chain or segment (see
  Calibration formula above).
- Any chain- or segment-specific channel (`offline_share`) difference —
  stays the shared 0.8 for everyone.
