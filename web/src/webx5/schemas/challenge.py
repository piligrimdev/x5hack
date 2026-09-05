from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from webx5.schemas.types import JsonDecimal


class EmptyReason(str, Enum):
    none = "none"
    no_history = "no_history"


class ChallengeItem(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    mechanic: str
    reward_rub: JsonDecimal
    criterion_type: str
    criterion_entity_id: uuid.UUID
    quantity_target: int = Field(ge=1)
    quantity_current: int = Field(ge=0)
    deadline: datetime
    status: str = "открыто"

    model_config = {"from_attributes": True}


class ChallengeListResponse(BaseModel):
    items: list[ChallengeItem]
    empty_reason: EmptyReason


class PastChallengeItem(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    mechanic: str
    reward_rub: JsonDecimal
    criterion_type: str
    criterion_entity_id: uuid.UUID
    quantity_target: int = Field(ge=1)
    quantity_current: int = Field(ge=0)
    issued_at: datetime
    deadline: datetime
    completed_at: datetime | None = None
    status: str
    reward_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class ChallengeHistoryResponse(BaseModel):
    items: list[PastChallengeItem]
    total: int
    limit: int
    offset: int
