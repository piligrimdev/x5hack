from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from webx5.crud.discount import DiscountRepository
from webx5.crud.receipt import ReceiptRepository
from webx5.entities.receipt import Receipt
from webx5.schemas.receipt import ReceiptCreate, ReceiptItemResponse, ReceiptResponse


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

        # Anonymous receipts cannot spend points (FR-011).
        wants_points = data.points_to_spend not in (None, 0)
        if wants_points and data.loyalty_card_id is None:
            raise HTTPException(
                status_code=422,
                detail="Cashback points can only be spent with a loyalty card",
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

        # Spend cashback points atomically with the receipt insert (FR-008, FR-010).
        # Skip on idempotent replay (is_new=False) — the original amount is already stored.
        if is_new and wants_points and data.loyalty_card_id is not None:
            from webx5.core.points import points_service

            subtotal_rub = int(
                sum(
                    Decimal(str(item["paid_price"])) * item["quantity"]
                    for item in items_data
                )
            )
            applied_points, cashback_rub, rate = points_service.spend_for_receipt(
                session,
                loyalty_card_id=data.loyalty_card_id,
                points_requested_raw=data.points_to_spend,
                receipt_subtotal_rub=subtotal_rub,
                receipt_id=receipt.id,
            )
            if applied_points > 0:
                receipt.cashback_applied_points = applied_points
                receipt.cashback_applied_rub = cashback_rub
                receipt.points_rate_at_purchase = rate
                session.flush()

        session.commit()
        session.refresh(receipt)

        # Kick off background processing of this receipt (task progress + generation).
        # Fire-and-forget: does not block the API response (FR-012).
        if is_new and data.loyalty_card_id is not None:
            try:
                from webx5.tasks.receipt import process_receipt

                process_receipt.apply_async(args=[str(receipt.id)], queue="receipts")
            except Exception:  # noqa: BLE001 — Celery/Redis outage must not fail the API write
                pass

        return receipt, is_new

    def build_receipt_response(self, session: Session, receipt: Receipt) -> ReceiptResponse:
        items_with_products = self.receipt_repo.get_items_with_products(session, receipt.id)

        item_responses = [
            ReceiptItemResponse(
                id=ri.id,
                product_id=ri.product_id,
                quantity=ri.quantity,
                base_price_at_purchase=Decimal(str(ri.base_price_at_purchase)),
                paid_price=Decimal(str(ri.paid_price)),
                discounted_amount=Decimal(str(ri.discounted_amount)),
                discount_id=ri.discount_id,
            )
            for ri, _product in items_with_products
        ]

        total_base = sum(i.base_price_at_purchase * i.quantity for i in item_responses)
        total_paid_before_cashback = sum(i.paid_price * i.quantity for i in item_responses)
        cashback_rub = Decimal(str(receipt.cashback_applied_rub))
        discount_saved = total_base - total_paid_before_cashback
        total_paid = max(total_paid_before_cashback - cashback_rub, Decimal("0"))

        return ReceiptResponse(
            id=receipt.id,
            purchase_date=receipt.purchase_date,
            store_id=receipt.store_id,
            loyalty_card_id=receipt.loyalty_card_id,
            channel=receipt.channel,
            items=item_responses,
            total_base=total_base,
            total_paid=total_paid,
            total_saved=discount_saved + cashback_rub,
            discount_saved_rub=discount_saved,
            cashback_applied_points=int(receipt.cashback_applied_points),
            cashback_applied_rub=int(receipt.cashback_applied_rub),
            points_rate_at_purchase=(
                int(receipt.points_rate_at_purchase)
                if receipt.points_rate_at_purchase is not None
                else None
            ),
        )
