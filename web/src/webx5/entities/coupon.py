from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webx5.entities.base import Base


class CouponAccount(Base):
    __tablename__ = "coupon_account"
    __table_args__ = (
        UniqueConstraint("loyalty_card_id", name="uq_coupon_account_loyalty_card"),
        CheckConstraint("balance >= 0", name="ck_coupon_account_balance_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    loyalty_card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transactions: Mapped[list[CouponTransaction]] = relationship(
        back_populates="account", lazy="select"
    )


class CouponTransaction(Base):
    __tablename__ = "coupon_transaction"
    __table_args__ = (
        CheckConstraint(
            "type IN ('weekly_grant', 'task_complete', 'spin')",
            name="ck_coupon_tx_type",
        ),
        CheckConstraint("amount <> 0", name="ck_coupon_tx_amount_nonzero"),
        Index("ix_coupon_tx_account_created", "coupon_account_id", "created_at"),
        Index(
            "ux_coupon_tx_weekly",
            "coupon_account_id",
            "week_start",
            unique=True,
            postgresql_where=text("type = 'weekly_grant'"),
        ),
        Index(
            "ux_coupon_tx_task",
            "related_task_id",
            unique=True,
            postgresql_where=text("type = 'task_complete'"),
        ),
        Index(
            "ux_coupon_tx_spin",
            "related_spin_id",
            unique=True,
            postgresql_where=text("type = 'spin'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    coupon_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coupon_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task.id", ondelete="SET NULL"), nullable=True
    )
    related_spin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wheel_spin.id", ondelete="SET NULL"), nullable=True
    )
    week_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    account: Mapped[CouponAccount] = relationship(back_populates="transactions")
