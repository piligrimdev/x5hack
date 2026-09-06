from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

LEADERBOARD_TZ = ZoneInfo("Europe/Moscow")
HOME_STORE_WINDOW = 20


def current_month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    moment = now or datetime.now(LEADERBOARD_TZ)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=LEADERBOARD_TZ)
    local = moment.astimezone(LEADERBOARD_TZ)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _build_service():
    from webx5.crud.leaderboard import LeaderboardRepository
    from webx5.services.leaderboard import LeaderboardService

    return LeaderboardService(repo=LeaderboardRepository())


leaderboard_service = _build_service()
