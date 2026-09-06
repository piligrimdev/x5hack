from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from webx5.entities.base import Base


class WheelSpin(Base):
    __tablename__ = "wheel_spin"
    __table_args__ = (
        CheckConstraint("prize_type IN ('cashback', 'gift')", name="ck_wheel_spin_prize_type"),
        CheckConstraint("coupons_spent = 1", name="ck_wheel_spin_coupons_spent"),
        Index("ix_wheel_spin_user_created", "loyalty_card_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    loyalty_card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sector_code: Mapped[str] = mapped_column(String(40), nullable=False)
    prize_type: Mapped[str] = mapped_column(String(20), nullable=False)
    prize_label: Mapped[str] = mapped_column(String(200), nullable=False)
    cashback_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gift_reward_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "gift_reward.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_wheel_spin_gift_reward",
        ),
        nullable=True,
    )
    coupons_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
