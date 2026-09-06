from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webx5.entities.base import Base


class ReferralCode(Base):
    __tablename__ = "referral_code"
    __table_args__ = (
        UniqueConstraint("code", name="uq_referral_code_code"),
        CheckConstraint("code ~ '^[A-Za-z0-9]{6}$'", name="ck_referral_code_format"),
        Index("ix_referral_code_inviter_created", "inviter_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    inviter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    link: Mapped[ReferralLink | None] = relationship(
        back_populates="code_row", uselist=False, lazy="select"
    )


class ReferralLink(Base):
    __tablename__ = "referral_link"
    __table_args__ = (
        UniqueConstraint("referral_code_id", name="uq_referral_link_code"),
        CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 100",
            name="ck_referral_link_discount_pct",
        ),
        CheckConstraint("inviter_coupons >= 0", name="ck_referral_link_coupons"),
        CheckConstraint("inviter_cashback_rub >= 0", name="ck_referral_link_cashback"),
        CheckConstraint(
            "reward_status IN ('awaiting_purchase', 'rewarded')",
            name="ck_referral_link_reward_status",
        ),
        CheckConstraint("inviter_id <> invitee_id", name="ck_referral_link_not_self"),
        Index("ix_referral_link_invitee_activated", "invitee_id", "activated_at"),
        Index("ix_referral_link_inviter_activated", "inviter_id", "activated_at"),
        Index(
            "ux_referral_link_qualifying_receipt",
            "qualifying_receipt_id",
            unique=True,
            postgresql_where=text("qualifying_receipt_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    referral_code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("referral_code.id", ondelete="RESTRICT"), nullable=False
    )
    inviter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    invitee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    inviter_coupons: Mapped[int] = mapped_column(Integer, nullable=False)
    inviter_cashback_rub: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_valid_to: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    purchase_window_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    discount_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discounts.id", ondelete="SET NULL"), nullable=True
    )
    reward_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="awaiting_purchase", server_default="awaiting_purchase"
    )
    qualifying_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("receipts.id", ondelete="SET NULL"), nullable=True
    )
    rewarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    code_row: Mapped[ReferralCode] = relationship(back_populates="link")
