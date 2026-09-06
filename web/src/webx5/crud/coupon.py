from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from webx5.entities.coupon import CouponAccount, CouponTransaction


class CouponRepository:
    def get_or_create_account(
        self, session: Session, loyalty_card_id: uuid.UUID
    ) -> CouponAccount:
        stmt = (
            pg_insert(CouponAccount)
            .values(loyalty_card_id=loyalty_card_id)
            .on_conflict_do_nothing(index_elements=["loyalty_card_id"])
        )
        session.execute(stmt)
        session.flush()
        return session.execute(
            select(CouponAccount).where(CouponAccount.loyalty_card_id == loyalty_card_id)
        ).scalar_one()

    def lock_account_for_update(
        self, session: Session, loyalty_card_id: uuid.UUID
    ) -> CouponAccount:
        self.get_or_create_account(session, loyalty_card_id)
        return session.execute(
            select(CouponAccount)
            .where(CouponAccount.loyalty_card_id == loyalty_card_id)
            .with_for_update()
        ).scalar_one()

    def bump_balance(
        self, session: Session, account: CouponAccount, delta: int
    ) -> CouponAccount:
        account.balance = account.balance + delta
        account.updated_at = datetime.now(UTC)
        session.flush()
        return account

    def debit_balance(
        self, session: Session, account: CouponAccount, amount: int
    ) -> CouponAccount:
        account.balance = account.balance - amount
        account.updated_at = datetime.now(UTC)
        session.flush()
        return account

    def insert_transaction(
        self,
        session: Session,
        *,
        account_id: uuid.UUID,
        type: str,
        amount: int,
        related_task_id: uuid.UUID | None = None,
        related_spin_id: uuid.UUID | None = None,
        related_referral_link_id: uuid.UUID | None = None,
        related_receipt_id: uuid.UUID | None = None,
        week_start: date | None = None,
    ) -> CouponTransaction:
        tx = CouponTransaction(
            coupon_account_id=account_id,
            type=type,
            amount=amount,
            related_task_id=related_task_id,
            related_spin_id=related_spin_id,
            related_referral_link_id=related_referral_link_id,
            related_receipt_id=related_receipt_id,
            week_start=week_start,
        )
        session.add(tx)
        session.flush()
        return tx

    def has_weekly_grant(
        self, session: Session, account_id: uuid.UUID, week_start: date
    ) -> bool:
        row = session.execute(
            select(CouponTransaction.id).where(
                CouponTransaction.coupon_account_id == account_id,
                CouponTransaction.type == "weekly_grant",
                CouponTransaction.week_start == week_start,
            )
        ).first()
        return row is not None

    def has_task_grant(self, session: Session, task_id: uuid.UUID) -> bool:
        row = session.execute(
            select(CouponTransaction.id).where(
                CouponTransaction.type == "task_complete",
                CouponTransaction.related_task_id == task_id,
            )
        ).first()
        return row is not None

    def has_purchase_grant(self, session: Session, receipt_id: uuid.UUID) -> bool:
        row = session.execute(
            select(CouponTransaction.id).where(
                CouponTransaction.type == "purchase",
                CouponTransaction.related_receipt_id == receipt_id,
            )
        ).first()
        return row is not None

    def list_transactions(
        self,
        session: Session,
        account_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> list[CouponTransaction]:
        rows = session.execute(
            select(CouponTransaction)
            .where(CouponTransaction.coupon_account_id == account_id)
            .order_by(CouponTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars().all()
        return list(rows)

    def count_transactions(self, session: Session, account_id: uuid.UUID) -> int:
        return int(
            session.execute(
                select(func.count(CouponTransaction.id)).where(
                    CouponTransaction.coupon_account_id == account_id
                )
            ).scalar_one()
        )
