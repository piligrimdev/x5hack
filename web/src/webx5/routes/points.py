from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from webx5.dependencies.auth import CurrentUserUUID, TerminalTokenDep
from webx5.dependencies.db import SessionDep
from webx5.schemas.points import (
    BalanceResponse,
    RateResponse,
    RateUpdate,
    TransactionOut,
    TransactionsPage,
)

points_router = APIRouter(prefix="/points", tags=["Points"])


@points_router.get("/balance", response_model=BalanceResponse)
def get_balance(
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> BalanceResponse:
    from webx5.core.points import points_service

    view = points_service.get_balance(session, user_id)
    session.commit()
    return BalanceResponse(
        balance=view.balance,
        rate_points_per_rub=view.rate_points_per_rub,
        balance_rub_equivalent=view.balance_rub_equivalent,
    )


@points_router.get("/transactions", response_model=TransactionsPage)
def list_transactions(
    session: SessionDep,
    user_id: CurrentUserUUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> TransactionsPage:
    from webx5.core.points import points_service

    items, total = points_service.list_transactions(session, user_id, limit, offset)
    session.commit()
    return TransactionsPage(
        items=[
            TransactionOut(
                id=tx.id,
                type=tx.type,
                amount=tx.amount,
                related_task_id=tx.related_task_id,
                related_receipt_id=tx.related_receipt_id,
                rate_at_time=tx.rate_at_time,
                created_at=tx.created_at,
            )
            for tx in items
        ],
        limit=limit,
        offset=offset,
        total=total,
    )


@points_router.get("/settings/rate", response_model=RateResponse)
def get_rate(session: SessionDep) -> RateResponse:
    from webx5.core.points import points_repo

    return RateResponse(rate_points_per_rub=points_repo.get_rate(session))


@points_router.put("/settings/rate", response_model=RateResponse)
def set_rate(
    body: RateUpdate,
    session: SessionDep,
    _terminal: TerminalTokenDep,
) -> RateResponse:
    from webx5.core.points import points_service

    if body.rate_points_per_rub <= 0:
        raise HTTPException(status_code=422, detail="rate must be positive")
    new_rate = points_service.set_rate(session, body.rate_points_per_rub)
    session.commit()
    return RateResponse(rate_points_per_rub=new_rate)
