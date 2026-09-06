from __future__ import annotations


def _build_services():
    from webx5.crud.coupon import CouponRepository
    from webx5.crud.reward import GiftRewardRepository
    from webx5.crud.wheel import WheelSpinRepository
    from webx5.services.coupon import CouponService
    from webx5.services.prize_catalog import FixedPrizeCatalog
    from webx5.services.wheel import WheelService

    coupon_repo = CouponRepository()
    coupon_service = CouponService(repo=coupon_repo)
    wheel_service = WheelService(
        coupon_service=coupon_service,
        spin_repo=WheelSpinRepository(),
        catalog=FixedPrizeCatalog(),
        gift_repo=GiftRewardRepository(),
    )
    return coupon_service, wheel_service


coupon_service, wheel_service = _build_services()
