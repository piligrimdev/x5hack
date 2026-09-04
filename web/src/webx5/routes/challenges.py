from __future__ import annotations

from fastapi import APIRouter

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.challenge import ChallengeItem, ChallengeListResponse, EmptyReason

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
