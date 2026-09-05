from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, noload, selectinload

from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem
from webx5.entities.task import Task, TaskStatus

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
            .options(noload(Product.category))
            .group_by(Product.id)
        ).all()

        result: list[tuple[Product, int]] = []
        for product, purchase_count, avg_quantity in rows:
            weekly_frequency = purchase_count / span_weeks
            if weekly_frequency >= MIN_WEEKLY_FREQUENCY:
                result.append((product, max(1, round(avg_quantity))))
        return result

    def get_shopping_context(self, session: Session, user_id: uuid.UUID) -> dict:
        """Compact personal data for the LLM, without identity/payment details."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=90)
        first = session.scalar(select(func.min(Receipt.purchase_date)).where(
            Receipt.loyalty_card_id == user_id, Receipt.purchase_date >= since,
        ))
        weeks = max((now.replace(tzinfo=None) - first.replace(tzinfo=None)).days / 7, 1) if first else 1
        rows = session.execute(select(
            Product.sku_id, func.sum(ReceiptItem.quantity),
            func.count(func.distinct(Receipt.id)), func.max(Receipt.purchase_date),
            func.sum(ReceiptItem.quantity * ReceiptItem.paid_price),
        ).join(ReceiptItem, ReceiptItem.product_id == Product.id)
          .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
          .where(Receipt.loyalty_card_id == user_id, Receipt.purchase_date >= since)
          .group_by(Product.sku_id).order_by(func.sum(ReceiptItem.quantity).desc())).all()
        tasks = session.scalars(select(Task).join(TaskStatus).where(
            Task.loyalty_card_id == user_id, TaskStatus.name == "открыто", Task.deadline > now,
        ).options(selectinload(Task.criteria))).all()
        catalog = self.get_full_catalog(session) if tasks else []
        from webx5.utils.forbidden_categories import get_forbidden_categories
        forbidden = get_forbidden_categories()
        return {
            "as_of": now.date().isoformat(),
            "history_weeks": round(weeks, 1),
            "typical_weekly_spend_rub": round(sum(float(row[4]) for row in rows) / weeks, 2),
            "purchases": [{"sku_id": sku, "weekly_quantity": round(float(qty) / weeks, 2),
                           "purchase_count": count, "last_purchase": last.date().isoformat()}
                          for sku, qty, count, last, _ in rows[:100]],
            "challenges": [self.challenge_context(t, catalog, forbidden) for t in tasks],
        }

    @staticmethod
    def challenge_context(task: Task, catalog: list[Product], forbidden: set[str]) -> dict:
        # Match the same product/category and exclusion rules as task completion.
        matching = [p for p in catalog if
                    (p.category.name if p.category else "") not in forbidden and (
                        (task.criterion_type == "product" and p.id == task.criterion_entity_id) or
                        (task.criterion_type == "category" and p.category_id == task.criterion_entity_id)
                    )]
        criteria = [{"kind": c.kind, "key": c.key,
                     "value_num": float(c.value_num) if c.value_num is not None else None,
                     "value_text": c.value_text} for c in task.criteria]
        target = max([task.quantity_target] + [int(c.value_num) for c in task.criteria
                                              if c.kind == "item_quantity" and c.value_num is not None])
        return {
            "title": task.title, "description": task.description,
            "criterion_type": task.criterion_type,
            "quantity_target": target, "quantity_current": task.quantity_current,
            "quantity_remaining": max(0, target - task.quantity_current),
            "deadline": task.deadline.isoformat(),
            "matching_sku_ids": [p.sku_id for p in matching],
            "criteria": criteria,
            "all_criteria_required": True,
            "supported": bool(criteria) and task.criterion_type in {"product", "category"}
                         and all(c.kind in {"item_quantity", "spend_threshold_rub"} for c in task.criteria),
        }

    def get_full_catalog(self, session: Session) -> list[Product]:
        return list(session.scalars(select(Product)))
