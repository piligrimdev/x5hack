from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
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


class PointsAccount(Base):
    __tablename__ = "points_account"
    __table_args__ = (
        UniqueConstraint("loyalty_card_id", name="uq_points_account_loyalty_card"),
        CheckConstraint("balance >= 0", name="ck_points_account_balance_nonneg"),
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

    transactions: Mapped[list[PointsTransaction]] = relationship(
        back_populates="account", lazy="select"
    )


class PointsTransaction(Base):
    __tablename__ = "points_transaction"
    __table_args__ = (
        CheckConstraint("type IN ('earn', 'spend')", name="ck_points_tx_type"),
        CheckConstraint("amount <> 0", name="ck_points_tx_amount_nonzero"),
        Index(
            "ix_points_tx_account_created",
            "points_account_id",
            "created_at",
        ),
        Index(
            "ux_points_tx_earn_task",
            "related_task_id",
            unique=True,
            postgresql_where=text("type = 'earn'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    points_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("points_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task.id", ondelete="SET NULL"), nullable=True
    )
    related_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("receipts.id", ondelete="SET NULL"), nullable=True
    )
    rate_at_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    account: Mapped[PointsAccount] = relationship(back_populates="transactions")


class PointsSettings(Base):
    __tablename__ = "points_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_points_settings_singleton"),
        CheckConstraint("rate_points_per_rub > 0", name="ck_points_settings_rate_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rate_points_per_rub: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
