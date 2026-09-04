from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webx5.entities.base import Base


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint("channel IN ('online', 'offline')", name="ck_receipts_channel"),
        CheckConstraint(
            "cashback_applied_points >= 0", name="ck_receipts_cashback_points_nonneg"
        ),
        CheckConstraint(
            "cashback_applied_rub >= 0", name="ck_receipts_cashback_rub_nonneg"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    purchase_date: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )
    payment_card_uid: Mapped[str | None] = mapped_column(String(200), nullable=True)
    loyalty_card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="offline")
    cashback_applied_points: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cashback_applied_rub: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    points_rate_at_purchase: Mapped[int | None] = mapped_column(Integer, nullable=True)

    items: Mapped[list[ReceiptItem]] = relationship(back_populates="receipt", lazy="select")


class ReceiptItem(Base):
    __tablename__ = "receipt_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_receipt_items_quantity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    base_price_at_purchase: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    paid_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    discounted_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    discount_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discounts.id", ondelete="SET NULL"), nullable=True
    )

    receipt: Mapped[Receipt] = relationship(back_populates="items")
