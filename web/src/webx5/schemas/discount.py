from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from webx5.schemas.types import JsonDecimal


class DiscountTypeResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class DiscountResponse(BaseModel):
    id: uuid.UUID
    value: JsonDecimal
    discount_type: str
    link_type: str
    entity_id: uuid.UUID | None
    loyalty_card_id: uuid.UUID | None
    min_loyalty_level: int | None
    scope: str
    valid_from: datetime | None
    valid_to: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_discount(cls, d) -> "DiscountResponse":
        return cls(
            id=d.id,
            value=Decimal(str(d.value)),
            discount_type=d.discount_type.name,
            link_type=d.link_type.name,
            entity_id=d.entity_id,
            loyalty_card_id=d.loyalty_card_id,
            min_loyalty_level=d.min_loyalty_level,
            scope=d.scope,
            valid_from=d.valid_from,
            valid_to=d.valid_to,
        )


class DiscountCreate(BaseModel):
    value: Decimal = Field(ge=0, le=100)
    discount_type_id: uuid.UUID
    link_type_id: uuid.UUID
    entity_id: uuid.UUID | None = None
    loyalty_card_id: uuid.UUID | None = None
    min_loyalty_level: int | None = None
    scope: str = "all"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    format_ids: list[uuid.UUID] = []
    store_ids: list[uuid.UUID] = []


class DiscountUpdate(BaseModel):
    value: Decimal | None = Field(default=None, ge=0, le=100)
    scope: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    format_ids: list[uuid.UUID] | None = None
    store_ids: list[uuid.UUID] | None = None
