from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from webx5.entities.discount import Discount, DiscountLinkType, DiscountType, FormatDiscount, StoreDiscount
from webx5.entities.store import Store


class DiscountRepository:
    def find_applicable_for_cart(
        self,
        session: Session,
        product_infos: list[dict],
        store: Store,
    ) -> list[Discount]:
        """Return all candidate discounts for the cart.

        product_infos: list of {"product_id": UUID, "category_id": UUID, "brand_id": UUID | None}
        Filters by date and scope. Caller applies best-price-wins per product.
        """
        now = datetime.now(timezone.utc)
        date_filter = and_(
            or_(Discount.valid_from.is_(None), Discount.valid_from <= now),
            or_(Discount.valid_to.is_(None), Discount.valid_to >= now),
        )

        entity_ids = set()
        for info in product_infos:
            entity_ids.add(info["product_id"])
            entity_ids.add(info["category_id"])
            if info.get("brand_id"):
                entity_ids.add(info["brand_id"])

        # Discounts tied to specific entities
        stmt = (
            select(Discount)
            .where(Discount.entity_id.in_(entity_ids))
            .where(date_filter)
        )
        candidates = list(session.scalars(stmt))

        # Discounts with link_type="all" (apply to every product in cart)
        all_link_type = session.scalar(select(DiscountLinkType).where(DiscountLinkType.name == "all"))
        if all_link_type:
            all_scope_stmt = select(Discount).where(
                Discount.link_type_id == all_link_type.id,
                date_filter,
            )
            candidates += list(session.scalars(all_scope_stmt))

        # Filter by scope
        result = []
        for d in candidates:
            if d.scope == "all":
                result.append(d)
            elif d.scope == "by_format":
                fd_stmt = select(FormatDiscount).where(
                    FormatDiscount.discount_id == d.id,
                    FormatDiscount.format_id == store.format_id,
                )
                if session.scalar(fd_stmt) is not None:
                    result.append(d)
            elif d.scope == "by_store":
                sd_stmt = select(StoreDiscount).where(
                    StoreDiscount.discount_id == d.id,
                    StoreDiscount.store_id == store.id,
                )
                if session.scalar(sd_stmt) is not None:
                    result.append(d)
        return result

    def get_by_id(self, session: Session, discount_id: uuid.UUID) -> Discount | None:
        return session.get(Discount, discount_id)

    def list_active(
        self,
        session: Session,
        entity_id: uuid.UUID | None = None,
        link_type_name: str | None = None,
    ) -> list[Discount]:
        now = datetime.now(timezone.utc)
        stmt = select(Discount).where(
            and_(
                or_(Discount.valid_from.is_(None), Discount.valid_from <= now),
                or_(Discount.valid_to.is_(None), Discount.valid_to >= now),
            )
        )
        if entity_id:
            stmt = stmt.where(Discount.entity_id == entity_id)
        if link_type_name:
            stmt = stmt.join(Discount.link_type).where(DiscountLinkType.name == link_type_name)
        return list(session.scalars(stmt))

    def list_types(self, session: Session) -> list[DiscountType]:
        return list(session.scalars(select(DiscountType).order_by(DiscountType.name)))

    def get_link_type_by_name(self, session: Session, name: str) -> DiscountLinkType | None:
        return session.scalar(select(DiscountLinkType).where(DiscountLinkType.name == name))

    def get_type_by_name(self, session: Session, name: str) -> DiscountType | None:
        return session.scalar(select(DiscountType).where(DiscountType.name == name))

    def create(self, session: Session, data: dict) -> Discount:
        discount = Discount(
            id=uuid.uuid4(),
            value=data["value"],
            discount_type_id=data["discount_type_id"],
            link_type_id=data["link_type_id"],
            entity_id=data.get("entity_id"),
            loyalty_card_id=data.get("loyalty_card_id"),
            min_loyalty_level=data.get("min_loyalty_level"),
            scope=data.get("scope", "all"),
            valid_from=data.get("valid_from"),
            valid_to=data.get("valid_to"),
        )
        session.add(discount)
        session.flush()

        for format_id in data.get("format_ids", []):
            session.add(FormatDiscount(discount_id=discount.id, format_id=format_id))
        for store_id in data.get("store_ids", []):
            session.add(StoreDiscount(discount_id=discount.id, store_id=store_id))

        session.commit()
        session.refresh(discount)
        return discount

    def update(self, session: Session, discount_id: uuid.UUID, data: dict) -> Discount | None:
        discount = session.get(Discount, discount_id)
        if not discount:
            return None
        for field in ("value", "scope", "valid_from", "valid_to"):
            if field in data:
                setattr(discount, field, data[field])
        if "format_ids" in data:
            session.query(FormatDiscount).filter(FormatDiscount.discount_id == discount_id).delete()
            for fid in data["format_ids"]:
                session.add(FormatDiscount(discount_id=discount_id, format_id=fid))
        if "store_ids" in data:
            session.query(StoreDiscount).filter(StoreDiscount.discount_id == discount_id).delete()
            for sid in data["store_ids"]:
                session.add(StoreDiscount(discount_id=discount_id, store_id=sid))
        session.commit()
        session.refresh(discount)
        return discount

    def get_or_create_by_category_and_pct(
        self,
        session: Session,
        category_id: uuid.UUID,
        discount_pct: Decimal,
        discount_type_id: uuid.UUID,
        link_type_id: uuid.UUID,
    ) -> Discount:
        stmt = select(Discount).where(
            Discount.entity_id == category_id,
            Discount.value == discount_pct,
            Discount.link_type_id == link_type_id,
        )
        existing = session.scalar(stmt)
        if existing:
            return existing
        discount = Discount(
            id=uuid.uuid4(),
            value=discount_pct,
            discount_type_id=discount_type_id,
            link_type_id=link_type_id,
            entity_id=category_id,
            scope="all",
        )
        session.add(discount)
        session.flush()
        return discount
