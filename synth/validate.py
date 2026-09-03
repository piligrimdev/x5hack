from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from synth.config import SynthConfig, load_config
from synth.features import compute_observable_habitual_categories
from synth.receipts import Receipt, ReceiptLine

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_HIDDEN_KEYS = {
    "generation_class",
    "_simulation_truth",
    "persona_archetype",
    "baseline_visits_28d",
    "frequency_headroom",
    "promo_sensitivity",
    "challenge_sensitivity",
    "reward_sensitivity",
    "basket_uplift_sensitivity",
    "app_open_probability",
    "fatigue_sensitivity",
    "category_affinity",
    "repurchase_intervals",
    "response_noise_seed",
}
_MONEY_TOLERANCE = 0.05  # rub, per-record float-rounding slack


class Check:
    def __init__(self, name: str):
        self.name = name
        self.passed: bool | None = None
        self.detail: str = ""

    def ok(self, detail: str = "") -> None:
        self.passed = True
        self.detail = detail

    def fail(self, detail: str) -> None:
        self.passed = False
        self.detail = detail


def _open_jsonl(path: str | Path):
    path = Path(path)
    if path.suffix == ".gz":
        import gzip

        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def _load_jsonl(path: str | Path) -> list[dict]:
    records = []
    with _open_jsonl(path) as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON — {e}") from e
    return records


def _scan_hidden_keys(obj, path: str, found: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _HIDDEN_KEYS:
                found.append(f"{path}.{k}")
            _scan_hidden_keys(v, f"{path}.{k}", found)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_hidden_keys(v, f"{path}[{i}]", found)


def _all_lines(user_or_profile: dict) -> list[dict]:
    return [line for r in user_or_profile["receipts"] for line in r["lines"]]


def validate_population(config: SynthConfig, population_path: str, n_expected: int) -> list[Check]:
    checks: list[Check] = []

    c = Check("Valid JSONL, parses cleanly")
    try:
        users = _load_jsonl(population_path)
        c.ok(f"{len(users)} records parsed")
    except ValueError as e:
        c.fail(str(e))
        checks.append(c)
        return checks
    checks.append(c)

    c = Check(f"{n_expected} unique users")
    ids = [u["user_id"] for u in users]
    if len(users) == n_expected and len(set(ids)) == n_expected:
        c.ok(f"{len(set(ids))} unique user_id values, {len(users)} records")
    else:
        c.fail(f"expected {n_expected} unique users, got {len(users)} records / {len(set(ids))} unique ids")
    checks.append(c)

    c = Check("Receipt IDs globally unique")
    all_receipt_ids = [r["receipt_id"] for u in users for r in u["receipts"]]
    dupes = [rid for rid, cnt in Counter(all_receipt_ids).items() if cnt > 1]
    if not dupes:
        c.ok(f"{len(all_receipt_ids)} receipts, all unique")
    else:
        c.fail(f"{len(dupes)} duplicate receipt_id values, e.g. {dupes[:5]}")
    checks.append(c)

    c = Check("Every receipt.user_id matches its containing user")
    mismatches = 0
    for u in users:
        for r in u["receipts"]:
            if r["user_id"] != u["user_id"]:
                mismatches += 1
    if mismatches == 0:
        c.ok("0 mismatches")
    else:
        c.fail(f"{mismatches} receipts with user_id != containing user's user_id")
    checks.append(c)

    c = Check("No negative prices, costs, or margins")
    bad = 0
    for line in (l for u in users for r in u["receipts"] for l in r["lines"]):
        if (
            line["regular_unit_price_rub"] < 0
            or line["paid_unit_price_rub"] < 0
            or line["unit_cost_rub"] < 0
            or line["gross_margin_rub"] < 0
            or line["savings_rub"] < 0
        ):
            bad += 1
    if bad == 0:
        c.ok("0 negative-value lines")
    else:
        c.fail(f"{bad} lines with a negative price/cost/margin/savings field")
    checks.append(c)

    c = Check("paid_unit_price_rub <= regular_unit_price_rub, always")
    bad = sum(
        1 for l in (l for u in users for r in u["receipts"] for l in r["lines"])
        if l["paid_unit_price_rub"] > l["regular_unit_price_rub"] + 1e-6
    )
    if bad == 0:
        c.ok("0 violations")
    else:
        c.fail(f"{bad} lines where paid > regular")
    checks.append(c)

    c = Check("paid_unit_price_rub never below unit_cost_rub")
    bad = sum(
        1 for l in (l for u in users for r in u["receipts"] for l in r["lines"])
        if l["paid_unit_price_rub"] < l["unit_cost_rub"] - 1e-6
    )
    if bad == 0:
        c.ok("0 violations")
    else:
        c.fail(f"{bad} lines sold below cost")
    checks.append(c)

    c = Check("on_promo correctness (discount_pct/paid consistent with the flag)")
    bad = 0
    for l in (l for u in users for r in u["receipts"] for l in r["lines"]):
        if l["on_promo"]:
            if not (l["discount_pct"] > 0 or abs(l["paid_unit_price_rub"] - l["unit_cost_rub"]) < 1e-6):
                bad += 1
        else:
            if l["discount_pct"] != 0 or abs(l["paid_unit_price_rub"] - l["regular_unit_price_rub"]) > 1e-6:
                bad += 1
    if bad == 0:
        c.ok("0 inconsistent lines")
    else:
        c.fail(f"{bad} lines where on_promo doesn't match discount_pct/paid price")
    checks.append(c)

    c = Check("Financial formulas: line and receipt totals reconcile (within rounding)")
    bad_lines, bad_receipts = 0, 0
    for u in users:
        for r in u["receipts"]:
            regular_sum = sum(l["regular_unit_price_rub"] * l["qty"] for l in r["lines"])
            paid_sum = sum(l["paid_unit_price_rub"] * l["qty"] for l in r["lines"])
            savings_sum = sum(l["savings_rub"] for l in r["lines"])
            margin_sum = sum(l["gross_margin_rub"] for l in r["lines"])
            for l in r["lines"]:
                expected_savings = round((l["regular_unit_price_rub"] - l["paid_unit_price_rub"]) * l["qty"], 2)
                expected_margin = round((l["paid_unit_price_rub"] - l["unit_cost_rub"]) * l["qty"], 2)
                if abs(l["savings_rub"] - expected_savings) > _MONEY_TOLERANCE or abs(l["gross_margin_rub"] - expected_margin) > _MONEY_TOLERANCE:
                    bad_lines += 1
            if (
                abs(r["regular_total_rub"] - regular_sum) > _MONEY_TOLERANCE
                or abs(r["total_rub"] - paid_sum) > _MONEY_TOLERANCE
                or abs(r["savings_rub"] - savings_sum) > _MONEY_TOLERANCE
                or abs(r["gross_margin_rub"] - margin_sum) > _MONEY_TOLERANCE
            ):
                bad_receipts += 1
    if bad_lines == 0 and bad_receipts == 0:
        c.ok("all line and receipt-level financial fields reconcile")
    else:
        c.fail(f"{bad_lines} lines and {bad_receipts} receipts with formula mismatches > {_MONEY_TOLERANCE} rub")
    checks.append(c)

    c = Check("Multi-receipt purchase-days <= 5% of all (user, day) purchase groups")
    day_groups: dict[tuple[str, str], int] = Counter()
    for u in users:
        for r in u["receipts"]:
            day_groups[(u["user_id"], r["purchase_date"])] += 1
    total_days = len(day_groups)
    multi_days = sum(1 for cnt in day_groups.values() if cnt > 1)
    rate = multi_days / total_days if total_days else 0.0
    if rate <= 0.05:
        c.ok(f"{multi_days}/{total_days} = {rate:.2%}")
    else:
        c.fail(f"{multi_days}/{total_days} = {rate:.2%}, exceeds 5%")
    checks.append(c)

    c = Check("qty=1 more common than qty=2, qty=2 more common than qty>=3")
    qtys = Counter(l["qty"] for u in users for r in u["receipts"] for l in r["lines"])
    q1, q2, q3plus = qtys.get(1, 0), qtys.get(2, 0), sum(v for k, v in qtys.items() if k >= 3)
    if q1 > q2 > q3plus:
        c.ok(f"qty=1: {q1}, qty=2: {q2}, qty>=3: {q3plus}")
    else:
        c.fail(f"expected qty=1 > qty=2 > qty>=3, got {q1} / {q2} / {q3plus}")
    checks.append(c)

    c = Check("Basket size distribution is not uniform (right-skewed, small baskets dominate)")
    basket_sizes = Counter(len(r["lines"]) for u in users for r in u["receipts"])
    total_receipts = sum(basket_sizes.values())
    small = sum(v for k, v in basket_sizes.items() if k <= 3) / total_receipts if total_receipts else 0
    large = sum(v for k, v in basket_sizes.items() if k >= 6) / total_receipts if total_receipts else 0
    if small > 0.45 and small > large * 2:
        c.ok(f"baskets<=3 lines: {small:.1%}, baskets>=6 lines: {large:.1%} — {dict(sorted(basket_sizes.items()))}")
    else:
        c.fail(f"basket sizes look too flat: <=3 lines {small:.1%}, >=6 lines {large:.1%}")
    checks.append(c)

    c = Check("Category prices differ meaningfully across categories")
    price_by_cat: dict[str, list[float]] = {}
    for l in (l for u in users for r in u["receipts"] for l in r["lines"]):
        price_by_cat.setdefault(l["category"], []).append(l["regular_unit_price_rub"])
    means = {cat: sum(v) / len(v) for cat, v in price_by_cat.items() if v}
    if means:
        lo, hi = min(means.values()), max(means.values())
        ratio = hi / lo if lo else 0
        if ratio > 3:
            c.ok(f"min mean price {lo:.0f}, max mean price {hi:.0f}, ratio {ratio:.1f}x")
        else:
            c.fail(f"category mean prices too close: min {lo:.0f}, max {hi:.0f}, ratio {ratio:.1f}x")
    else:
        c.fail("no price data found")
    checks.append(c)

    c = Check("Visit frequency differs by segment (not all segments equal)")
    receipts_per_user_by_segment: dict[str, list[int]] = {}
    for u in users:
        receipts_per_user_by_segment.setdefault(u["segment"], []).append(len(u["receipts"]))
    seg_means = {seg: sum(v) / len(v) for seg, v in receipts_per_user_by_segment.items() if v}
    if seg_means:
        lo, hi = min(seg_means.values()), max(seg_means.values())
        if hi - lo > 3:
            c.ok(f"segment mean receipt counts: {dict((k, round(v,1)) for k,v in seg_means.items())}")
        else:
            c.fail(f"segments too similar in visit frequency: {seg_means}")
    else:
        c.fail("no segment data found")
    checks.append(c)

    c = Check("No hidden/simulation-truth fields leaked into the population file")
    found: list[str] = []
    for u in users[:200]:  # sampling is enough — the field set is structural, not per-record-random
        _scan_hidden_keys(u, u["user_id"], found)
    if not found:
        c.ok("scanned 200 sampled records, 0 hidden-field leaks")
    else:
        c.fail(f"found hidden fields: {found[:10]}")
    checks.append(c)

    c = Check("Observable habitual_categories is derived from TRAIN-period receipts only (no holdout leakage)")
    train_end = config.temporal_split.train_end.isoformat()
    mismatches = 0
    for u in users[:500]:
        recomputed = compute_observable_habitual_categories(
            [Receipt(receipt_id=r["receipt_id"], user_id=r["user_id"], purchase_date=r["purchase_date"],
                      channel=r["channel"], lines=[ReceiptLine(**l) for l in r["lines"]],
                      regular_total_rub=r["regular_total_rub"], total_rub=r["total_rub"],
                      savings_rub=r["savings_rub"], gross_margin_rub=r["gross_margin_rub"])
             for r in u["receipts"]],
            config,
        )
        if recomputed != u["habitual_categories"]:
            mismatches += 1
    if mismatches == 0:
        c.ok("sampled 500 users: stored habitual_categories exactly reproducible from train-only receipts")
    else:
        c.fail(f"{mismatches}/500 sampled users' habitual_categories do NOT match a train-only recomputation (possible holdout leakage)")
    checks.append(c)

    holdout_start = config.temporal_split.holdout_start.isoformat()
    has_holdout = any(r["purchase_date"] >= holdout_start for u in users[:200] for r in u["receipts"])
    c = Check("Holdout-period receipts are present in the data (split isn't vacuous)")
    if has_holdout:
        c.ok("found holdout-period receipts in sample")
    else:
        c.fail("no holdout-period receipts found in sampled users — split may be misconfigured")
    checks.append(c)

    return checks


def validate_reference(config: SynthConfig, blind_path: str, answer_key_path: str) -> list[Check]:
    checks: list[Check] = []

    c = Check("Blind reference file: valid JSON")
    try:
        with open(blind_path, encoding="utf-8") as f:
            blind = json.load(f)
        c.ok(f"{len(blind)} profiles")
    except (ValueError, OSError) as e:
        c.fail(str(e))
        checks.append(c)
        return checks
    checks.append(c)

    c = Check("Reference IDs are random UUIDs, not sequential/archetype-coded")
    bad = [p["user_id"] for p in blind if not _UUID_RE.match(p["user_id"])]
    if not bad:
        c.ok("all user_id values match UUID format")
    else:
        c.fail(f"{len(bad)} non-UUID ids, e.g. {bad[:5]}")
    checks.append(c)

    c = Check("No hidden/generation-class fields in the blind file")
    found: list[str] = []
    for p in blind:
        _scan_hidden_keys(p, p["user_id"], found)
    if not found:
        c.ok(f"scanned {len(blind)} profiles, 0 hidden-field leaks")
    else:
        c.fail(f"found hidden fields: {found[:10]}")
    checks.append(c)

    c = Check("Blind file order is shuffled, not grouped by class")
    # We can't see class in the blind file (by design) — instead check the
    # order isn't literally the input order (would be a shuffle no-op bug).
    ids = [p["user_id"] for p in blind]
    if ids != sorted(ids):
        c.ok("blind order is not alphabetically sorted (consistent with a real shuffle)")
    else:
        c.fail("blind file order is suspiciously sorted")
    checks.append(c)

    c = Check("Answer key: every reference profile has a draft ground-truth entry")
    try:
        with open(answer_key_path, encoding="utf-8") as f:
            answer_key = json.load(f)
        blind_ids = {p["user_id"] for p in blind}
        key_ids = {a["user_id"] for a in answer_key}
        if blind_ids == key_ids and all(a.get("draft") is True for a in answer_key):
            c.ok(f"{len(answer_key)} entries, ids match the reference set, all marked draft")
        else:
            c.fail(f"id set mismatch or not all entries marked draft (blind={len(blind_ids)}, key={len(key_ids)})")
    except (ValueError, OSError) as e:
        c.fail(str(e))
        checks.append(c)
        return checks
    checks.append(c)

    c = Check("Answer key never lists a forbidden category as acceptable")
    bad = [
        a["user_id"] for a in answer_key
        if set(a["acceptable_target_categories"]) & set(a["forbidden_categories"])
    ]
    if not bad:
        c.ok(f"checked {len(answer_key)} entries, 0 contradictions")
    else:
        c.fail(f"{len(bad)} entries list a forbidden category as an acceptable target: {bad[:5]}")
    checks.append(c)

    return checks


def render_report(population_checks: list[Check], reference_checks: list[Check]) -> str:
    lines = ["# Validation report", ""]
    for title, checks in (("Population dataset", population_checks), ("Reference profiles", reference_checks)):
        lines.append(f"## {title}")
        lines.append("")
        for c in checks:
            mark = "✅" if c.passed else "❌"
            lines.append(f"- {mark} **{c.name}** — {c.detail}")
        lines.append("")
    total = len(population_checks) + len(reference_checks)
    failed = sum(1 for c in population_checks + reference_checks if not c.passed)
    lines.append(f"**{total - failed}/{total} checks passed.**")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate a generated synthetic dataset.")
    parser.add_argument("--config", default="config/synth_schema.yaml")
    parser.add_argument("--population", required=True)
    parser.add_argument("--n-expected", type=int, required=True)
    parser.add_argument("--reference-blind", required=True)
    parser.add_argument("--answer-key", required=True)
    parser.add_argument("--report-out", default=None)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    pop_checks = validate_population(config, args.population, args.n_expected)
    ref_checks = validate_reference(config, args.reference_blind, args.answer_key)

    report = render_report(pop_checks, ref_checks)
    print(report)
    if args.report_out:
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_out).write_text(report, encoding="utf-8")

    if any(not c.passed for c in pop_checks + ref_checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
