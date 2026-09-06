from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class GiftSectorOut(BaseModel):
    criterion_type: Literal["product", "category"]
    criterion_entity_id: uuid.UUID
    quantity: int = Field(ge=1)


class SectorOut(BaseModel):
    code: str
    label: str
    description: str
    prize_type: Literal["cashback", "gift"]
    probability_percent: int = Field(ge=1, le=99)
    cashback_rub: int | None = None
    gift: GiftSectorOut | None = None


class WheelStateOut(BaseModel):
    coupons: int = Field(ge=0)
    can_spin: bool
    weekly_coupons: int = Field(ge=0)
    week_start: date
    sectors: list[SectorOut]


class SpinOut(BaseModel):
    spin_id: uuid.UUID
    sector_code: str
    prize_type: Literal["cashback", "gift"]
    prize_label: str
    cashback_rub: int | None = None
    points_awarded: int | None = None
    gift_reward_id: uuid.UUID | None = None
    coupons_after: int = Field(ge=0)
    created_at: datetime


class SpinHistoryItem(BaseModel):
    id: uuid.UUID
    sector_code: str
    prize_type: Literal["cashback", "gift"]
    prize_label: str
    cashback_rub: int | None = None
    gift_reward_id: uuid.UUID | None = None
    gift_status: Literal["active", "used", "expired"] | None = None
    coupons_spent: int
    created_at: datetime


class SpinPage(BaseModel):
    items: list[SpinHistoryItem]
    limit: int
    offset: int
    total: int
