from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from webx5.core.leaderboard import LEADERBOARD_TZ
from webx5.crud.leaderboard import MonthlySavings, StoreVote
from webx5.services.leaderboard import (
    LeaderboardService,
    neighbor_label,
    resolve_home_store,
    savings_percent,
    top_percent_bucket,
)

MSK = LEADERBOARD_TZ
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=MSK)


class FakeRepo:
    def __init__(
        self,
        votes: list[StoreVote] | None = None,
        savings: list[MonthlySavings] | None = None,
        stores: dict[uuid.UUID, tuple[uuid.UUID, str]] | None = None,
    ) -> None:
        self.votes = votes or []
        self.savings = savings or []
        self.stores = stores or {}

    def list_recent_store_votes(self, session, window: int) -> list[StoreVote]:
        return self.votes

    def list_monthly_savings(self, session, month_start, month_end) -> list[MonthlySavings]:
        return self.savings

    def get_store_public(self, session, store_id: uuid.UUID):
        return self.stores.get(store_id)


def _vote(
    user_id: uuid.UUID,
    store_id: uuid.UUID,
    count: int,
    last: datetime,
) -> StoreVote:
    return StoreVote(
        loyalty_card_id=user_id,
        store_id=store_id,
        vote_count=count,
        last_purchase_at=last,
    )


def _saved(user_id: uuid.UUID, saved: str, base: str) -> MonthlySavings:
    return MonthlySavings(
        loyalty_card_id=user_id,
        total_saved=Decimal(saved),
        total_base=Decimal(base),
    )


def test_no_home_store_when_no_votes() -> None:
    service = LeaderboardService(repo=FakeRepo())
    snap = service.get_snapshot(session=None, user_id=uuid.uuid4(), now=NOW)
    assert snap["status"] == "no_home_store"
    assert snap["store"] is None
    assert snap["me"] is None
    assert snap["entries"] == []
    assert snap["participant_count"] == 0
    assert snap["solo"] is False


def test_percent_beats_absolute_rubles() -> None:
    store_a = uuid.uuid4()
    user_a = uuid.UUID("00000000-0000-0000-0000-00000000000a")
    user_b = uuid.UUID("00000000-0000-0000-0000-00000000000b")
    last = datetime(2026, 9, 10, tzinfo=MSK)
    repo = FakeRepo(
        votes=[
            _vote(user_a, store_a, 5, last),
            _vote(user_b, store_a, 5, last),
        ],
        savings=[
            _saved(user_a, "200", "2000"),
            _saved(user_b, "500", "10000"),
        ],
        stores={store_a: (store_a, "Пятёрочка, d_03")},
    )
    service = LeaderboardService(repo=repo)
    snap_a = service.get_snapshot(session=None, user_id=user_a, now=NOW)
    snap_b = service.get_snapshot(session=None, user_id=user_b, now=NOW)
    assert snap_a["me"]["savings_percent"] == 10
    assert snap_b["me"]["savings_percent"] == 5
    assert snap_a["me"]["rank"] < snap_b["me"]["rank"]
    assert snap_a["store"]["name"] == "Пятёрочка, d_03"


def test_tied_percent_shares_competition_rank() -> None:
    store_a = uuid.uuid4()
    users = [uuid.uuid4() for _ in range(4)]
    last = datetime(2026, 9, 10, tzinfo=MSK)
    # percents 10, 8, 8, 5 → ranks 1, 2, 2, 4
    saved = [
        _saved(users[0], "100", "1000"),
        _saved(users[1], "80", "1000"),
        _saved(users[2], "80", "1000"),
        _saved(users[3], "50", "1000"),
    ]
    votes = [_vote(uid, store_a, 3, last) for uid in users]
    service = LeaderboardService(
        repo=FakeRepo(
            votes=votes,
            savings=saved,
            stores={store_a: (store_a, "Перекрёсток, d_01")},
        )
    )
    snap = service.get_snapshot(session=None, user_id=users[0], now=NOW)
    ranks_by_percent = {entry["savings_percent"]: entry["rank"] for entry in snap["entries"]}
    assert ranks_by_percent[10] == 1
    assert ranks_by_percent[8] == 2
    assert ranks_by_percent[5] == 4
    eight_ranks = [e["rank"] for e in snap["entries"] if e["savings_percent"] == 8]
    assert eight_ranks == [2, 2]


def test_shows_ten_nearest_including_viewer() -> None:
    store_a = uuid.uuid4()
    last = datetime(2026, 9, 10, tzinfo=MSK)
    users = [uuid.uuid4() for _ in range(20)]
    votes = [_vote(uid, store_a, 2, last) for uid in users]
    savings = [_saved(users[i], str(40 - i), "100") for i in range(20)]
    viewer = users[14]
    service = LeaderboardService(
        repo=FakeRepo(
            votes=votes,
            savings=savings,
            stores={store_a: (store_a, "Чижик, d_02")},
        )
    )
    snap = service.get_snapshot(session=None, user_id=viewer, now=NOW)
    assert len(snap["entries"]) == 10
    assert snap["me"]["rank"] == 15
    assert any(entry["is_me"] for entry in snap["entries"])
    assert snap["entries"][0]["rank"] <= snap["me"]["rank"] <= snap["entries"][-1]["rank"]
    assert snap["me"]["top_percent"] in {1, 5, 10, 25, 50, 75, 100}
    assert all(
        entry["label"].startswith("сосед ") or entry["is_me"]
        for entry in snap["entries"]
    )


def test_home_store_majority_of_twenty() -> None:
    store_a = uuid.uuid4()
    store_b = uuid.uuid4()
    user = uuid.uuid4()
    last_a = datetime(2026, 9, 8, tzinfo=MSK)
    last_b = datetime(2026, 9, 12, tzinfo=MSK)
    votes = [
        _vote(user, store_a, 12, last_a),
        _vote(user, store_b, 8, last_b),
    ]
    assert resolve_home_store(votes) == store_a
    service = LeaderboardService(
        repo=FakeRepo(
            votes=votes,
            savings=[_saved(user, "10", "100")],
            stores={store_a: (store_a, "Пятёрочка, d_03")},
        )
    )
    first = service.get_snapshot(session=None, user_id=user, now=NOW)
    second = service.get_snapshot(session=None, user_id=user, now=NOW)
    assert first["store"]["id"] == store_a
    assert second["store"]["id"] == store_a


def test_home_store_uses_all_when_fewer_than_twenty() -> None:
    store_a = uuid.uuid4()
    store_b = uuid.uuid4()
    user = uuid.uuid4()
    last = datetime(2026, 9, 10, tzinfo=MSK)
    votes = [_vote(user, store_a, 5, last), _vote(user, store_b, 4, last)]
    assert resolve_home_store(votes) == store_a


def test_home_store_tie_prefers_later_purchase() -> None:
    store_a = uuid.uuid4()
    store_b = uuid.uuid4()
    user = uuid.uuid4()
    earlier = datetime(2026, 9, 1, tzinfo=MSK)
    later = datetime(2026, 9, 10, tzinfo=MSK)
    votes = [_vote(user, store_a, 10, earlier), _vote(user, store_b, 10, later)]
    assert resolve_home_store(votes) == store_b


def test_other_home_store_excluded_from_entries() -> None:
    store_a = uuid.uuid4()
    store_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_c = uuid.uuid4()
    last = datetime(2026, 9, 10, tzinfo=MSK)
    service = LeaderboardService(
        repo=FakeRepo(
            votes=[
                _vote(user_a, store_a, 6, last),
                _vote(user_c, store_b, 6, last),
            ],
            savings=[
                _saved(user_a, "10", "100"),
                _saved(user_c, "50", "100"),
            ],
            stores={store_a: (store_a, "Пятёрочка, d_03")},
        )
    )
    snap = service.get_snapshot(session=None, user_id=user_a, now=NOW)
    assert snap["participant_count"] == 1
    assert all(entry["savings_percent"] != 50 for entry in snap["entries"])
    assert snap["solo"] is True
    assert snap["me"]["rank"] == 1
    assert snap["me"]["beats_percent"] == 0


def test_ready_without_me_when_no_month_purchases() -> None:
    store_a = uuid.uuid4()
    user = uuid.uuid4()
    neighbor = uuid.uuid4()
    last = datetime(2026, 8, 20, tzinfo=MSK)
    service = LeaderboardService(
        repo=FakeRepo(
            votes=[
                _vote(user, store_a, 4, last),
                _vote(neighbor, store_a, 3, last),
            ],
            savings=[_saved(neighbor, "20", "100")],
            stores={store_a: (store_a, "Пятёрочка, d_03")},
        )
    )
    snap = service.get_snapshot(session=None, user_id=user, now=NOW)
    assert snap["status"] == "ready"
    assert snap["store"] is not None
    assert snap["me"] is None
    assert snap["solo"] is False
    assert snap["entries"][0]["is_me"] is False


def test_neighbor_label_is_not_a_name() -> None:
    user_id = uuid.uuid4()
    label = neighbor_label(user_id)
    assert label.startswith("сосед ")
    assert "Покупатель" not in label
    assert str(user_id) not in label
    assert neighbor_label(user_id) == label


def test_top_percent_buckets() -> None:
    assert top_percent_bucket(1, 100) == 1
    assert top_percent_bucket(3, 100) == 5
    assert top_percent_bucket(12, 100) == 25
    assert top_percent_bucket(50, 100) == 50
    assert top_percent_bucket(1, 1) == 100


def test_savings_percent_clamped() -> None:
    assert savings_percent(Decimal(10), Decimal(100)) == 10
    assert savings_percent(Decimal(200), Decimal(100)) == 100
    assert savings_percent(Decimal(0), Decimal(0)) == 0


def test_period_is_moscow_calendar_month() -> None:
    service = LeaderboardService(repo=FakeRepo())
    snap = service.get_snapshot(session=None, user_id=uuid.uuid4(), now=NOW)
    assert snap["period"] == {
        "year": 2026,
        "month": 9,
        "timezone": "Europe/Moscow",
    }
    late = datetime(2026, 10, 1, 0, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    snap_oct = service.get_snapshot(
        session=None, user_id=uuid.uuid4(), now=late - timedelta(seconds=1)
    )
    assert snap_oct["period"]["month"] == 9
