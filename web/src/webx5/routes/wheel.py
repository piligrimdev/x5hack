from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.wheel import SpinHistoryItem, SpinOut, SpinPage, WheelStateOut
from webx5.services.prize_catalog import GiftCatalogNotConfiguredError
from webx5.services.wheel import InsufficientCouponsError

wheel_router = APIRouter(prefix="/wheel", tags=["Fortune wheel"])


@wheel_router.get("", response_model=WheelStateOut)
def get_wheel(session: SessionDep, user_id: CurrentUserUUID) -> WheelStateOut:
    from webx5.core.wheel import wheel_service

    try:
        state = wheel_service.get_state(session, user_id)
    except GiftCatalogNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    session.commit()
    return WheelStateOut.model_validate(state)


@wheel_router.post("/spin", response_model=SpinOut)
def spin_wheel(session: SessionDep, user_id: CurrentUserUUID) -> SpinOut:
    from webx5.core.wheel import wheel_service

    try:
        result = wheel_service.spin(session, user_id)
    except InsufficientCouponsError:
        raise HTTPException(status_code=409, detail="INSUFFICIENT_COUPONS") from None
    except GiftCatalogNotConfiguredError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    session.commit()
    return SpinOut.model_validate(result)


@wheel_router.get("/spins", response_model=SpinPage)
def list_spins(
    session: SessionDep,
    user_id: CurrentUserUUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SpinPage:
    from webx5.core.wheel import wheel_service

    items, total = wheel_service.list_spins(session, user_id, limit, offset)
    session.commit()
    return SpinPage(
        items=[SpinHistoryItem.model_validate(item) for item in items],
        limit=limit,
        offset=offset,
        total=total,
    )
