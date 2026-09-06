from __future__ import annotations

from fastapi import APIRouter, status

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.referral import ReferralListOut, ReferralOut

referral_router = APIRouter(prefix="/referrals", tags=["Referrals"])


@referral_router.post("", response_model=ReferralOut, status_code=status.HTTP_201_CREATED)
def issue_referral(session: SessionDep, user_id: CurrentUserUUID) -> ReferralOut:
    from webx5.core.referral import referral_service

    code = referral_service.issue(session, user_id)
    session.commit()
    items = referral_service.list_for_inviter(session, user_id)
    issued = next((item for item in items if item.id == code.id), None)
    if issued is None:
        return ReferralOut(
            id=code.id,
            code=code.code,
            status="issued",
            created_at=code.created_at,
        )
    return issued


@referral_router.get("", response_model=ReferralListOut)
def list_referrals(session: SessionDep, user_id: CurrentUserUUID) -> ReferralListOut:
    from webx5.core.referral import referral_service

    items = referral_service.list_for_inviter(session, user_id)
    return ReferralListOut(items=items)
