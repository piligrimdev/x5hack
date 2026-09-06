from __future__ import annotations

from fastapi import APIRouter

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.leaderboard import LeaderboardOut

leaderboard_router = APIRouter(tags=["Leaderboard"])


@leaderboard_router.get("/leaderboard", response_model=LeaderboardOut)
def get_leaderboard(session: SessionDep, user_id: CurrentUserUUID) -> LeaderboardOut:
    from webx5.core.leaderboard import leaderboard_service

    snapshot = leaderboard_service.get_snapshot(session, user_id)
    return LeaderboardOut.model_validate(snapshot)
