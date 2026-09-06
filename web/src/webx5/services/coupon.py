from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webx5.crud.coupon import CouponRepository
from webx5.entities.coupon import CouponTransaction
from webx5.entities.task import Task

logger = structlog.get_logger("coupon")


class CouponService:
    def __init__(
        self,
        repo: CouponRepository,
        weekly_n: Callable[[], int],
        week_start: Callable[[], date],
    ) -> None:
        self._repo = repo
        self._weekly_n = weekly_n
        self._week_start = week_start

    def get_or_create_account(self, session: Session, user_id: uuid.UUID):
        return self._repo.get_or_create_account(session, user_id)

    def get_balance(self, session: Session, user_id: uuid.UUID) -> int:
        account = self._repo.get_or_create_account(session, user_id)
        return int(account.balance)

    def list_transactions(
        self,
        session: Session,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[CouponTransaction], int]:
        account = self._repo.get_or_create_account(session, user_id)
        items = self._repo.list_transactions(session, account.id, limit, offset)
        total = self._repo.count_transactions(session, account.id)
        return items, total

    def ensure_weekly_grant(
        self,
        session: Session,
        user_id: uuid.UUID,
        week_start: date | None = None,
    ) -> int:
        n = self._weekly_n()
        week = week_start or self._week_start()
        account = self._repo.lock_account_for_update(session, user_id)
        if self._repo.has_weekly_grant(session, account.id, week):
            return 0
        if n <= 0:
            return 0
        nested = session.begin_nested()
        try:
            self._repo.insert_transaction(
                session,
                account_id=account.id,
                type="weekly_grant",
                amount=n,
                week_start=week,
            )
            nested.commit()
        except IntegrityError:
            nested.rollback()
            return 0
        self._repo.bump_balance(session, account, n)
        logger.info(
            "coupon.weekly_grant",
            loyalty_card_id=str(user_id),
            amount=n,
            week_start=str(week),
            new_balance=account.balance,
        )
        return n

    def debit_for_spin(
        self, session: Session, user_id: uuid.UUID, spin_id: uuid.UUID
    ) -> bool:
        account = self._repo.lock_account_for_update(session, user_id)
        if account.balance < 1:
            logger.info(
                "coupon.spin_denied",
                loyalty_card_id=str(user_id),
                reason="insufficient",
                balance=account.balance,
            )
            return False
        self._repo.debit_balance(session, account, 1)
        self._repo.insert_transaction(
            session,
            account_id=account.id,
            type="spin",
            amount=-1,
            related_spin_id=spin_id,
        )
        return True

    def award_for_task(self, session: Session, task: Task) -> int:
        if self._repo.has_task_grant(session, task.id):
            return 0
        account = self._repo.get_or_create_account(session, task.loyalty_card_id)
        nested = session.begin_nested()
        try:
            self._repo.insert_transaction(
                session,
                account_id=account.id,
                type="task_complete",
                amount=1,
                related_task_id=task.id,
            )
            nested.commit()
        except IntegrityError:
            nested.rollback()
            return 0
        self._repo.bump_balance(session, account, 1)
        logger.info(
            "coupon.task_complete",
            loyalty_card_id=str(task.loyalty_card_id),
            task_id=str(task.id),
            new_balance=account.balance,
        )
        return 1

    def award_for_referral(
        self,
        session: Session,
        inviter_id: uuid.UUID,
        amount: int,
        referral_link_id: uuid.UUID,
    ) -> int:
        if amount <= 0:
            return 0
        account = self._repo.lock_account_for_update(session, inviter_id)
        nested = session.begin_nested()
        try:
            self._repo.insert_transaction(
                session,
                account_id=account.id,
                type="referral",
                amount=amount,
                related_referral_link_id=referral_link_id,
            )
            nested.commit()
        except IntegrityError:
            nested.rollback()
            return 0
        self._repo.bump_balance(session, account, amount)
        logger.info(
            "coupon.referral",
            loyalty_card_id=str(inviter_id),
            referral_link_id=str(referral_link_id),
            amount=amount,
            new_balance=account.balance,
        )
        return amount
