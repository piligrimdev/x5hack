from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class CouponTxOut(BaseModel):
    id: uuid.UUID
    type: Literal["weekly_grant", "task_complete", "spin"]
    amount: int
    related_task_id: uuid.UUID | None = None
    related_spin_id: uuid.UUID | None = None
    week_start: date | None = None
    created_at: datetime


class CouponTxPage(BaseModel):
    items: list[CouponTxOut]
    limit: int
    offset: int
    total: int
