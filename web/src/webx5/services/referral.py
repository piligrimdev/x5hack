from __future__ import annotations

import re
import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

import structlog
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webx5.crud.discount import DiscountRepository
from webx5.crud.referral import ReferralRepository
from webx5.entities.discount import Discount
from webx5.entities.referral import ReferralCode, ReferralLink
from webx5.schemas.referral import ReferralOut, ReferralStatus
from webx5.services.coupon import CouponService
from webx5.services.points import PointsService

logger = structlog.get_logger("referral")

CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
CODE_RE = re.compile(r"^[A-Za-z0-9]{6}$")
ISSUE_ATTEMPTS = 8
WINDOW_DAYS = 7
INACTIVE_DAYS = 180

ERR_FORMAT = "Некорректный формат кода"
ERR_NOT_FOUND = "Код не найден"
ERR_USED = "Код уже использован"
ERR_SELF = "Нельзя пригласить себя"
ERR_ACTIVE = "Реферальная скидка уже действует"
ERR_RECENT = "Реактивация недоступна: недавно были покупки. Войдите без кода"
ERR_ISSUE = "Не удалось выдать уникальный код"


class ReferralService:
    def __init__(
        self,
        repo: ReferralRepository,
        discount_repo: DiscountRepository,
        coupon_service: CouponService,
        points_service: PointsService,
        settings: Callable[[], tuple[Decimal, int, int]],
        clock: Callable[[datetime | None], datetime],
    ) -> None:
        self._repo = repo
        self._discount_repo = discount_repo
        self._coupon_service = coupon_service
        self._points_service = points_service
        self._settings = settings
        self._clock = clock

    def issue(self, session: Session, inviter_id: uuid.UUID) -> ReferralCode:
        last_error: Exception | None = None
        for _ in range(ISSUE_ATTEMPTS):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            nested = session.begin_nested()
            try:
                row = self._repo.insert_code(session, inviter_id, code)
                nested.commit()
                logger.info(
                    "referral.issued",
                    inviter_id=str(inviter_id),
                    code=code,
                )
                return row
            except IntegrityError as exc:
                nested.rollback()
                last_error = exc
        raise HTTPException(status_code=503, detail=ERR_ISSUE) from last_error

    def activate(
        self,
        session: Session,
        invitee_id: uuid.UUID,
        raw_code: str,
        *,
        is_new_user: bool,
    ) -> ReferralLink:
        if not CODE_RE.fullmatch(raw_code):
            raise HTTPException(status_code=422, detail=ERR_FORMAT)

        now = self._clock(None)
        code_row = self._repo.lock_code_for_update(session, raw_code)
        if code_row is None:
            raise HTTPException(status_code=409, detail=ERR_NOT_FOUND)
        if self._repo.get_link_by_code_id(session, code_row.id) is not None:
            raise HTTPException(status_code=409, detail=ERR_USED)
        if code_row.inviter_id == invitee_id:
            raise HTTPException(status_code=409, detail=ERR_SELF)
        if self._repo.get_active_link_for_invitee(session, invitee_id, now) is not None:
            raise HTTPException(status_code=409, detail=ERR_ACTIVE)
        if not is_new_user and self._repo.has_recent_receipt(
            session, invitee_id, now - timedelta(days=INACTIVE_DAYS)
        ):
            raise HTTPException(status_code=409, detail=ERR_RECENT)

        percent, coupons, cashback = self._settings()
        discount = self._create_invitee_discount(session, invitee_id, percent, now)
        ends = now + timedelta(days=WINDOW_DAYS)
        link = ReferralLink(
            id=uuid.uuid4(),
            referral_code_id=code_row.id,
            inviter_id=code_row.inviter_id,
            invitee_id=invitee_id,
            activated_at=now,
            discount_percent=percent,
            inviter_coupons=coupons,
            inviter_cashback_rub=cashback,
            discount_valid_to=ends,
            purchase_window_until=ends,
            discount_id=discount.id if discount is not None else None,
            reward_status="awaiting_purchase",
        )
        self._repo.insert_link(session, link)
        try:
            replacement = self.issue(session, code_row.inviter_id)
            logger.info(
                "referral.replacement_issued",
                inviter_id=str(code_row.inviter_id),
                code=replacement.code,
            )
        except HTTPException:
            logger.warning(
                "referral.replacement_issue_failed",
                inviter_id=str(code_row.inviter_id),
            )
        logger.info(
            "referral.activated",
            code=raw_code,
            inviter_id=str(code_row.inviter_id),
            invitee_id=str(invitee_id),
            is_new_user=is_new_user,
            window_days=WINDOW_DAYS,
        )
        return link

    def award_on_receipt(
        self,
        session: Session,
        invitee_id: uuid.UUID,
        receipt_id: uuid.UUID,
    ) -> ReferralLink | None:
        now = self._clock(None)
        link = self._repo.get_awaiting_link_for_invitee(session, invitee_id, now)
        if link is None:
            return None
        if link.inviter_coupons > 0:
            self._coupon_service.award_for_referral(
                session, link.inviter_id, link.inviter_coupons, link.id
            )
        if link.inviter_cashback_rub > 0:
            self._points_service.award_for_referral(
                session, link.inviter_id, link.inviter_cashback_rub, link.id
            )
        link.reward_status = "rewarded"
        link.qualifying_receipt_id = receipt_id
        link.rewarded_at = now
        session.flush()
        logger.info(
            "referral.rewarded",
            link_id=str(link.id),
            inviter_id=str(link.inviter_id),
            invitee_id=str(invitee_id),
            receipt_id=str(receipt_id),
            coupons=link.inviter_coupons,
            cashback_rub=link.inviter_cashback_rub,
        )
        return link

    def list_for_inviter(
        self, session: Session, inviter_id: uuid.UUID
    ) -> list[ReferralOut]:
        now = self._clock(None)
        rows = self._repo.list_codes_for_inviter(session, inviter_id)
        return [self._to_out(code, link, now) for code, link in rows]

    def _create_invitee_discount(
        self,
        session: Session,
        invitee_id: uuid.UUID,
        percent: Decimal,
        now: datetime,
    ) -> Discount | None:
        if percent <= 0:
            return None
        dtype = self._discount_repo.get_type_by_name(session, "персональная")
        ltype = self._discount_repo.get_link_type_by_name(session, "all")
        if dtype is None or ltype is None:
            raise HTTPException(
                status_code=503,
                detail="Реферальная скидка не настроена",
            )
        discount = Discount(
            id=uuid.uuid4(),
            value=percent,
            value_type="percent",
            discount_type_id=dtype.id,
            link_type_id=ltype.id,
            entity_id=None,
            loyalty_card_id=invitee_id,
            scope="all",
            valid_from=now,
            valid_to=now + timedelta(days=WINDOW_DAYS),
        )
        session.add(discount)
        session.flush()
        return discount

    @staticmethod
    def _status(link: ReferralLink | None, now: datetime) -> ReferralStatus:
        if link is None:
            return "issued"
        if link.reward_status == "rewarded":
            return "rewarded"
        if now <= link.purchase_window_until:
            return "awaiting_purchase"
        return "expired"

    def _to_out(
        self, code: ReferralCode, link: ReferralLink | None, now: datetime
    ) -> ReferralOut:
        return ReferralOut(
            id=code.id,
            code=code.code,
            status=self._status(link, now),
            created_at=code.created_at,
            activated_at=link.activated_at if link else None,
            discount_valid_to=link.discount_valid_to if link else None,
            purchase_window_until=link.purchase_window_until if link else None,
            reward_status=link.reward_status if link else None,
        )
