from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem
from webx5.entities.store import Store


class ReceiptRepository:
    def create(
        self,
        session: Session,
        receipt_id: uuid.UUID,
        loyalty_card_id: uuid.UUID | None,
        store_id: uuid.UUID,
        channel: str,
        payment_card_uid: str | None,
        items: list[dict],
    ) -> tuple[Receipt, bool]:
        """Create receipt. Returns (receipt, is_new). Idempotent via PK IntegrityError."""
        receipt = Receipt(
            id=receipt_id,
            loyalty_card_id=loyalty_card_id,
            store_id=store_id,
            channel=channel,
            payment_card_uid=payment_card_uid,
        )
        try:
            session.add(receipt)
            session.flush()
        except IntegrityError:
            session.rollback()
            existing = session.get(Receipt, receipt_id)
            if existing:
                session.expire_all()
                session.refresh(existing)
                return existing, False
            raise

        for item_data in items:
            ri = ReceiptItem(
                id=uuid.uuid4(),
                receipt_id=receipt_id,
                product_id=item_data["product_id"],
                quantity=item_data["quantity"],
                base_price_at_purchase=item_data["base_price_at_purchase"],
                paid_price=item_data["paid_price"],
                discounted_amount=item_data["discounted_amount"],
                discount_id=item_data.get("discount_id"),
            )
            session.add(ri)

        session.commit()
        session.refresh(receipt)
        return receipt, True

    def get_by_id(self, session: Session, receipt_id: uuid.UUID) -> Receipt | None:
        return session.get(Receipt, receipt_id)

    def get_with_items(
        self,
        session: Session,
        receipt_id: uuid.UUID,
        loyalty_card_id: uuid.UUID | None = None,
    ) -> Receipt | None:
        receipt = session.get(Receipt, receipt_id)
        if receipt is None:
            return None
        if loyalty_card_id is not None and receipt.loyalty_card_id != loyalty_card_id:
            return None
        _ = receipt.items  # force load
        return receipt

    def list_by_loyalty_card(
        self,
        session: Session,
        loyalty_card_id: uuid.UUID,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Receipt], int]:
        stmt = (
            select(Receipt)
            .where(Receipt.loyalty_card_id == loyalty_card_id)
            .order_by(Receipt.purchase_date.desc())
        )
        total = session.scalar(
            select(func.count()).select_from(Receipt).where(Receipt.loyalty_card_id == loyalty_card_id)
        ) or 0
        receipts = list(session.scalars(stmt.offset((page - 1) * size).limit(size)))
        return receipts, total

    def get_economy_summary(
        self,
        session: Session,
        loyalty_card_id: uuid.UUID,
    ) -> dict:
        row = session.execute(
            select(
                func.coalesce(func.sum(ReceiptItem.discounted_amount * ReceiptItem.quantity), 0).label("total_saved"),
                func.coalesce(func.sum(ReceiptItem.paid_price * ReceiptItem.quantity), 0).label("total_paid"),
            )
            .join(Receipt, ReceiptItem.receipt_id == Receipt.id)
            .where(Receipt.loyalty_card_id == loyalty_card_id)
        ).one()

        receipts_count = session.scalar(
            select(func.count(Receipt.id)).where(Receipt.loyalty_card_id == loyalty_card_id)
        ) or 0

        return {
            "total_saved": Decimal(str(row.total_saved)),
            "total_paid": Decimal(str(row.total_paid)),
            "receipts_count": receipts_count,
        }

    def get_items_with_products(
        self,
        session: Session,
        receipt_id: uuid.UUID,
    ) -> list[tuple[ReceiptItem, Product]]:
        stmt = (
            select(ReceiptItem, Product)
            .join(Product, ReceiptItem.product_id == Product.id)
            .where(ReceiptItem.receipt_id == receipt_id)
        )
        return list(session.execute(stmt))
