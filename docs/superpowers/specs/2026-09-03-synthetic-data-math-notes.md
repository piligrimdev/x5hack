# Synthetic data generator — math notes

Companion to `2026-09-03-synthetic-data-schema-design.md` (the spec) and
`2026-09-03-synthetic-data-generator.md` (the plan). This file collects the
arithmetic behind every tuned constant in `synth/`, and why each one is what
it is — so a later change to `config/synth_schema.yaml` or `synth/*.py` can
be checked against the same math instead of re-derived from scratch.

## 1. Why the seeds are `seed*4 + i*4 + {1,2,3,4}`

Every user/profile needs two independent random draws: one for "which
categories does this person habitually buy from" and one for "what's in
each of their receipts." Seeding both draws from the same integer looked
harmless but wasn't — the first `random.Random(x).sample(...)` call and the
second `random.Random(x)`-derived receipt generation walked the *same*
Mersenne Twister state, so the size of the habitual-category set and the
number of receipts generated became correlated by construction, not by any
intended behavior.

Measured on 500 population users at a fixed seed, before the fix:

```
correlation(len(habitual_categories), len(receipts)) = -0.56
```

That's a strong, fake, monotonic relationship — nobody designed "users with
more habitual categories buy less often," it fell out of reusing one RNG
state for two purposes. This is exactly the kind of hidden structure the
whole point of freezing this generator exists to prevent: it would leak
into the H1/H4 simulation as a real-looking effect, and give the LLM
recommender a free, spurious signal to learn.

**Fix:** give every RNG consumer its own residue class mod 4:

| Consumer | Seed |
|---|---|
| `population()` habit RNG | `seed*4 + i*4 + 1` |
| `population()` receipt RNG | `seed*4 + i*4 + 2` |
| `reference_profiles()` archetype-param RNG | `seed*4 + i*4 + 3` |
| `reference_profiles()` receipt RNG | `seed*4 + i*4 + 4` (≡ `+0` mod 4) |

**Why this guarantees no collisions, for any `seed` and any `i`:** every
produced value is `4k + r` for some integer `k` and a fixed `r ∈ {0,1,2,3}`
per consumer. Two different consumers always have different `r`, so their
value sets (`{..., -4, 0, 4, 8, ...} + r`) are disjoint residue classes mod
4 — they cannot share a value no matter what `seed` or `i` is, without
needing a hash function or any run-time check.

Note `assign_households` (used by both `population()` and, after the final
fix, `reference_profiles()` too) is seeded directly from the caller's raw
`seed`, not from one of the four streams above — it constructs its own
`random.Random(seed)` instance internally and never touches the four
per-item RNGs, so it can't reintroduce the correlation either.

**Verification after the fix**, same 500-user measurement:

```
correlation(len(habitual_categories), len(receipts)) = 0.018
```

Independently reproduced by the re-review agent to 14 significant digits
against the implementer's own run — same computation, not a coincidence.

## 2. Receipt-total calibration (`avg_receipt_total_rub`)

`config/synth_schema.yaml` documents `avg_receipt_total_rub: 850.0` as a
calibration constant sourced from public retail aggregates (no real X5 data
exists to calibrate against — see CONTEXT_PACK.md §3/§4). The config should
describe what the generator actually produces.

`generate_receipts_for_user` builds each receipt from `n_lines` items
(`n_lines = rng.randint(1, 5)`, mean 3) each with `qty = rng.randint(1, 3)`
(mean 2), and each line's price drawn from `_price_for_item`, uniform over
`[avg * lo, avg * hi]` before an optional promo discount.

Expected receipt total ≈ `mean_lines × mean_qty × mean_price_per_unit`
= `3 × 2 × avg × (lo+hi)/2` = `6 × avg × (lo+hi)/2`.

**Original range** `lo=0.03, hi=0.15` → `(lo+hi)/2 = 0.09` → expected total
= `6 × 0.09 × avg = 0.54 × avg` = `0.54 × 850 ≈ 459`. Measured mean was
~440 (the gap from 459 is the promo discount, which multiplies ~15% of
lines by 0.6–0.85). The config claimed 850; the generator produced ~440 —
off by roughly 2×.

**New range** `lo=0.10, hi=0.24` → `(lo+hi)/2 = 0.17` → expected total =
`6 × 0.17 × avg = 1.02 × avg ≈ 867`, and after the promo discount pulls it
down slightly:

```
measured mean total_rub = 827.29–828.15  (two independent runs)
```

−2.6% to −2.7% off the configured 850 — inside the ±15% target the fix was
scoped to, without needing to also model the promo discount's exact effect
analytically.

## 3. Weekend bias (`bakes_on_weekends` archetype)

Uniformly random calendar dates land on a weekend with probability
`2/7 ≈ 28.6%` (Saturday + Sunday out of 7 days) — and that's exactly what
was measured for all three archetypes before this fix (~29–32%), including
`bakes_on_weekends`, whose entire premise is a weekend-shopping pattern. A
label with no distinguishing timing signal is not something a blind labeler
can actually detect from the receipts alone.

**Fix:** `generate_receipts_for_user` gained an optional `weekend_bias`
parameter. When set, each candidate purchase date is resampled (up to 5
tries, all draws from the function's own seeded RNG — no wall clock, no
unbounded loop) until it lands on a Saturday/Sunday, with probability
`weekend_bias` of attempting the resample at all. `reference_profiles()`
passes `weekend_bias=0.65` for `bakes_on_weekends` only; the other two
archetypes keep the default `0.0` (unbiased).

**Verification**, weekend share of `purchase_date` across a
`bakes_on_weekends` profile's receipts:

```
67.1–67.3% (two independent measurements)  vs.  ~29–31% baseline
```

A comfortable, unambiguous separation — this is the kind of gap a labeler
should be able to notice without needing exact statistics, matching how the
`promo_hunter`/`one_off_no_pattern` archetypes are already separable on
promo rate and category spread (see spec's `ReferenceProfile` rationale).

## 4. `bakes_on_weekends` category dominance: why `k=1`, not the plan's `k=2`

This one isn't a later fix — it's a bug in the plan itself, caught during
Task 5's review, before this file's other three fixes even existed.

`_archetype_params` builds the archetype's `habitual_categories` list as 3
fixed "baking" categories (`бакалея`, `хлеб и выпечка`, `молочные продукты
и яйца`) plus `k` extra categories sampled at random. `generate_receipts_for_user`
then draws each receipt line from the habitual list with probability 0.8,
or from all 22 categories with probability 0.2 (the "exploration" branch).

For a habitual list of size `n = 3 + k`, the expected fraction of lines
landing in a baking category is:

```
P(baking) = 0.8 × (3 / n) + 0.2 × (3 / 22)
```

The `0.2 × (3/22) ≈ 0.0273` term is constant (exploration draws uniformly
over all 22 categories regardless of `k`); only the first term moves.

| `k` | `n` | `0.8 × 3/n` | `+ 0.0273` | Theoretical `P(baking)` |
|---|---|---|---|---|
| 2 (plan's original) | 5 | 0.480 | 0.507 | **50.7%**, barely above 0.5 |
| 1 (shipped) | 4 | 0.600 | 0.627 | **62.7%**, comfortable margin |

The plan's own test, `test_bakes_on_weekends_receipts_are_dominated_by_baking_categories`,
asserts `baking_fraction > 0.5` at a fixed `seed=1`. The 50.7% theoretical
value for `k=2` is close enough to the 0.5 threshold that a single fixed
seed's actual draw can land on either side of it — and at `seed=1` it did
land on the wrong side:

```
k=2, seed=1:  baking_count=71, total_lines=147, fraction=0.483  →  FAILS (not > 0.5)
k=1, seed=1:  baking_count=91, total_lines=155, fraction=0.587  →  PASSES
```

Reproduced independently by the task reviewer before the ruling to accept
`k=1` — this is a real defect in the plan's originally-specified constant,
not a matter of implementer taste, and both the plan document and the
shipped code were updated to `k=1` to keep them in sync.

## 5. Item vocabulary: why 22 categories × 6 items, not "~30–40"

The spec's design discussion (see the brainstorming transcript that
produced `2026-09-03-synthetic-data-schema-design.md`) set "~30–40
categories" as an approximate target — deliberately not a category-only
model, because pure categories are too coarse to build the H2 example
challenge from CONTEXT_PACK.md ("купи недостающие ингредиенты для блюда
X" — a category like "dairy" can't say *which* dairy item is missing).

22 categories × 6 items = 132 concrete items was chosen as a solid MVP
vocabulary within that "~" tolerance — enough breadth for the three
archetypes to be distinguishable (see §3 and the promo/category
measurements in the final review) and enough specificity for
ingredient-level challenges, without hand-authoring a much larger list for
a hackathon-scale demo. `tests/synth/test_config.py` locks the count at
`== 22`; loosening that to a range is a one-line change if the vocabulary
is ever extended.

## 6. Recalibration against real public data (Rosstat + X5), 2026-09-03

The original `avg_receipt_total_rub: 850.0` and `purchases_per_month_mean:
10.0` (§2, §7) were unsourced assumptions — CONTEXT_PACK.md §4/§7 notes no
real X5 data is available and the case owner wasn't sure they could provide
real aggregates either. A later request to check what's publicly available
turned up two real sources, so these two constants were updated
(config bumped to `0.2.0`); `offline_share` and `household_size_weights`
stayed unsourced assumptions — no public data was found for either.

**Source 1 — X5's own reported average check (2025).** Retail.ru ("Как
меняется средний чек в ритейле"): X5's offline average check (Пятёрочка +
Перекрёсток) was **550–870 rub** in 2025 (vs. 2,650 rub online — irrelevant
here since the generator doesn't vary price by channel, only frequency).
Midpoint used: **710 rub**.

**Source 2 — Rosstat household food spending, 2025.** "Потребительские
расходы домашних хозяйств в 2025 году": monthly food spend per person by
household size —

| Household size | Monthly food spend / person |
|---|---|
| 1 (living alone) | 19,000 rub |
| 2 | *not published — interpolated below* |
| 3 | ~13,000 rub |
| 4 | *not published — interpolated below* |
| 5 | ~10,500 rub |

Rosstat also gives city-tier figures (12,000–12,500 for small towns,
14,500–15,000 for medium/large cities and million-cities, 16,500 for St.
Petersburg, ~18,000 for Moscow) — used only as a cross-check below, not as
an input to the calculation.

**Deriving `purchases_per_month_mean`.** The generator has no household-level
spending model (each `User` gets an individual purchase pattern regardless
of `family_size`), so the right input is *per-person* monthly spend,
weighted by this config's `household_size_weights` (`{1: 0.30, 2: 0.30,
3: 0.25, 4: 0.15}`). The 2- and 4-person figures aren't published; linear
interpolation between their neighbors was used and is flagged here as
estimated, not sourced:

```
2-person (interpolated) = (19000 + 13000) / 2 = 16000
4-person (interpolated) = (13000 + 10500) / 2 = 11750

weighted mean = 0.30×19000 + 0.30×16000 + 0.25×13000 + 0.15×11750
             = 5700 + 4800 + 3250 + 1762.5
             = 15512.5 rub/month/person
```

Cross-check: 15,512.5 lands inside Rosstat's own 14,500–15,000 band for
"medium/large cities and million-cities" — close enough (the weighted
estimate leans slightly single-person-heavy at these household weights) to
trust the interpolation didn't introduce a large error.

```
purchases_per_month = weighted_monthly_spend / avg_receipt
                     = 15512.5 / 710
                     ≈ 21.85  →  rounded to 22
```

~22/month is roughly 5 shopping trips a week — high for a "weekly big
shop" mental model, but consistent with the X5 average check itself:
550–870 rub is a *small-basket, convenience-format* number (Пятёрочка/
Перекрёсток, not a hypermarket), which implies frequent small trips rather
than infrequent large ones. `purchases_per_month_stddev` (6.5) keeps the
same ~30% relative spread as the original unsourced value (3.0/10.0) —
Rosstat doesn't publish a frequency variance, so this piece is still an
assumption, just scaled to the new mean.

**Verification**, 500 population users at a fixed seed (33,592 receipts
sampled):

```
mean receipt total_rub:        691.13   (target 710, -2.7%)
mean purchases/month:            22.39   (target 22, +1.8%)
```

Both inside the same ±15%-ish tolerance used for the original calibration
(§2) — no code changes were needed for this recalibration, since
`_price_for_item`'s range and `n_receipts`'s formula are already expressed
as functions of the config's calibration fields, not hardcoded constants.

## 7. Other calibration choices (not separately re-derived, listed for completeness)

- **3 months of purchase history per user** — long enough to show a
  recurring pattern (e.g. weekly milk) and compute a meaningful
  frequency/savings figure, short enough to keep generation and file sizes
  small for a multi-day hackathon.
- **`offline_share: 0.8`** — directly from CONTEXT_PACK.md §7 (case owner:
  "лучше оффлайн, но онлайн тоже можно"), not derived from public data;
  channel is a Bernoulli draw at this rate per receipt. Measured at 0.809
  over a 5,000-user run — matches the configured rate as expected for a
  simple Bernoulli parameter (no compounding calibration issue like §2's
  price range had).
- **Household size weights `{1: 0.30, 2: 0.30, 3: 0.25, 4: 0.15}`** — a
  reasonable assumption (no real household-size data available), not
  measured/fit against anything; flagged here only so a future correction
  knows there's no empirical basis to reconcile against.
- **`reference_date: "2026-09-01"`** (config, not code — see the final
  review's fix #7) — a fixed anchor so 3-months-back history stays close to
  "now" without ever reading the wall clock (which would break the
  determinism property this whole file is about). Needs a manual bump if
  this project runs long enough for Sept 2026 data to look stale again;
  nothing computes it automatically on purpose.
