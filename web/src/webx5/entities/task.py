from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, PrimaryKeyConstraint, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webx5.entities.base import Base


class TaskStatus(Base):
    __tablename__ = "task_status"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class Task(Base):
    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint("criterion_type IN ('product', 'category', 'brand')", name="ck_task_criterion_type"),
        CheckConstraint("quantity_target >= 1", name="ck_task_quantity_target"),
        CheckConstraint("quantity_current >= 0", name="ck_task_quantity_current"),
        CheckConstraint("reward_rub >= 0", name="ck_task_reward_rub"),
        CheckConstraint(
            "path IN ('personal', 'generic', 'generic_fallback', 'no_challenge', 'personal_dry_run')",
            name="ck_task_path",
        ),
        CheckConstraint("reward_type IN ('discount')", name="ck_task_reward_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    loyalty_card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_status_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_status.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    criterion_type: Mapped[str] = mapped_column(String(20), nullable=False)
    criterion_entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    quantity_target: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    quantity_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mechanic: Mapped[str] = mapped_column(String(200), nullable=False)
    reward_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reward_type: Mapped[str] = mapped_column(String(20), nullable=False, default="discount", server_default="discount")
    reward_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    challenge_slot: Mapped[str | None] = mapped_column(String(30), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[TaskStatus] = relationship(lazy="joined")
    criteria: Mapped[list[TaskCriterion]] = relationship(back_populates="task", lazy="select")


class TaskCriterion(Base):
    __tablename__ = "task_criterion"
    __table_args__ = (
        CheckConstraint("value_num IS NOT NULL OR value_text IS NOT NULL", name="ck_task_criterion_value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task: Mapped[Task] = relationship(back_populates="criteria")


class TaskReceiptIncrement(Base):
    __tablename__ = "task_receipt_increment"
    __table_args__ = (
        PrimaryKeyConstraint("task_id", "receipt_id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id", ondelete="CASCADE"), nullable=False)
    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
