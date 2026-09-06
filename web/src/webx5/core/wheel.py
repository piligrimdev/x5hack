from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

WHEEL_TZ = ZoneInfo("Europe/Moscow")


def weekly_coupons_from_env() -> int:
    raw = os.environ.get("FORTUNE_WHEEL_WEEKLY_COUPONS", "3")
    try:
        n = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            "FORTUNE_WHEEL_WEEKLY_COUPONS must be an integer >= 0"
        ) from exc
    if n < 0:
        raise RuntimeError("FORTUNE_WHEEL_WEEKLY_COUPONS must be an integer >= 0")
    return n


def current_week_start(now: datetime | None = None) -> date:
    moment = now or datetime.now(WHEEL_TZ)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=WHEEL_TZ)
    local = moment.astimezone(WHEEL_TZ)
    return local.date() - timedelta(days=local.weekday())


def _build_services():
    from webx5.crud.coupon import CouponRepository
    from webx5.crud.reward import GiftRewardRepository
    from webx5.crud.wheel import WheelSpinRepository
    from webx5.services.coupon import CouponService
    from webx5.services.prize_catalog import FixedPrizeCatalog
    from webx5.services.wheel import WheelService

    coupon_repo = CouponRepository()
    spin_repo = WheelSpinRepository()
    coupon_service = CouponService(
        repo=coupon_repo,
        weekly_n=weekly_coupons_from_env,
        week_start=current_week_start,
    )
    catalog = FixedPrizeCatalog()
    wheel_service = WheelService(
        coupon_service=coupon_service,
        spin_repo=spin_repo,
        catalog=catalog,
        gift_repo=GiftRewardRepository(),
        weekly_n=weekly_coupons_from_env,
        week_start=current_week_start,
    )
    return coupon_service, wheel_service


coupon_service, wheel_service = _build_services()
