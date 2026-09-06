from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webx5.crud.coupon import CouponRepository
from webx5.entities.coupon import CouponTransaction

logger = structlog.get_logger("coupon")

RUB_PER_COUPON = 1000


class CouponService:
    def __init__(self, repo: CouponRepository) -> None:
        self._repo = repo

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

    def award_for_purchase(
        self,
        session: Session,
        user_id: uuid.UUID,
        paid_rub: int,
        receipt_id: uuid.UUID,
    ) -> int:
        if paid_rub <= 0:
            return 0
        account = self._repo.lock_account_for_update(session, user_id)
        if self._repo.has_purchase_grant(session, receipt_id):
            return 0
        pool = int(account.spend_remainder_rub) + paid_rub
        coupons = pool // RUB_PER_COUPON
        new_remainder = pool % RUB_PER_COUPON
        if coupons > 0:
            nested = session.begin_nested()
            try:
                self._repo.insert_transaction(
                    session,
                    account_id=account.id,
                    type="purchase",
                    amount=coupons,
                    related_receipt_id=receipt_id,
                )
                nested.commit()
            except IntegrityError:
                nested.rollback()
                return 0
            self._repo.bump_balance(session, account, coupons)
        account.spend_remainder_rub = new_remainder
        account.updated_at = datetime.now(UTC)
        session.flush()
        logger.info(
            "coupon.purchase",
            loyalty_card_id=str(user_id),
            receipt_id=str(receipt_id),
            paid_rub=paid_rub,
            amount=coupons,
            remainder_rub=new_remainder,
            new_balance=account.balance,
        )
        return coupons
