"""Seed products from a JSONL file into the database.

Config via env vars (loaded from .env):
  SEED_FILE_PATH   Path to the JSONL file
  DATABASE_URL     PostgreSQL connection string
"""

import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "web" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from webx5.core.db import db  # noqa: E402
from webx5.crud.catalog import CatalogRepository  # noqa: E402

REQUIRED_FIELDS = {"sku_id", "item", "category", "regular_unit_price_rub"}


def _parse_record(line_num: int, row: dict) -> dict | None:
    missing = REQUIRED_FIELDS - set(row.keys())
    if missing:
        print(f"WARNING: line {line_num} missing field(s) {sorted(missing)}, skipping")
        return None

    try:
        price = Decimal(str(row["regular_unit_price_rub"]))
    except InvalidOperation:
        print(f"WARNING: line {line_num} invalid price '{row['regular_unit_price_rub']}', skipping")
        return None

    if price <= 0:
        print(f"WARNING: line {line_num} invalid price {price}, skipping")
        return None

    return {
        "sku_id": str(row["sku_id"]).strip(),
        "name": str(row["item"]).strip(),
        "category": str(row["category"]).strip(),
        "price": price,
    }


def main() -> None:
    seed_path = os.getenv("SEED_FILE_PATH", "").strip()
    if not seed_path:
        print("ERROR: SEED_FILE_PATH is not set")
        sys.exit(1)

    path = Path(seed_path)
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print("WARNING: file is empty, nothing to import")
        return

    # Support both JSON array format ([{...}, ...]) and JSONL (one JSON object per line)
    if text.startswith("["):
        try:
            records = json.loads(text)
        except json.JSONDecodeError as exc:
            print(f"ERROR: failed to parse JSON array: {exc}")
            sys.exit(1)
        print(f"Loaded {len(records)} records from {path} (JSON array format)")
        rows = []
        for i, obj in enumerate(records, start=1):
            row = _parse_record(i, obj)
            rows.append(row)
    else:
        lines = [l for l in text.splitlines() if l.strip()]
        print(f"Loaded {len(lines)} lines from {path} (JSONL format)")
        rows = []
        for i, raw in enumerate(lines, start=1):
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"WARNING: line {i} invalid JSON ({exc}), skipping")
                rows.append(None)
                continue
            rows.append(_parse_record(i, obj))

    repo = CatalogRepository()
    imported = updated = skipped = 0

    with db.get_sync_session() as session:
        for i, row in enumerate(rows, start=1):
            if row is None:
                skipped += 1
                continue

            category = repo.get_or_create_category_by_name(session, row["category"])
            is_new = repo.get_product_by_sku(session, row["sku_id"]) is None
            repo.upsert_product(
                session,
                sku_id=row["sku_id"],
                name=row["name"],
                current_price=row["price"],
                category_id=category.id,
            )
            if is_new:
                imported += 1
            else:
                updated += 1

        session.commit()

    print(f"Done. Imported: {imported}, Updated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
