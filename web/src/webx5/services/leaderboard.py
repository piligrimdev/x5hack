from __future__ import annotations

import hashlib
import math
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.orm import Session

from webx5.crud.leaderboard import LeaderboardRepository, MonthlySavings, StoreVote

logger = structlog.get_logger("leaderboard")

WINDOW_SIZE = 10
HOME_STORE_WINDOW = 20
TOP_BUCKETS = (1, 5, 10, 25, 50, 75, 100)


def resolve_home_store(
    votes: list[StoreVote],
    window: int = HOME_STORE_WINDOW,
) -> uuid.UUID | None:
    """Pick the most frequent store; ties → latest purchase, then min store_id."""
    if not votes or window <= 0:
        return None
    winner = max(
        votes,
        key=lambda vote: (
            vote.vote_count,
            vote.last_purchase_at,
            # invert UUID so min store_id wins remaining ties via max()
            _uuid_sort_key(vote.store_id, reverse=True),
        ),
    )
    return winner.store_id


def _uuid_sort_key(value: uuid.UUID, reverse: bool = False) -> bytes:
    raw = value.bytes
    return bytes(255 - b for b in raw) if reverse else raw


def savings_percent(total_saved: Decimal, total_base: Decimal) -> int:
    if total_base <= 0:
        return 0
    raw = (total_saved / total_base) * Decimal(100)
    return max(0, min(100, round(raw)))


def neighbor_label(user_id: uuid.UUID) -> str:
    digest = hashlib.sha256(user_id.bytes).digest()
    code = int.from_bytes(digest[:4], "big") % 99 + 1
    return f"сосед {code}"


def top_percent_bucket(rank: int, total: int) -> int:
    if total <= 0:
        return 100
    raw = max(1, min(100, math.ceil(rank / total * 100)))
    for bucket in TOP_BUCKETS:
        if raw <= bucket:
            return bucket
    return 100


def nearest_window(
    ranked: list[dict[str, Any]],
    me_index: int | None,
    size: int = WINDOW_SIZE,
) -> list[dict[str, Any]]:
    count = len(ranked)
    if count <= size:
        return ranked
    if me_index is None:
        return ranked[:size]
    start = me_index - size // 2
    end = start + size
    if start < 0:
        start = 0
        end = size
    if end > count:
        end = count
        start = count - size
    return ranked[start:end]


class LeaderboardService:
    def __init__(self, repo: LeaderboardRepository) -> None:
        self._repo = repo

    def get_snapshot(
        self,
        session: Session,
        user_id: uuid.UUID,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        from webx5.core.leaderboard import current_month_bounds

        month_start, month_end = current_month_bounds(now)
        period = {
            "year": month_start.year,
            "month": month_start.month,
            "timezone": "Europe/Moscow",
        }
        empty = {
            "status": "no_home_store",
            "period": period,
            "store": None,
            "participant_count": 0,
            "me": None,
            "entries": [],
            "solo": False,
        }

        votes = self._repo.list_recent_store_votes(session, HOME_STORE_WINDOW)
        home_by_user = self._home_stores_by_user(votes)
        viewer_store_id = home_by_user.get(user_id)
        if viewer_store_id is None:
            logger.info(
                "leaderboard.snapshot",
                status="no_home_store",
                store_id=None,
                participant_count=0,
            )
            return empty

        store_public = self._repo.get_store_public(session, viewer_store_id)
        if store_public is None:
            store_out = {"id": viewer_store_id, "name": "Магазин"}
        else:
            store_out = {"id": store_public[0], "name": store_public[1]}

        savings = self._repo.list_monthly_savings(session, month_start, month_end)
        cohort = [
            row
            for row in savings
            if home_by_user.get(row.loyalty_card_id) == viewer_store_id
        ]
        ranked = self._rank_cohort(cohort)
        participant_count = len(ranked)
        me_row = next((row for row in ranked if row["user_id"] == user_id), None)

        window = nearest_window(
            ranked,
            me_row["index"] if me_row is not None else None,
        )
        in_window = bool(me_row and any(row["user_id"] == user_id for row in window))
        entries = [
            {
                "rank": row["rank"],
                "label": neighbor_label(row["user_id"]),
                "savings_percent": row["savings_percent"],
                "is_me": row["user_id"] == user_id,
            }
            for row in window
        ]

        me = None
        if me_row is not None:
            lower = sum(
                1 for row in ranked if row["savings_percent"] < me_row["savings_percent"]
            )
            beats = math.floor(lower / participant_count * 100) if participant_count else 0
            me = {
                "rank": me_row["rank"],
                "savings_percent": me_row["savings_percent"],
                "beats_percent": beats,
                "top_percent": top_percent_bucket(me_row["rank"], participant_count),
                "in_top": in_window,
            }

        snapshot = {
            "status": "ready",
            "period": period,
            "store": store_out,
            "participant_count": participant_count,
            "me": me,
            "entries": entries,
            "solo": participant_count == 1 and me is not None,
        }
        logger.info(
            "leaderboard.snapshot",
            status="ready",
            store_id=str(viewer_store_id),
            participant_count=participant_count,
        )
        return snapshot

    def _home_stores_by_user(
        self,
        votes: list[StoreVote],
    ) -> dict[uuid.UUID, uuid.UUID]:
        grouped: dict[uuid.UUID, list[StoreVote]] = defaultdict(list)
        for vote in votes:
            grouped[vote.loyalty_card_id].append(vote)
        result: dict[uuid.UUID, uuid.UUID] = {}
        for uid, user_votes in grouped.items():
            store_id = resolve_home_store(user_votes, HOME_STORE_WINDOW)
            if store_id is not None:
                result[uid] = store_id
        return result

    def _rank_cohort(self, cohort: list[MonthlySavings]) -> list[dict[str, Any]]:
        scored: list[tuple[uuid.UUID, int]] = [
            (row.loyalty_card_id, savings_percent(row.total_saved, row.total_base))
            for row in cohort
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        ranked: list[dict[str, Any]] = []
        prev_percent: int | None = None
        prev_rank = 0
        for index, (uid, percent) in enumerate(scored, start=1):
            rank = index if percent != prev_percent else prev_rank
            prev_percent = percent
            prev_rank = rank
            ranked.append(
                {
                    "user_id": uid,
                    "savings_percent": percent,
                    "rank": rank,
                    "index": index - 1,
                }
            )
        return ranked
