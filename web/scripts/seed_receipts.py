"""Seed loyalty cards and receipts from the dataset JSONL file.

Requires seed_products.py, seed_stores.py, and seed_discounts.py
to have been run first.

For each user line, creates a LoyaltyCard (if absent) and then all
receipts with their items. Uses on_promo / discount_pct to link the
matching synthetic Discount record to each item.

Config via env vars:
  SEED_FILE_PATH   Path to the dataset JSONL file
  DATABASE_URL     PostgreSQL connection string
  SEED_LIMIT       Max number of user lines to process (default: all)
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "web" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

from sqlalchemy import select  # noqa: E402

from webx5.core.db import db  # noqa: E402
from webx5.crud.catalog import CatalogRepository  # noqa: E402
from webx5.crud.discount import DiscountRepository  # noqa: E402
from webx5.crud.store import StoreRepository  # noqa: E402
from webx5.entities.loyalty import LoyaltyCard, Segment  # noqa: E402
from webx5.entities.receipt import Receipt, ReceiptItem  # noqa: E402

_USER_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


def _user_uuid(user_id: str) -> uuid.UUID:
    return uuid.uuid5(_USER_NS, f"user:{user_id}")


def _receipt_uuid(receipt_id: str) -> uuid.UUID:
    return uuid.uuid5(_USER_NS, f"receipt:{receipt_id}")


def main() -> None:
    seed_path = os.getenv("SEED_FILE_PATH", "").strip()
    if not seed_path:
        print("ERROR: SEED_FILE_PATH is not set")
        sys.exit(1)

    path = Path(seed_path)
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    limit_str = os.getenv("SEED_LIMIT", "").strip()
    limit = int(limit_str) if limit_str else None

    catalog_repo = CatalogRepository()
    store_repo = StoreRepository()
    discount_repo = DiscountRepository()

    users_processed = cards_created = receipts_created = receipts_skipped = items_created = 0

    with db.get_sync_session() as session:
        # Cache: segment_name → Segment.id
        segment_cache: dict[str, uuid.UUID | None] = {}

        # Cache: (category_name, pct) → Discount.id
        discount_cache: dict[tuple[str, str], uuid.UUID | None] = {}

        # Cache: chain → store_id (first store found)
        store_cache: dict[str, uuid.UUID | None] = {}

        discount_link_type = discount_repo.get_link_type_by_name(session, "category")

        def _get_segment_id(name: str) -> uuid.UUID | None:
            if name not in segment_cache:
                seg = session.scalar(select(Segment).where(Segment.name == name))
                segment_cache[name] = seg.id if seg else None
            return segment_cache[name]

        def _get_store_id(chain: str, district: str) -> uuid.UUID | None:
            key = f"{chain}|{district}"
            if key not in store_cache:
                from webx5.entities.store import Store, StoreFormat
                fmt = store_repo.get_format_by_name(session, chain)
                if not fmt:
                    store_cache[key] = None
                else:
                    store = session.scalar(
                        select(Store).where(
                            Store.format_id == fmt.id,
                            Store.geo_cluster == district,
                        )
                    )
                    if not store:
                        store = session.scalar(select(Store).where(Store.format_id == fmt.id))
                    store_cache[key] = store.id if store else None
            return store_cache[key]

        def _get_discount_id(category_name: str, pct: Decimal) -> uuid.UUID | None:
            key = (category_name, str(pct))
            if key not in discount_cache:
                cat = catalog_repo.get_category_by_name(session, category_name)
                if not cat or not discount_link_type:
                    discount_cache[key] = None
                else:
                    d = discount_repo.get_or_create_by_category_and_pct(
                        session,
                        category_id=cat.id,
                        discount_pct=pct,
                        discount_type_id=discount_repo.get_type_by_name(session, "акция").id,  # type: ignore[union-attr]
                        link_type_id=discount_link_type.id,
                    )
                    discount_cache[key] = d.id if d else None
            return discount_cache[key]

        with open(path, encoding="utf-8") as f:
            for line_num, raw in enumerate(f, start=1):
                if limit and users_processed >= limit:
                    break
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError as exc:
                    print(f"WARNING: line {line_num} invalid JSON ({exc}), skipping")
                    continue

                user_id_str = str(obj.get("user_id", "")).strip()
                if not user_id_str:
                    continue

                chain = str(obj.get("chain", "")).strip()
                district = str(obj.get("district_id", "")).strip() or "unknown"
                segment_name = str(obj.get("segment", "")).strip()

                loyalty_card_id = _user_uuid(user_id_str)

                # Create LoyaltyCard if absent
                card = session.get(LoyaltyCard, loyalty_card_id)
                if not card:
                    segment_id = _get_segment_id(segment_name) if segment_name else None
                    card = LoyaltyCard(
                        id=loyalty_card_id,
                        name=user_id_str,
                        geo_cluster=district,
                        segment_id=segment_id,
                    )
                    session.add(card)
                    session.flush()
                    cards_created += 1

                store_id = _get_store_id(chain, district)
                if not store_id:
                    print(f"WARNING: no store for chain='{chain}', district='{district}' — skipping user {user_id_str}")
                    users_processed += 1
                    continue

                for receipt_obj in obj.get("receipts", []):
                    receipt_id_str = str(receipt_obj.get("receipt_id", "")).strip()
                    if not receipt_id_str:
                        receipts_skipped += 1
                        continue

                    receipt_uuid = _receipt_uuid(receipt_id_str)

                    # Skip if receipt already exists
                    if session.get(Receipt, receipt_uuid):
                        receipts_skipped += 1
                        continue

                    purchase_date_str = receipt_obj.get("purchase_date", "")
                    try:
                        purchase_date = datetime.fromisoformat(purchase_date_str).replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        purchase_date = datetime.now(timezone.utc)

                    channel = str(receipt_obj.get("channel", "offline")).strip()
                    if channel not in ("online", "offline"):
                        channel = "offline"

                    receipt = Receipt(
                        id=receipt_uuid,
                        loyalty_card_id=loyalty_card_id,
                        store_id=store_id,
                        channel=channel,
                        purchase_date=purchase_date,
                    )
                    session.add(receipt)
                    session.flush()

                    for line in receipt_obj.get("lines", []):
                        sku_id = str(line.get("sku_id", "")).strip()
                        product = catalog_repo.get_product_by_sku(session, sku_id)
                        if not product:
                            continue

                        qty = int(line.get("qty", 1))
                        base_price = Decimal(str(line.get("regular_unit_price_rub", product.current_price)))
                        paid_price = Decimal(str(line.get("paid_unit_price_rub", base_price)))
                        discounted_amount = (base_price - paid_price).quantize(Decimal("0.01"))

                        discount_id = None
                        if line.get("on_promo") and line.get("discount_pct", 0) > 0:
                            category_name = str(line.get("category", "")).strip()
                            pct = Decimal(str(line["discount_pct"]))
                            discount_id = _get_discount_id(category_name, pct)

                        ri = ReceiptItem(
                            id=uuid.uuid4(),
                            receipt_id=receipt_uuid,
                            product_id=product.id,
                            quantity=qty,
                            base_price_at_purchase=base_price,
                            paid_price=paid_price,
                            discounted_amount=discounted_amount,
                            discount_id=discount_id,
                        )
                        session.add(ri)
                        items_created += 1

                    receipts_created += 1

                    if receipts_created % 500 == 0:
                        session.commit()
                        print(f"  ... {receipts_created} receipts committed")

                users_processed += 1

        session.commit()

    print(
        f"Done. Users processed: {users_processed}, "
        f"Cards created: {cards_created}, "
        f"Receipts created: {receipts_created}, "
        f"Receipts skipped: {receipts_skipped}, "
        f"Items created: {items_created}"
    )


if __name__ == "__main__":
    main()
