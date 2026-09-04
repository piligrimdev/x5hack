from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BalanceResponse(BaseModel):
    balance: int = Field(ge=0)
    rate_points_per_rub: int = Field(gt=0)
    balance_rub_equivalent: int = Field(ge=0)


class TransactionOut(BaseModel):
    id: uuid.UUID
    type: Literal["earn", "spend"]
    amount: int
    related_task_id: uuid.UUID | None = None
    related_receipt_id: uuid.UUID | None = None
    rate_at_time: int | None = None
    created_at: datetime


class TransactionsPage(BaseModel):
    items: list[TransactionOut]
    limit: int
    offset: int
    total: int


class RateResponse(BaseModel):
    rate_points_per_rub: int = Field(gt=0)


class RateUpdate(BaseModel):
    rate_points_per_rub: int = Field(gt=0)
