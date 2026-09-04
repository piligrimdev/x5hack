from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem

# A product must repeat at least this often per week (on average, over the
# user's own full receipt history) to be suggested for the weekly basket —
# 0.5 means "roughly once every two weeks or more often". Deliberately
# conservative: the basket should read as "what you actually keep buying",
# not every item ever bought once. Tune against real seeded data if the
# suggested list reads as too sparse/too noisy once Task 2's seed is live.
MIN_WEEKLY_FREQUENCY = 0.5


class BasketRepository:
    def suggest_items(self, session: Session, user_id: uuid.UUID) -> list[tuple[Product, int]]:
        """Return (product, suggested_quantity) pairs for products this user
        buys with at least MIN_WEEKLY_FREQUENCY cadence, based on their own
        full receipt history. suggested_quantity is the rounded average
        quantity per purchase (minimum 1). Empty list if the user has no
        receipts at all (min/max purchase_date both None)."""
        min_date, max_date = session.execute(
            select(func.min(Receipt.purchase_date), func.max(Receipt.purchase_date)).where(
                Receipt.loyalty_card_id == user_id
            )
        ).one()
        if min_date is None or max_date is None:
            return []

        span_weeks = max((max_date - min_date).days / 7, 1.0)

        rows = session.execute(
            select(
                Product,
                func.count(ReceiptItem.id).label("purchase_count"),
                func.avg(ReceiptItem.quantity).label("avg_quantity"),
            )
            .join(ReceiptItem, ReceiptItem.product_id == Product.id)
            .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
            .where(Receipt.loyalty_card_id == user_id)
            .group_by(Product.id)
        ).all()

        result: list[tuple[Product, int]] = []
        for product, purchase_count, avg_quantity in rows:
            weekly_frequency = purchase_count / span_weeks
            if weekly_frequency >= MIN_WEEKLY_FREQUENCY:
                result.append((product, max(1, round(avg_quantity))))
        return result

    def get_full_catalog(self, session: Session) -> list[Product]:
        return list(session.scalars(select(Product)))
