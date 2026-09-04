from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webx5.entities.discount import Discount, DiscountLinkType, DiscountType
from webx5.entities.task import Task, TaskCriterion, TaskReceiptIncrement, TaskStatus


STATUS_OPEN = "открыто"
STATUS_COMPLETED = "выполнено"
STATUS_FAILED = "провалено"
STATUS_EXPIRED = "истекло"


class TaskRepository:
    # --- status helpers ---
    def get_status_id(self, session: Session, name: str) -> uuid.UUID:
        row = session.execute(select(TaskStatus).where(TaskStatus.name == name)).scalar_one()
        return row.id

    # --- reads ---
    def get_active_for_user(self, session: Session, user_id: uuid.UUID) -> list[Task]:
        open_id = self.get_status_id(session, STATUS_OPEN)
        rows = session.execute(
            select(Task)
            .where(Task.loyalty_card_id == user_id, Task.task_status_id == open_id)
            .order_by(Task.issued_at.asc())
        ).scalars().all()
        return list(rows)

    def count_active_for_user(self, session: Session, user_id: uuid.UUID) -> int:
        open_id = self.get_status_id(session, STATUS_OPEN)
        return session.execute(
            select(func.count(Task.id)).where(
                Task.loyalty_card_id == user_id, Task.task_status_id == open_id
            )
        ).scalar_one()

    def get_by_id(self, session: Session, task_id: uuid.UUID) -> Task | None:
        return session.get(Task, task_id)

    def get_task_criteria(self, session: Session, task_id: uuid.UUID) -> list[TaskCriterion]:
        return list(
            session.execute(select(TaskCriterion).where(TaskCriterion.task_id == task_id)).scalars().all()
        )

    # --- creates ---
    def create(
        self,
        session: Session,
        *,
        loyalty_card_id: uuid.UUID,
        criterion_type: str,
        criterion_entity_id: uuid.UUID,
        quantity_target: int,
        title: str,
        description: str,
        mechanic: str,
        reward_rub: Decimal,
        reasoning: str | None,
        path: str,
        model: str | None,
        deadline: datetime | None = None,
    ) -> Task:
        open_status_id = self.get_status_id(session, STATUS_OPEN)
        if deadline is None:
            deadline = datetime.now(timezone.utc) + timedelta(days=7)
        task = Task(
            loyalty_card_id=loyalty_card_id,
            task_status_id=open_status_id,
            deadline=deadline,
            criterion_type=criterion_type,
            criterion_entity_id=criterion_entity_id,
            quantity_target=quantity_target,
            quantity_current=0,
            title=title,
            description=description,
            mechanic=mechanic,
            reward_rub=reward_rub,
            reasoning=reasoning,
            path=path,
            model=model,
            reward_type="discount",
        )
        session.add(task)
        session.flush()
        return task

    def create_criterion(
        self,
        session: Session,
        *,
        task_id: uuid.UUID,
        kind: str,
        value_num: Decimal | None = None,
        value_text: str | None = None,
        key: str | None = None,
    ) -> TaskCriterion:
        crit = TaskCriterion(
            task_id=task_id, kind=kind, key=key, value_num=value_num, value_text=value_text
        )
        session.add(crit)
        session.flush()
        return crit

    # --- lifecycle ---
    def record_increment(
        self, session: Session, task_id: uuid.UUID, receipt_id: uuid.UUID
    ) -> bool:
        """Try to record that `receipt` was applied to `task`. Returns True if inserted,
        False if the (task_id, receipt_id) pair already exists (dedupe via PK conflict).
        """
        row = TaskReceiptIncrement(task_id=task_id, receipt_id=receipt_id)
        session.add(row)
        try:
            session.flush()
            return True
        except IntegrityError:
            session.rollback()
            return False

    def bump_progress(
        self, session: Session, task: Task, delta: int
    ) -> Task:
        task.quantity_current = min(task.quantity_current + delta, task.quantity_target)
        session.flush()
        return task

    def mark_completed(
        self, session: Session, task: Task, reward_id: uuid.UUID
    ) -> Task:
        completed_status_id = self.get_status_id(session, STATUS_COMPLETED)
        task.task_status_id = completed_status_id
        task.completed_at = datetime.now(timezone.utc)
        task.reward_id = reward_id
        session.flush()
        return task

    def expire_overdue(self, session: Session, batch_size: int = 100) -> list[Task]:
        open_id = self.get_status_id(session, STATUS_OPEN)
        expired_id = self.get_status_id(session, STATUS_EXPIRED)
        overdue = (
            session.execute(
                select(Task)
                .where(Task.task_status_id == open_id, Task.deadline < func.now())
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        for task in overdue:
            task.task_status_id = expired_id
        session.flush()
        return list(overdue)

    # --- reward creation (Discount) ---
    def create_reward_discount(
        self, session: Session, task: Task, valid_to_days: int = 7
    ) -> Discount:
        # Look up dictionary FKs
        personal_type_id = session.execute(
            select(DiscountType.id).where(DiscountType.name == "персональная")
        ).scalar_one()
        # criterion_type ('product'/'category'/'brand') → discount_link_types row
        link_type_id = session.execute(
            select(DiscountLinkType.id).where(DiscountLinkType.name == task.criterion_type)
        ).scalar_one()

        now = datetime.now(timezone.utc)
        discount = Discount(
            value=task.reward_rub,
            value_type="fixed_rub",
            discount_type_id=personal_type_id,
            link_type_id=link_type_id,
            entity_id=task.criterion_entity_id,
            loyalty_card_id=task.loyalty_card_id,
            link_task_id=task.id,
            scope="all",
            valid_from=now,
            valid_to=now + timedelta(days=valid_to_days),
        )
        session.add(discount)
        session.flush()
        return discount
