"""Generate demo discounts across all categories and discount types.

Creates a realistic set of discounts:
  - Акции (промо) по категориям — scope=all и scope=by_format
  - Акции по конкретным товарам — scope=all
  - Лояльность по категориям — scope=all
  - Персональные по категориям — scope=all (применяются только с картой)
  - Скидки только для Перекрёстка (by_format)

Idempotent: skips discounts that already exist for the same
(entity_id, value, link_type_id, discount_type_id) combination.

Config via env vars:
  DATABASE_URL   PostgreSQL connection string
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "web" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

from sqlalchemy import select  # noqa: E402

from webx5.core.db import db  # noqa: E402
from webx5.entities.discount import Discount, DiscountLinkType, DiscountType, FormatDiscount  # noqa: E402
from webx5.entities.product import Product  # noqa: E402
from webx5.entities.store import StoreFormat  # noqa: E402

now = datetime.now(timezone.utc)

# ─── discount definitions ───────────────────────────────────────────────────
# Each entry: (discount_type, link_type, entity_name, value_pct, scope, valid_days, format_names)
# entity_name — category name, or "SKU:<sku_id>" for product-level discounts
# format_names — list of chain names for by_format scope (ignored otherwise)

DISCOUNT_SPECS: list[tuple] = [
    # (type,          link,       entity,                      pct,  scope,       days,  formats)

    # ── Акции по категориям (scope=all) ──────────────────────────────────────
    ("акция", "category", "молочные продукты и яйца",  15, "all",       30,  []),
    ("акция", "category", "хлеб и выпечка",             10, "all",       14,  []),
    ("акция", "category", "мясо и птица",               12, "all",       7,   []),
    ("акция", "category", "овощи",                      20, "all",       10,  []),
    ("акция", "category", "напитки",                    10, "all",       21,  []),
    ("акция", "category", "кондитерка",                  8, "all",       14,  []),
    ("акция", "category", "бакалея",                    10, "all",       30,  []),
    ("акция", "category", "заморозка",                  15, "all",       14,  []),
    ("акция", "category", "алкоголь",                    5, "all",       30,  []),
    ("акция", "category", "рыба и морепродукты",        18, "all",       7,   []),
    ("акция", "category", "консервация",                12, "all",       30,  []),
    ("акция", "category", "соусы и приправы",            7, "all",       30,  []),
    ("акция", "category", "сладости и снеки",           10, "all",       21,  []),

    # ── Акции только для Перекрёстка (scope=by_format) ──────────────────────
    ("акция", "category", "готовая еда",                20, "by_format", 14,  ["Перекрёсток"]),
    ("акция", "category", "молочные продукты и яйца",  25, "by_format", 7,   ["Перекрёсток"]),
    ("акция", "category", "мясо и птица",               18, "by_format", 7,   ["Перекрёсток"]),

    # ── Акции только для Пятёрочки (scope=by_format) ────────────────────────
    ("акция", "category", "бакалея",                    15, "by_format", 14,  ["Пятёрочка"]),
    ("акция", "category", "напитки",                    18, "by_format", 10,  ["Пятёрочка"]),

    # ── Акции только для Чижика (scope=by_format) ───────────────────────────
    ("акция", "category", "овощи",                      25, "by_format", 7,   ["Чижик"]),
    ("акция", "category", "молочные продукты и яйца",  20, "by_format", 14,  ["Чижик"]),

    # ── Лояльность по категориям (scope=all, бессрочно) ─────────────────────
    ("лояльность", "category", "молочные продукты и яйца",   5, "all", None, []),
    ("лояльность", "category", "мясо и птица",                5, "all", None, []),
    ("лояльность", "category", "бакалея",                     3, "all", None, []),
    ("лояльность", "category", "кондитерка",                  3, "all", None, []),
    ("лояльность", "category", "напитки",                     5, "all", None, []),
    ("лояльность", "category", "рыба и морепродукты",         5, "all", None, []),
    ("лояльность", "category", "алкоголь",                    3, "all", None, []),
    ("лояльность", "category", "заморозка",                   5, "all", None, []),

    # ── Персональные по категориям (только с картой лояльности) ─────────────
    ("персональная", "category", "молочные продукты и яйца",  30, "all", 30,  []),
    ("персональная", "category", "мясо и птица",              25, "all", 30,  []),
    ("персональная", "category", "готовая еда",               20, "all", 14,  []),
    ("персональная", "category", "детское питание",           15, "all", 30,  []),
    ("персональная", "category", "кондитерка",                20, "all", 14,  []),
    ("персональная", "category", "бакалея",                   15, "all", 30,  []),
    ("персональная", "category", "напитки",                   15, "all", 14,  []),
    ("персональная", "category", "сладости и снеки",          20, "all", 21,  []),
    ("персональная", "category", "рыба и морепродукты",       25, "all", 14,  []),

    # ── Уценка по конкретным товарам (берём первые доступные SKU) ───────────
    # entity_name задаётся как "SKU:<sku_id>" — заполнится при запуске
]

# Extra product-level уценки — top SKUs (will be resolved at runtime)
PRODUCT_DISCOUNT_SPECS = [
    # (sku_id, value_pct, valid_days)
    ("sku_0000", 30, 3),
    ("sku_0001", 25, 3),
    ("sku_0002", 40, 5),
    ("sku_0003", 35, 3),
    ("sku_0004", 20, 7),
    ("sku_0005", 15, 7),
    ("sku_0006", 30, 5),
    ("sku_0007", 25, 5),
    ("sku_0008", 20, 7),
    ("sku_0009", 10, 14),
]


def _get_or_none(session, entity_id, value, link_type_id, discount_type_id):
    return session.scalar(
        select(Discount).where(
            Discount.entity_id == entity_id,
            Discount.value == value,
            Discount.link_type_id == link_type_id,
            Discount.discount_type_id == discount_type_id,
        )
    )


def main() -> None:
    created = skipped = 0

    with db.get_sync_session() as session:
        # ── Lookup dictionaries ────────────────────────────────────────────
        type_map: dict[str, uuid.UUID] = {
            row.name: row.id
            for row in session.scalars(select(DiscountType))
        }
        link_map: dict[str, uuid.UUID] = {
            row.name: row.id
            for row in session.scalars(select(DiscountLinkType))
        }
        format_map: dict[str, uuid.UUID] = {
            row.name: row.id
            for row in session.scalars(select(StoreFormat))
        }

        from webx5.entities.category import Category
        category_map: dict[str, uuid.UUID] = {
            row.name: row.id
            for row in session.scalars(select(Category))
        }

        product_map: dict[str, uuid.UUID] = {
            row.sku_id: row.id
            for row in session.scalars(select(Product))
        }

        def _create(
            discount_type: str,
            link_type: str,
            entity_id: uuid.UUID,
            value: int,
            scope: str,
            valid_days: int | None,
            format_names: list[str],
            label: str,
        ) -> None:
            nonlocal created, skipped
            dt_id = type_map.get(discount_type)
            lt_id = link_map.get(link_type)
            if not dt_id or not lt_id:
                print(f"  WARN: тип '{discount_type}' или link '{link_type}' не найден, пропуск")
                return

            existing = _get_or_none(session, entity_id, Decimal(str(value)), lt_id, dt_id)
            if existing:
                skipped += 1
                return

            valid_to = (now + timedelta(days=valid_days)) if valid_days else None

            d = Discount(
                id=uuid.uuid4(),
                value=Decimal(str(value)),
                discount_type_id=dt_id,
                link_type_id=lt_id,
                entity_id=entity_id,
                scope=scope,
                valid_from=now,
                valid_to=valid_to,
            )
            session.add(d)
            session.flush()

            for fname in format_names:
                fid = format_map.get(fname)
                if fid:
                    session.add(FormatDiscount(discount_id=d.id, format_id=fid))
                else:
                    print(f"  WARN: формат '{fname}' не найден в БД (запустите generate_stores.py)")

            created += 1
            ttl = f"{valid_days} дн." if valid_days else "∞"
            print(f"  +{value}% {discount_type}/{link_type} [{scope}] {ttl} — {label}")

        # ── Category discounts ─────────────────────────────────────────────
        for dtype, ltype, cat_name, pct, scope, days, formats in DISCOUNT_SPECS:
            cat_id = category_map.get(cat_name)
            if not cat_id:
                print(f"  WARN: категория '{cat_name}' не найдена, пропуск")
                continue
            _create(dtype, ltype, cat_id, pct, scope, days, formats, cat_name)

        # ── Product-level уценки ──────────────────────────────────────────
        lt_id_product = link_map.get("product")
        dt_id_utsanka = type_map.get("уценка")
        if lt_id_product and dt_id_utsanka:
            for sku_id, pct, days in PRODUCT_DISCOUNT_SPECS:
                prod_id = product_map.get(sku_id)
                if not prod_id:
                    continue
                _create("уценка", "product", prod_id, pct, "all", days, [], f"SKU {sku_id}")

        session.commit()

    print(f"\nГотово. Скидок создано: {created}, пропущено: {skipped}")


if __name__ == "__main__":
    main()
