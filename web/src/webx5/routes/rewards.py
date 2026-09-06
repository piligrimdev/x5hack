from __future__ import annotations

import uuid

from fastapi import APIRouter

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.reward import GiftRewardOut

rewards_router = APIRouter(prefix="/rewards", tags=["Rewards"])


@rewards_router.get("", response_model=list[GiftRewardOut])
def list_rewards(session: SessionDep, user_id: CurrentUserUUID) -> list[GiftRewardOut]:
    from webx5.core.rewards import gift_reward_repo
    rewards = gift_reward_repo.get_active_for_user(session, user_id)
    return [GiftRewardOut(
        id=r.id,
        criterion_type=r.criterion_type,
        criterion_entity_id=r.criterion_entity_id,
        quantity=r.quantity,
        status=r.status,
        valid_to=r.valid_to,
        applicable=False,
    ) for r in rewards]
