from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from webx5.crud.points import PointsRepository
from webx5.entities.task import Task
from webx5.services.points_applier import (
    CashbackResult,
    apply_cashback,
    resolve_points_to_spend,
)

logger = structlog.get_logger("points")


@dataclass(frozen=True)
class CashbackPreview:
    points_available: int
    points_to_apply: int
    cashback_rub: int
    total_paid_rub: int
    points_balance_after: int
    points_capped_by: Literal["none", "balance", "receipt_total"]
    rate_points_per_rub: int


@dataclass(frozen=True)
class BalanceView:
    balance: int
    rate_points_per_rub: int
    balance_rub_equivalent: int


class PointsService:
    def __init__(self, repo: PointsRepository) -> None:
        self._repo = repo

    def award_for_task(self, session: Session, task: Task) -> int:
        points = int(task.reward_rub)
        if points <= 0:
            logger.info(
                "points.awarded.skipped_zero",
                task_id=str(task.id),
                loyalty_card_id=str(task.loyalty_card_id),
            )
            return 0

        account = self._repo.get_or_create_account(session, task.loyalty_card_id)
        tx = self._repo.insert_earn(session, account.id, task.id, points)
        if tx is None:
            logger.info(
                "points.awarded.duplicate",
                task_id=str(task.id),
                loyalty_card_id=str(task.loyalty_card_id),
            )
            return 0

        self._repo.bump_balance(session, account, points)
        logger.info(
            "points.awarded",
            task_id=str(task.id),
            loyalty_card_id=str(task.loyalty_card_id),
            amount=points,
            new_balance=account.balance,
        )
        return points

    def spend_for_receipt(
        self,
        session: Session,
        loyalty_card_id: uuid.UUID,
        points_requested_raw: int | str | None,
        receipt_subtotal_rub: int,
        receipt_id: uuid.UUID,
    ) -> tuple[int, int, int]:
        """Returns (applied_points, cashback_rub, rate_used)."""
        rate = self._repo.get_rate(session)
        account = self._repo.lock_account_for_update(session, loyalty_card_id)
        points_requested = resolve_points_to_spend(
            points_requested_raw, account.balance
        )
        if isinstance(points_requested_raw, int) and points_requested_raw > account.balance:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient points balance: requested {points_requested_raw}, available {account.balance}",
            )
        result: CashbackResult = apply_cashback(
            subtotal_rub=receipt_subtotal_rub,
            points_requested=points_requested,
            balance=account.balance,
            rate=rate,
        )
        if result.applied_points == 0:
            return (0, 0, rate)
        self._repo.deduct_balance(session, account, result.applied_points)
        self._repo.insert_spend(
            session,
            account.id,
            receipt_id,
            -result.applied_points,
            rate,
        )
        logger.info(
            "points.spent",
            loyalty_card_id=str(loyalty_card_id),
            receipt_id=str(receipt_id),
            applied_points=result.applied_points,
            cashback_rub=result.cashback_rub,
            rate=rate,
            capped_by=result.capped_by,
            new_balance=account.balance,
        )
        return (result.applied_points, result.cashback_rub, rate)

    def set_rate(self, session: Session, new_rate: int) -> int:
        old_rate = self._repo.get_rate(session)
        applied = self._repo.set_rate(session, new_rate)
        logger.info("points.rate_changed", old=old_rate, new=applied)
        return applied

    def get_balance(
        self, session: Session, loyalty_card_id: uuid.UUID
    ) -> BalanceView:
        rate = self._repo.get_rate(session)
        account = self._repo.get_or_create_account(session, loyalty_card_id)
        return BalanceView(
            balance=account.balance,
            rate_points_per_rub=rate,
            balance_rub_equivalent=account.balance // rate,
        )

    def list_transactions(
        self,
        session: Session,
        loyalty_card_id: uuid.UUID,
        limit: int,
        offset: int,
    ):
        account = self._repo.get_or_create_account(session, loyalty_card_id)
        items = self._repo.list_transactions(session, account.id, limit, offset)
        total = self._repo.count_transactions(session, account.id)
        return items, total

    def preview_for_calculate(
        self,
        session: Session,
        loyalty_card_id: uuid.UUID | None,
        points_requested_raw: int | str | None,
        subtotal_rub: int,
    ) -> CashbackPreview | None:
        if loyalty_card_id is None:
            return None
        rate = self._repo.get_rate(session)
        account = self._repo.get_or_create_account(session, loyalty_card_id)
        try:
            points_requested = resolve_points_to_spend(
                points_requested_raw, account.balance
            )
        except ValueError:
            points_requested = 0
        result = apply_cashback(
            subtotal_rub=subtotal_rub,
            points_requested=points_requested,
            balance=account.balance,
            rate=rate,
        )
        return CashbackPreview(
            points_available=account.balance,
            points_to_apply=result.applied_points,
            cashback_rub=result.cashback_rub,
            total_paid_rub=max(subtotal_rub - result.cashback_rub, 0),
            points_balance_after=account.balance - result.applied_points,
            points_capped_by=result.capped_by,
            rate_points_per_rub=rate,
        )
