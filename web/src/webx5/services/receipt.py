from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from webx5.crud.discount import DiscountRepository
from webx5.crud.receipt import ReceiptRepository
from webx5.entities.receipt import Receipt
from webx5.schemas.receipt import ReceiptCreate


class ReceiptService:
    def __init__(
        self,
        receipt_repo: ReceiptRepository,
        discount_repo: DiscountRepository,
    ) -> None:
        self.receipt_repo = receipt_repo
        self.discount_repo = discount_repo

    def create_receipt(
        self,
        session: Session,
        receipt_id: uuid.UUID,
        data: ReceiptCreate,
    ) -> tuple[Receipt, bool]:
        from sqlalchemy import select

        from webx5.entities.product import Product
        from webx5.entities.store import Store

        store = session.get(Store, data.store_id)
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")

        product_ids = [item.product_id for item in data.items]
        products: dict[uuid.UUID, Product] = {
            p.id: p
            for p in session.scalars(select(Product).where(Product.id.in_(product_ids)))
        }
        missing = [str(pid) for pid in product_ids if pid not in products]
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"detail": "Unknown product_ids", "unknown_product_ids": missing},
            )

        now = datetime.now(timezone.utc)
        items_data = []
        invalid_items = []

        for item in data.items:
            product = products[item.product_id]
            base_price = Decimal(str(product.current_price))

            discount_id = item.discount_id
            paid_price = base_price

            if discount_id is not None:
                discount = self.discount_repo.get_by_id(session, discount_id)
                if discount is None:
                    invalid_items.append({
                        "product_id": str(item.product_id),
                        "discount_id": str(discount_id),
                        "reason": "discount_not_found",
                    })
                    continue

                # Check date validity
                if discount.valid_to is not None:
                    valid_to = discount.valid_to
                    if valid_to.tzinfo is None:
                        from datetime import timezone as tz
                        valid_to = valid_to.replace(tzinfo=tz.utc)
                    if valid_to < now:
                        invalid_items.append({
                            "product_id": str(item.product_id),
                            "discount_id": str(discount_id),
                            "reason": "discount_expired",
                        })
                        continue

                value = Decimal(str(discount.value))
                paid_price = (base_price * (1 - value / 100)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            discounted_amount = (base_price - paid_price).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            items_data.append({
                "product_id": item.product_id,
                "quantity": item.quantity,
                "base_price_at_purchase": base_price,
                "paid_price": paid_price,
                "discounted_amount": discounted_amount,
                "discount_id": discount_id,
            })

        if invalid_items:
            raise HTTPException(
                status_code=422,
                detail={"detail": "Discount expired or not applicable", "invalid_items": invalid_items},
            )

        receipt, is_new = self.receipt_repo.create(
            session,
            receipt_id=receipt_id,
            loyalty_card_id=data.loyalty_card_id,
            store_id=data.store_id,
            channel=data.channel,
            payment_card_uid=data.payment_card_uid,
            items=items_data,
        )

        # Kick off background processing of this receipt (task progress + generation).
        # Fire-and-forget: does not block the API response (FR-012).
        if is_new and data.loyalty_card_id is not None:
            try:
                from webx5.tasks.receipt import process_receipt

                process_receipt.apply_async(args=[str(receipt.id)], queue="receipts")
            except Exception:  # noqa: BLE001 — Celery/Redis outage must not fail the API write
                pass

        return receipt, is_new
