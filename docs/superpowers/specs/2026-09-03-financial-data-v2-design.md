# Synthetic data v2: financial fields, realistic behavior, leakage-safe benchmark

Date: 2026-09-03. Extends the v1 generator (`2026-09-03-synthetic-data-schema-design.md`,
`2026-09-03-synthetic-data-chains-segments-design.md`). Implemented directly
per an exhaustive user spec (not brainstormed) — this doc records the
resulting design and the decisions made while implementing it, for
traceability.

## What changed and why

v1 priced every receipt line from a flat range around `avg_receipt_total_rub`
— salt, milk, beef, and champagne all drew from the same distribution, and
there was no cost/margin model, no way to compute savings, and every user
shared one visit-frequency/basket-size distribution regardless of segment.
v2 replaces this with:

1. **A stable per-SKU price catalog** (`synth/catalog.py`) — one entry per
   `(category, item)`, with its own `regular_unit_price_rub` and
   `unit_cost_rub`, both driven by `config/synth_schema.yaml`'s new
   `category_economics` block (`base_price_rub`, `price_jitter_pct`,
   `margin_pct`, `popularity_weight` per category). The catalog is built
   deterministically from catalog position, independent of any run seed —
   prices are a property of the (frozen) config, not of which generation
   run is asking.

2. **Full per-line financial fields** (`ReceiptLine`): `sku_id`,
   `regular_unit_price_rub`, `paid_unit_price_rub`, `discount_pct`,
   `savings_rub`, `unit_cost_rub`, `gross_margin_rub`, plus the existing
   `qty`/`on_promo`. Receipt-level rollups: `regular_total_rub`,
   `total_rub` (paid), `savings_rub`, `gross_margin_rub`.

3. **Cost anchored to the cheapest chain's price, not the reference price**
   — a bug found and fixed during this implementation. Chain `price_multiplier`
   (Чижик 0.75x, Пятёрочка 1.0x, Перекрёсток 1.25x) multiplies the catalog's
   reference price at generation time. If `unit_cost_rub` were derived from
   the reference (1.0x) price, any category whose `margin_pct` was below
   `1 - 0.75 = 0.25` would have Чижик selling BELOW cost before any promo
   even applied — several categories had margins under 25%. Fixed by
   deriving cost from `reference_price * min(chain.price_multiplier for all
   chains) * (1 - margin_pct)`, so the cheapest chain's price is guaranteed
   at or above cost regardless of margin_pct, and richer-margin chains
   naturally show fatter margins. Caught by the validator's "no negative
   margin" check on the first full-scale run, not by unit tests at small n —
   worth remembering if this model is extended further.

4. **Realistic behavioral distributions**, driven by per-user latent state
   generated in `synth/simulation_truth.py` (see below) rather than one
   shared global rate:
   - Individual visit frequency (`baseline_visits_28d`), scaled by
     `segment.visit_frequency_multiplier` (config) and a per-user
     `lognormvariate(0, 0.3)` factor.
   - Basket size drawn from a right-skewed weight table (mode 1-2, thin
     tail to 8), scaled by `segment.basket_size_multiplier` × a family-size
     factor (`0.7 + 0.15*family_size`).
   - `qty` drawn 1/2/3/4 with weights `[0.55, 0.28, 0.12, 0.05]`.
   - Purchase days sampled without replacement first (so the large
     majority of users never buy twice in one day), with an 8%-per-user
     chance of exactly one same-day second receipt — keeps the aggregate
     multi-receipt-day rate near the low single digits (measured 0.11% at
     n=10,000) without being artificially exactly zero.
   - Category draws outside the habitual list are weighted by
     `category_economics.popularity_weight`, not uniform.

5. **Observable/hidden split.** `population()` returns
   `(observable_users, simulation_truth_records)`. Only the former is
   written to `data/v2/population_1k-10k.jsonl`; the latter (
   `baseline_visits_28d`, `frequency_headroom`, `promo_sensitivity`,
   `challenge_sensitivity`, `reward_sensitivity`, `app_open_probability`,
   `fatigue_sensitivity`, `category_affinity`, `repurchase_intervals`,
   `forbidden_categories`, `response_noise_seed`) goes to
   `data/v2/simulation_truth.jsonl`, kept separate so a recommender never
   sees it. `synth/validate.py` scans the observable output for every
   hidden field name and fails the run if any leak through.

6. **Temporal split, leakage-safe derived features.**
   `config.temporal_split` fixes train (2026-06-03 to 2026-08-03) and
   holdout (2026-08-04 to 2026-08-31) — the same 90-day window the v1
   calibration already used, now with an explicit boundary. The observable
   `habitual_categories` field is no longer the raw generation-time bias
   list; `synth/features.py::compute_observable_habitual_categories`
   recomputes it from TRAIN-period receipts only (top-5 categories by
   frequency), so it's a genuinely derived, leakage-safe signal rather than
   the internal generative parameter leaking straight through. The hidden
   generative bias itself still exists (as `category_affinity` in
   simulation_truth).

7. **De-trivialized reference-profile benchmark.** The old 3
   `persona_archetype`s (crisp, non-overlapping stats, sequential
   `ref_NNN` IDs, `habitual_categories=None` as a de facto label for
   `one_off_no_pattern`) are replaced with 5 noisy, overlapping
   `generation_class`es (`bakes_on_weekends`, `promo_hunter`,
   `one_off_no_pattern`, `ambiguous_mixed`, `already_optimal_no_challenge`),
   each drawing its parameters from a range instead of a fixed value, none
   ever emitting `null` for `habitual_categories`, plus two classes whose
   correct benchmark answer is "don't issue a challenge"
   (`abstain_is_correct: true`). IDs are deterministic UUID4s
   (`synth/reference_profiles.py::_deterministic_uuid`), and class
   assignment is round-robin-then-shuffled so neither the ID nor list
   position reveals the class. The blind export additionally re-shuffles
   independently and strips `generation_class` + `_simulation_truth`.

8. **Ground-truth answer key for hit-rate evaluation.**
   `build_answer_key()` heuristically drafts, per reference profile:
   `acceptable_challenges`, `acceptable_target_categories` (filtered to
   exclude `forbidden_categories` — a second bug fixed during
   implementation: the first draft let a profile's habitual `алкоголь`
   purchases leak into its own acceptable-target list, contradicting the
   same entry's forbidden list), `acceptable_mechanics`,
   `forbidden_categories`, `max_reward_rub` (from the profile's own
   observed mean line margin), `relevance_reason`, `abstain_is_correct`.
   Every entry is marked `draft: true`. `write_answer_key_csv` produces a
   human-editable template (`confirmed_by`, `corrected_challenge`, `notes`
   columns) for a teammate other than the generator's author to confirm or
   correct — the same anti-circularity discipline as the blind-labeling
   process this project already uses.

9. **Automatic validator** (`synth/validate.py`, run via
   `python -m synth.validate`) — 23 checks across uniqueness, JSONL
   validity, financial-formula reconciliation, no negative
   price/cost/margin, `paid <= regular`, promo-flag consistency,
   multi-receipt-day rate, qty/basket-size distribution shape, category
   price spread, segment frequency spread, hidden-field leakage (both
   files), train-only feature derivation, and the answer-key
   forbidden/acceptable contradiction check. Produces a markdown report.

## Config additions

- `config/synth_schema.yaml`: `forbidden_categories` (`алкоголь` —
  regulated/age-restricted; `детское питание` — sensitive, excluded by
  choice not law), `temporal_split`, `category_economics` (22 entries).
  `segments[*].price_multiplier` removed, replaced by
  `visit_frequency_multiplier` + `basket_size_multiplier` — segments now
  differ on shopping behavior, not on the price charged for the same SKU
  (chains still carry `price_multiplier`, which is the real-world-defensible
  axis: different stores charging different prices for the same product).
  Version bumped `0.3.0` → `0.4.0`.

## Known simplifications (not fixed, flagged for whoever builds on this)

- `repurchase_intervals` in simulation_truth is drawn directly (`uniform(3,
  21)` days per habitual category), not derived by analyzing actual
  generated purchase gaps — a generative parameter, not a measured
  descriptive statistic. Treat it as an approximate hidden "intent," not an
  exact property of the receipts.
- `max_reward_rub` in the answer key is a coarse heuristic
  (`4 × mean observed line margin`), not a proper unit-economics
  calculation tied to H4's reward-vs-margin rule (H4 itself is still
  unowned per CONTEXT_PACK.md §8).
- The draft answer key's `acceptable_challenges` text is templated per
  generation class, not per-individual profile nuance — expected to be
  edited by the human reviewer via the CSV, per its `draft: true` marker.
- `data/v1/` (the pre-financial-fields generation) is kept for reference
  but is not schema-compatible with v2 — anything consuming this data
  should point at `data/v2/`.
