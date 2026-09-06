from __future__ import annotations

from fastapi import APIRouter, Query

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.coupon import CouponTxOut, CouponTxPage

coupons_router = APIRouter(prefix="/coupons", tags=["Coupons"])


@coupons_router.get("/transactions", response_model=CouponTxPage)
def list_coupon_transactions(
    session: SessionDep,
    user_id: CurrentUserUUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> CouponTxPage:
    from webx5.core.wheel import coupon_service

    items, total = coupon_service.list_transactions(session, user_id, limit, offset)
    session.commit()
    return CouponTxPage(
        items=[
            CouponTxOut(
                id=tx.id,
                type=tx.type,
                amount=tx.amount,
                related_task_id=tx.related_task_id,
                related_spin_id=tx.related_spin_id,
                related_referral_link_id=tx.related_referral_link_id,
                related_receipt_id=tx.related_receipt_id,
                week_start=tx.week_start,
                created_at=tx.created_at,
            )
            for tx in items
        ],
        limit=limit,
        offset=offset,
        total=total,
    )
