# Synthetic data schema — design

Date: 2026-09-03
Owner: Дима
Status: approved, ready for implementation plan

## Purpose

Freeze the synthetic-data schema and generation approach before any LLM
recommendation logic (H2/H3) is tuned against it. This is the anti-circularity
guard from `CONTEXT_PACK.md` §8: the same person (Дима) writes both the
recommendation logic and the data it's evaluated on, so the data generation
parameters must be locked first and the "true" expected outcomes for the
reference profiles must be labeled by someone else (Паша/Влад), blind to the
model's output.

One schema and one generator serve two different outputs:

1. A population of 1,000–10,000 synthetic users for the H1/H4 effect
   simulation (kanban task: "Прогнать симуляцию на 1–10 тыс.").
2. 30–50 hand-steered reference profiles for the H2 hit-rate evaluation
   (≥70% target from CONTEXT_PACK §3).

## Entities

- **User** — `user_id`, `household_id`, `district_id`, registration date.
- **Household** — `household_id`, `district_id`, family size. Not used by any
  mechanic yet (family-size purchase sharing is backlog item B4-adjacent in
  CONTEXT_PACK), but modeled now since the rating mechanic (H-rating) needs
  household-level aggregation and retrofitting it later is more disruptive
  than including the field now.
- **District** — `district_id`, a synthetic name. No real geodata — this
  satisfies the CONTEXT_PACK §3 fail-condition ("рейтинг требует ФИО/адреса").
- **Category** — ~30–40 grocery categories (dairy, produce, dry goods, ...).
- **Item** — a small vocabulary of 5–10 concrete items per category (e.g.
  "сметана", "свёкла" under dairy/produce), not a full retail SKU catalog.
  This is the resolution to a tradeoff surfaced during design: pure
  category-level data cannot support the H2 example challenge from
  CONTEXT_PACK ("купи недостающие ингредиенты для блюда X") because
  categories are too coarse to know a specific ingredient is missing. A full
  SKU catalog is unnecessary generation effort for a hackathon. A small
  per-category item vocabulary is the minimum that makes "missing
  ingredient" challenges constructible.
- **Receipt** — `receipt_id`, `user_id`, date, channel (offline/online,
  skewed toward offline per CONTEXT_PACK §7 answer 6), line items
  `(item, category, price, qty)`, total.
- **ReferenceProfile** (30–50 set only) — a User wrapper with an explicit
  `persona_archetype` field (e.g. "bakes on weekends", "buys mostly on
  promotion", "one-off shopper with no pattern"). The archetype drives which
  pattern the generator embeds into that profile's receipts, so there is a
  concrete expected pattern for Паша/Влад to label against — pure randomness
  would give them nothing to label.

## Generation

Single Python generator, two entry points sharing the same schema and item
vocabulary:

- `population(n, seed)` — randomized generation of `n` users with 3 months of
  receipt history each, for the 1–10k simulation.
- `reference_profiles(archetypes, seed)` — 30–50 profiles where the purchase
  pattern deterministically follows the given archetype rather than pure
  randomness.

**History depth:** 3 months per user. Long enough to show recurring patterns
(weekly milk + Friday snacks) and compute frequency/savings without
generating more data than a 5–6 day hackathon needs.

## Calibration

Reasonable assumptions plus public retail data (not real X5 data — none is
available per CONTEXT_PACK §3/§4). Calibration constants (avg receipt total,
purchase frequency ranges) live in the frozen config with their source noted
inline, so they can be corrected later without touching the generator code —
CONTEXT_PACK §7 notes the case owner may or may not provide real aggregates.

## Format and freeze mechanism

- `config/synth_schema.yaml` — categories, item vocabulary, price/frequency
  ranges, calibration assumptions and their source. Versioned with a date and
  short changelog entry per change. Frozen once H2/H3 prompt/logic tuning
  starts; changes after that point require an explicit decision, not a silent
  edit, because they would undermine the hit-rate measurement.
- Datasets as JSON/JSONL: `data/population_1k-10k.jsonl`,
  `data/reference_profiles.json`.
- No names or addresses anywhere — only synthetic IDs.

## Out of scope

- Real SKU-level retail catalog.
- Household purchase-list sharing (backlog, not a current mechanic).
- Antifraud signal fields (card-reuse across accounts) — belongs to H6,
  which is unowned and not yet scoped for the schema.
