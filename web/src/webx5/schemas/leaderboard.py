from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class PeriodOut(BaseModel):
    year: int
    month: int = Field(ge=1, le=12)
    timezone: Literal["Europe/Moscow"] = "Europe/Moscow"


class LeaderboardStoreOut(BaseModel):
    id: uuid.UUID
    name: str


class LeaderboardMeOut(BaseModel):
    rank: int = Field(ge=1)
    savings_percent: int = Field(ge=0, le=100)
    beats_percent: int = Field(ge=0, le=100)
    top_percent: int = Field(ge=1, le=100)
    in_top: bool


class LeaderboardEntryOut(BaseModel):
    rank: int = Field(ge=1)
    label: str
    savings_percent: int = Field(ge=0, le=100)
    is_me: bool


class LeaderboardOut(BaseModel):
    status: Literal["no_home_store", "ready"]
    period: PeriodOut
    store: LeaderboardStoreOut | None
    participant_count: int = Field(ge=0)
    me: LeaderboardMeOut | None
    entries: list[LeaderboardEntryOut]
    solo: bool
