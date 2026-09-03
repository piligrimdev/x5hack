# Validation report

## Population dataset

- ✅ **Valid JSONL, parses cleanly** — 10000 records parsed
- ✅ **10000 unique users** — 10000 unique user_id values, 10000 records
- ✅ **Receipt IDs globally unique** — 703200 receipts, all unique
- ✅ **Every receipt.user_id matches its containing user** — 0 mismatches
- ✅ **No negative prices, costs, or margins** — 0 negative-value lines
- ✅ **paid_unit_price_rub <= regular_unit_price_rub, always** — 0 violations
- ✅ **paid_unit_price_rub never below unit_cost_rub** — 0 violations
- ✅ **on_promo correctness (discount_pct/paid consistent with the flag)** — 0 inconsistent lines
- ✅ **Financial formulas: line and receipt totals reconcile (within rounding)** — all line and receipt-level financial fields reconcile
- ✅ **Multi-receipt purchase-days <= 5% of all (user, day) purchase groups** — 749/702451 = 0.11%
- ✅ **qty=1 more common than qty=2, qty=2 more common than qty>=3** — qty=1: 1160632, qty=2: 591959, qty>=3: 358143
- ✅ **Basket size distribution is not uniform (right-skewed, small baskets dominate)** — baskets<=3 lines: 68.7%, baskets>=6 lines: 12.6% — {1: 204054, 2: 145547, 3: 133754, 4: 79360, 5: 51609, 6: 41244, 7: 19838, 8: 11793, 9: 7438, 10: 5165, 11: 1735, 12: 1131, 13: 532}
- ✅ **Category prices differ meaningfully across categories** — min mean price 54, max mean price 394, ratio 7.3x
- ✅ **Visit frequency differs by segment (not all segments equal)** — segment mean receipt counts: {'Зрелые': 71.7, 'Старшие': 80.8, 'Молодёжь': 57.9, 'Взрослые с детьми до 3х лет': 78.6, 'Взрослые с вредными привычками': 71.4}
- ✅ **No hidden/simulation-truth fields leaked into the population file** — scanned 200 sampled records, 0 hidden-field leaks
- ✅ **Observable habitual_categories is derived from TRAIN-period receipts only (no holdout leakage)** — sampled 500 users: stored habitual_categories exactly reproducible from train-only receipts
- ✅ **Holdout-period receipts are present in the data (split isn't vacuous)** — found holdout-period receipts in sample

## Reference profiles

- ✅ **Blind reference file: valid JSON** — 40 profiles
- ✅ **Reference IDs are random UUIDs, not sequential/archetype-coded** — all user_id values match UUID format
- ✅ **No hidden/generation-class fields in the blind file** — scanned 40 profiles, 0 hidden-field leaks
- ✅ **Blind file order is shuffled, not grouped by class** — blind order is not alphabetically sorted (consistent with a real shuffle)
- ✅ **Answer key: every reference profile has a draft ground-truth entry** — 40 entries, ids match the reference set, all marked draft
- ✅ **Answer key never lists a forbidden category as acceptable** — checked 40 entries, 0 contradictions

**23/23 checks passed.**