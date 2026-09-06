from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey

from webx5.entities.base import Base


class GiftReward(Base):
    __tablename__ = "gift_reward"
    __table_args__ = (
        CheckConstraint("criterion_type IN ('product', 'category')", name="ck_gift_reward_criterion_type"),
        CheckConstraint("quantity >= 1", name="ck_gift_reward_quantity"),
        CheckConstraint("status IN ('active', 'used', 'expired')", name="ck_gift_reward_status"),
        Index("ix_gift_reward_user_status", "loyalty_card_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task.id", ondelete="SET NULL"), nullable=True
    )
    loyalty_card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    criterion_type: Mapped[str] = mapped_column(String(20), nullable=False)
    criterion_entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    related_spin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wheel_spin.id", ondelete="SET NULL"), nullable=True
    )
