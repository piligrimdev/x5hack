from __future__ import annotations

from fastapi import APIRouter, Query

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.challenge import (
    ChallengeHistoryResponse,
    ChallengeItem,
    ChallengeListResponse,
    EmptyReason,
    PastChallengeItem,
)

challenges_router = APIRouter(prefix="/challenges", tags=["Challenges"])


@challenges_router.get("/current", response_model=ChallengeListResponse)
def get_current_challenges(
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> ChallengeListResponse:
    from webx5.core.challenges import challenge_service

    tasks, reason = challenge_service.get_current(session, user_id)
    items = [
        ChallengeItem(
            id=t.id,
            title=t.title,
            description=t.description,
            mechanic=t.mechanic,
            reward_rub=t.reward_rub,
            criterion_type=t.criterion_type,
            criterion_entity_id=t.criterion_entity_id,
            quantity_target=t.quantity_target,
            quantity_current=t.quantity_current,
            deadline=t.deadline,
            status="открыто",
        )
        for t in tasks
    ]
    return ChallengeListResponse(items=items, empty_reason=EmptyReason(reason))


@challenges_router.get("/history", response_model=ChallengeHistoryResponse)
def get_challenges_history(
    session: SessionDep,
    user_id: CurrentUserUUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ChallengeHistoryResponse:
    """Прошедшие задания пользователя (выполнено / провалено / истекло).
    Сортировка: свежие сверху (completed_at desc, затем issued_at desc).
    """
    from webx5.core.challenges import challenge_service

    tasks, total = challenge_service.get_history(session, user_id, limit=limit, offset=offset)
    items = [
        PastChallengeItem(
            id=t.id,
            title=t.title,
            description=t.description,
            mechanic=t.mechanic,
            reward_rub=t.reward_rub,
            criterion_type=t.criterion_type,
            criterion_entity_id=t.criterion_entity_id,
            quantity_target=t.quantity_target,
            quantity_current=t.quantity_current,
            issued_at=t.issued_at,
            deadline=t.deadline,
            completed_at=t.completed_at,
            status=t.status.name if t.status else "",
            reward_id=t.reward_id,
        )
        for t in tasks
    ]
    return ChallengeHistoryResponse(items=items, total=total, limit=limit, offset=offset)
