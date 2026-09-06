from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

REFERRAL_TZ = ZoneInfo("Europe/Moscow")
INACTIVE_DAYS = 180
WINDOW_DAYS = 7


def invitee_discount_percent_from_env() -> Decimal:
    raw = os.environ.get("REFERRAL_INVITEE_DISCOUNT_PERCENT", "10")
    try:
        value = Decimal(raw)
    except Exception as exc:
        raise RuntimeError(
            "REFERRAL_INVITEE_DISCOUNT_PERCENT must be a number 0–100"
        ) from exc
    if value < 0 or value > 100:
        raise RuntimeError("REFERRAL_INVITEE_DISCOUNT_PERCENT must be a number 0–100")
    return value


def inviter_coupons_from_env() -> int:
    raw = os.environ.get("REFERRAL_INVITER_COUPONS", "2")
    try:
        n = int(raw)
    except ValueError as exc:
        raise RuntimeError("REFERRAL_INVITER_COUPONS must be an integer >= 0") from exc
    if n < 0:
        raise RuntimeError("REFERRAL_INVITER_COUPONS must be an integer >= 0")
    return n


def inviter_cashback_from_env() -> int:
    raw = os.environ.get("REFERRAL_INVITER_CASHBACK_RUB", "50")
    try:
        n = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            "REFERRAL_INVITER_CASHBACK_RUB must be an integer >= 0"
        ) from exc
    if n < 0:
        raise RuntimeError("REFERRAL_INVITER_CASHBACK_RUB must be an integer >= 0")
    return n


def now_moscow(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(REFERRAL_TZ)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=REFERRAL_TZ)
    return moment.astimezone(REFERRAL_TZ)


def window_end(start: datetime) -> datetime:
    return start + timedelta(days=WINDOW_DAYS)


def inactive_since(now: datetime | None = None) -> datetime:
    return now_moscow(now) - timedelta(days=INACTIVE_DAYS)


def _build_services():
    from webx5.core.points import points_service
    from webx5.core.wheel import coupon_service
    from webx5.crud.discount import DiscountRepository
    from webx5.crud.referral import ReferralRepository
    from webx5.services.referral import ReferralService

    settings: Callable[[], tuple[Decimal, int, int]] = lambda: (
        invitee_discount_percent_from_env(),
        inviter_coupons_from_env(),
        inviter_cashback_from_env(),
    )
    referral_repo = ReferralRepository()
    referral_service = ReferralService(
        repo=referral_repo,
        discount_repo=DiscountRepository(),
        coupon_service=coupon_service,
        points_service=points_service,
        settings=settings,
        clock=now_moscow,
    )
    return referral_repo, referral_service


referral_repo, referral_service = _build_services()
