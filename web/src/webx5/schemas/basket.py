from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from webx5.schemas.types import JsonDecimal


class BasketItem(BaseModel):
    product_id: uuid.UUID
    name: str
    quantity: int
    price: JsonDecimal


class SuggestedBasketResponse(BaseModel):
    items: list[BasketItem]


class BasketItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1)


class AssistantRequest(BaseModel):
    items: list[BasketItemIn]
    instruction: str = Field(min_length=1, max_length=500)


class AssistantResponse(BaseModel):
    items: list[BasketItem]
    applied: bool
    message: str | None = None
