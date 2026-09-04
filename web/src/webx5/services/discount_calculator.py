from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from webx5.crud.discount import DiscountRepository
from webx5.entities.discount import Discount
from webx5.entities.product import Product
from webx5.entities.store import Store


@dataclass
class CartItem:
    product_id: uuid.UUID
    quantity: int


def _apply_discount(base_price: Decimal, discount: "Discount") -> Decimal:
    """Compute paid price after applying one discount.

    `value_type='percent'` — value is percentage 0..100.
    `value_type='fixed_rub'` — value is a flat ruble amount subtracted from base price.
    """
    value = Decimal(str(discount.value))
    value_type = getattr(discount, "value_type", "percent")
    if value_type == "fixed_rub":
        paid = base_price - value
        if paid < Decimal("0"):
            paid = Decimal("0")
    else:
        paid = base_price * (Decimal("1") - value / Decimal("100"))
    return paid.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class CalculatedItem:
    product_id: uuid.UUID
    product_name: str
    quantity: int
    base_price: Decimal
    paid_price: Decimal
    discount_id: uuid.UUID | None
    discounted_amount: Decimal


class DiscountCalculatorService:
    def __init__(self, discount_repo: DiscountRepository) -> None:
        self.discount_repo = discount_repo

    def calculate(
        self,
        items: list[CartItem],
        store: Store,
        loyalty_card_id: uuid.UUID | None,
        session: Session,
        personal_discount_type_name: str = "персональная",
    ) -> list[CalculatedItem]:
        from sqlalchemy import select as sa_select

        from webx5.entities.discount import DiscountType

        product_ids = [i.product_id for i in items]
        products: dict[uuid.UUID, Product] = {
            p.id: p
            for p in session.scalars(
                __import__("sqlalchemy").select(Product).where(Product.id.in_(product_ids))
            )
        }

        product_infos = [
            {
                "product_id": p.id,
                "category_id": p.category_id,
                "brand_id": p.brand_id,
            }
            for p in products.values()
        ]

        # Get user's loyalty level (0 = anonymous)
        loyalty_level = 0
        if loyalty_card_id:
            from webx5.entities.user import User
            user = session.get(User, loyalty_card_id)
            loyalty_level = user.loyalty_level if user else 0

        all_discounts = self.discount_repo.find_applicable_for_cart(session, product_infos, store)

        # Filter by min_loyalty_level
        all_discounts = [
            d for d in all_discounts
            if d.min_loyalty_level is None or loyalty_level >= d.min_loyalty_level
        ]

        personal_type = session.scalar(
            sa_select(DiscountType).where(DiscountType.name == personal_discount_type_name)
        )
        if personal_type:
            filtered = []
            for d in all_discounts:
                if d.discount_type_id != personal_type.id:
                    filtered.append(d)
                    continue
                # Personal discount: requires loyalty card
                if not loyalty_card_id:
                    continue
                # If targeted to a specific card — must match
                if d.loyalty_card_id is not None and d.loyalty_card_id != loyalty_card_id:
                    continue
                filtered.append(d)
            all_discounts = filtered

        # Separate "all" link type (apply to every product) from entity-specific
        all_link_discounts = [d for d in all_discounts if d.entity_id is None]
        entity_discounts = [d for d in all_discounts if d.entity_id is not None]

        # Build lookup: entity_id → discounts list
        by_entity: dict[uuid.UUID, list[Discount]] = {}
        for d in entity_discounts:
            by_entity.setdefault(d.entity_id, []).append(d)

        result = []
        for item in items:
            product = products.get(item.product_id)
            if product is None:
                continue

            base_price = Decimal(str(product.current_price))
            candidates = (
                by_entity.get(item.product_id, [])
                + by_entity.get(product.category_id, [])
                + all_link_discounts  # applies to every product
            )
            if product.brand_id:
                candidates += by_entity.get(product.brand_id, [])

            # Deduplicate
            seen: set[uuid.UUID] = set()
            unique_candidates = []
            for d in candidates:
                if d.id not in seen:
                    seen.add(d.id)
                    unique_candidates.append(d)

            best_discount: Discount | None = None
            best_paid = base_price

            for d in unique_candidates:
                paid = _apply_discount(base_price, d)
                if paid < best_paid:
                    best_paid = paid
                    best_discount = d

            discounted_amount = (base_price - best_paid).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            result.append(
                CalculatedItem(
                    product_id=item.product_id,
                    product_name=product.name,
                    quantity=item.quantity,
                    base_price=base_price,
                    paid_price=best_paid,
                    discount_id=best_discount.id if best_discount else None,
                    discounted_amount=discounted_amount,
                )
            )

        return result
