"""Seed stores from the dataset JSONL file.

Scans dataset for unique (chain, district_id) pairs and creates
a StoreFormat per chain and a Store per (chain, district) pair.

Config via env vars:
  SEED_FILE_PATH   Path to the dataset JSONL file
  DATABASE_URL     PostgreSQL connection string
"""

import json
import os
import sys
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "web" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

from webx5.core.db import db  # noqa: E402
from webx5.crud.store import StoreRepository  # noqa: E402


def _collect_store_pairs(path: Path) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
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
            chain = str(obj.get("chain", "")).strip()
            district = str(obj.get("district_id", "")).strip()
            if chain:
                pairs.add((chain, district or "unknown"))
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

    print(f"Scanning {path} for unique (chain, district) pairs...")
    pairs = _collect_store_pairs(path)
    print(f"Found {len(pairs)} unique store (chain, district) pairs")

    repo = StoreRepository()
    created_formats = created_stores = skipped = 0

    with db.get_sync_session() as session:
        for chain, district in sorted(pairs):
            fmt = repo.get_or_create_format(session, chain)
            if fmt.id not in {f.id for f in [fmt]}:
                created_formats += 1

            # Check if store for this (format, geo_cluster) already exists
            from sqlalchemy import select
            from webx5.entities.store import Store

            existing = session.scalar(
                select(Store).where(
                    Store.format_id == fmt.id,
                    Store.geo_cluster == district,
                )
            )
            if existing:
                skipped += 1
                continue

            store = Store(
                id=uuid.uuid4(),
                format_id=fmt.id,
                geo_cluster=district,
                address=None,
            )
            session.add(store)
            created_stores += 1

        session.commit()

    print(f"Done. Stores created: {created_stores}, skipped (already exist): {skipped}")


if __name__ == "__main__":
    main()
