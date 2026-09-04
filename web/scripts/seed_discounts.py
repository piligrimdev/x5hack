"""Seed discounts from the dataset JSONL file.

Scans for unique (category, discount_pct) pairs where on_promo=True
and creates a synthetic Discount per pair linked to that category
with discount_type "акция" and link_type "category".

Config via env vars:
  SEED_FILE_PATH   Path to the dataset JSONL file
  DATABASE_URL     PostgreSQL connection string
"""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "web" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

from webx5.core.db import db  # noqa: E402
from webx5.crud.catalog import CatalogRepository  # noqa: E402
from webx5.crud.discount import DiscountRepository  # noqa: E402


def _collect_promo_pairs(path: Path) -> set[tuple[str, Decimal]]:
    pairs: set[tuple[str, Decimal]] = set()
    with open(path, encoding="utf-8") as f:
        for line_num, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"WARNING: line {line_num} invalid JSON ({exc}), skipping")
                continue
            for receipt in obj.get("receipts", []):
                for line in receipt.get("lines", []):
                    if line.get("on_promo") and line.get("discount_pct", 0) > 0:
                        category = str(line.get("category", "")).strip()
                        pct = Decimal(str(line["discount_pct"]))
                        if category:
                            pairs.add((category, pct))
    return pairs


def main() -> None:
    seed_path = os.getenv("SEED_FILE_PATH", "").strip()
    if not seed_path:
        print("ERROR: SEED_FILE_PATH is not set")
        sys.exit(1)

    path = Path(seed_path)
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    print(f"Scanning {path} for unique (category, discount_pct) pairs...")
    pairs = _collect_promo_pairs(path)
    print(f"Found {len(pairs)} unique promo (category, pct) pairs")

    catalog_repo = CatalogRepository()
    discount_repo = DiscountRepository()
    created = skipped = 0

    with db.get_sync_session() as session:
        discount_type = discount_repo.get_type_by_name(session, "акция")
        if not discount_type:
            print("ERROR: discount_type 'акция' not found — run migrations first")
            sys.exit(1)

        link_type = discount_repo.get_link_type_by_name(session, "category")
        if not link_type:
            print("ERROR: link_type 'category' not found — run migrations first")
            sys.exit(1)

        for category_name, pct in sorted(pairs):
            category = catalog_repo.get_or_create_category_by_name(session, category_name)
            existing = discount_repo.get_or_create_by_category_and_pct(
                session,
                category_id=category.id,
                discount_pct=pct,
                discount_type_id=discount_type.id,
                link_type_id=link_type.id,
            )
            if existing:
                created += 1

        session.commit()

    print(f"Done. Discounts created/found: {created}")


if __name__ == "__main__":
    main()
