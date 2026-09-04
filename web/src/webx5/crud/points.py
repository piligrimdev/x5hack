from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webx5.entities.points import PointsAccount, PointsSettings, PointsTransaction


class PointsRepository:
    # --- account ---
    def get_or_create_account(
        self, session: Session, loyalty_card_id: uuid.UUID
    ) -> PointsAccount:
        stmt = (
            pg_insert(PointsAccount)
            .values(loyalty_card_id=loyalty_card_id)
            .on_conflict_do_nothing(index_elements=["loyalty_card_id"])
        )
        session.execute(stmt)
        session.flush()
        return session.execute(
            select(PointsAccount).where(PointsAccount.loyalty_card_id == loyalty_card_id)
        ).scalar_one()

    def lock_account_for_update(
        self, session: Session, loyalty_card_id: uuid.UUID
    ) -> PointsAccount:
        self.get_or_create_account(session, loyalty_card_id)
        return session.execute(
            select(PointsAccount)
            .where(PointsAccount.loyalty_card_id == loyalty_card_id)
            .with_for_update()
        ).scalar_one()

    # --- transactions ---
    def insert_earn(
        self,
        session: Session,
        account_id: uuid.UUID,
        task_id: uuid.UUID,
        amount: int,
    ) -> PointsTransaction | None:
        tx = PointsTransaction(
            points_account_id=account_id,
            type="earn",
            amount=amount,
            related_task_id=task_id,
            rate_at_time=None,
        )
        session.add(tx)
        try:
            session.flush()
            return tx
        except IntegrityError:
            session.rollback()
            return None

    def insert_spend(
        self,
        session: Session,
        account_id: uuid.UUID,
        receipt_id: uuid.UUID,
        amount: int,
        rate: int,
    ) -> PointsTransaction:
        tx = PointsTransaction(
            points_account_id=account_id,
            type="spend",
            amount=amount,
            related_receipt_id=receipt_id,
            rate_at_time=rate,
        )
        session.add(tx)
        session.flush()
        return tx

    def bump_balance(
        self, session: Session, account: PointsAccount, delta: int
    ) -> PointsAccount:
        account.balance = account.balance + delta
        account.updated_at = datetime.now(UTC)
        session.flush()
        return account

    def deduct_balance(
        self, session: Session, account: PointsAccount, points: int
    ) -> PointsAccount:
        account.balance = account.balance - points
        account.updated_at = datetime.now(UTC)
        session.flush()
        return account

    def list_transactions(
        self,
        session: Session,
        account_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> list[PointsTransaction]:
        rows = session.execute(
            select(PointsTransaction)
            .where(PointsTransaction.points_account_id == account_id)
            .order_by(PointsTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars().all()
        return list(rows)

    def count_transactions(self, session: Session, account_id: uuid.UUID) -> int:
        return int(
            session.execute(
                select(func.count(PointsTransaction.id)).where(
                    PointsTransaction.points_account_id == account_id
                )
            ).scalar_one()
        )

    # --- settings ---
    def get_rate(self, session: Session) -> int:
        return int(
            session.execute(
                select(PointsSettings.rate_points_per_rub).where(PointsSettings.id == 1)
            ).scalar_one()
        )

    def set_rate(self, session: Session, new_rate: int) -> int:
        settings = session.execute(
            select(PointsSettings).where(PointsSettings.id == 1)
        ).scalar_one()
        settings.rate_points_per_rub = new_rate
        settings.updated_at = datetime.now(UTC)
        session.flush()
        return int(settings.rate_points_per_rub)
