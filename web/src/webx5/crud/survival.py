from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from webx5.entities.category import Category
from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem


class SurvivalRepository:
    def fetch_purchase_dates(self, session: Session) -> dict[str, dict[str, list[date]]]:
        """Every (user, category, purchase date) triple across ALL users'
        FULL receipt history — the population-level input
        `synth.survival.fit_population_curves` needs to fit one Kaplan-Meier
        curve per category.

        `.distinct()` collapses multiple line items of the same category on
        one receipt into a single row; the `set()` below also collapses two
        separate same-day receipts in the same category, since a same-day
        repeat purchase isn't a distinct repurchase event at the day
        granularity this model uses.
        """
        rows = session.execute(
            select(Receipt.loyalty_card_id, Category.name, Receipt.purchase_date)
            .join(ReceiptItem, ReceiptItem.receipt_id == Receipt.id)
            .join(Product, ReceiptItem.product_id == Product.id)
            .join(Category, Product.category_id == Category.id)
            .where(Receipt.loyalty_card_id.is_not(None))
            .distinct()
        ).all()

        by_user: dict[str, dict[str, set[date]]] = {}
        for loyalty_card_id, category_name, purchase_date in rows:
            by_category = by_user.setdefault(str(loyalty_card_id), {})
            by_category.setdefault(category_name, set()).add(purchase_date.date())

        return {
            user_id: {category: sorted(dates) for category, dates in by_category.items()}
            for user_id, by_category in by_user.items()
        }
