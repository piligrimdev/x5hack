from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webx5.entities.base import Base


class DiscountType(Base):
    __tablename__ = "discount_types"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class DiscountLinkType(Base):
    __tablename__ = "discount_link_types"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class Discount(Base):
    __tablename__ = "discounts"
    __table_args__ = (
        CheckConstraint("scope IN ('all', 'by_format', 'by_store')", name="ck_discounts_scope"),
        CheckConstraint("value >= 0", name="ck_discounts_value_nonneg"),
        CheckConstraint("value_type IN ('percent', 'fixed_rub')", name="ck_discounts_value_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    value: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    value_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="percent", server_default="percent"
    )
    discount_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discount_types.id", ondelete="RESTRICT"), nullable=False
    )
    link_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discount_link_types.id", ondelete="RESTRICT"), nullable=False
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    loyalty_card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    link_task_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    min_loyalty_level: Mapped[int | None] = mapped_column(nullable=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="all", index=True)
    valid_from: Mapped[datetime | None] = mapped_column(nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)

    discount_type: Mapped[DiscountType] = relationship(lazy="joined")
    link_type: Mapped[DiscountLinkType] = relationship(lazy="joined")
    format_discounts: Mapped[list[FormatDiscount]] = relationship(back_populates="discount", lazy="select")
    store_discounts: Mapped[list[StoreDiscount]] = relationship(back_populates="discount", lazy="select")


class FormatDiscount(Base):
    __tablename__ = "format_discounts"

    discount_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discounts.id", ondelete="CASCADE"), primary_key=True
    )
    format_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("store_formats.id", ondelete="CASCADE"), primary_key=True
    )

    discount: Mapped[Discount] = relationship(back_populates="format_discounts")


class StoreDiscount(Base):
    __tablename__ = "store_discounts"

    discount_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discounts.id", ondelete="CASCADE"), primary_key=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True
    )

    discount: Mapped[Discount] = relationship(back_populates="store_discounts")
