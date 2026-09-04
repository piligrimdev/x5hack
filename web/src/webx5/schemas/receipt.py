from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from webx5.schemas.types import JsonDecimal


PointsToSpend = int | Literal["all"] | None


# ---- Calculate ----

class CartItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1)


class CalculateRequest(BaseModel):
    loyalty_card_id: uuid.UUID | None = None
    store_id: uuid.UUID
    items: list[CartItemIn]
    points_to_spend: PointsToSpend = None


class CalculatedItemOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    quantity: int
    base_price: JsonDecimal
    paid_price: JsonDecimal
    discount_id: uuid.UUID | None
    discounted_amount: JsonDecimal


class CashbackBlock(BaseModel):
    points_available: int = Field(ge=0)
    points_to_apply: int = Field(ge=0)
    cashback_rub: int = Field(ge=0)
    total_paid_rub: int = Field(ge=0)
    points_balance_after: int = Field(ge=0)
    points_capped_by: Literal["none", "balance", "receipt_total"]
    rate_points_per_rub: int = Field(gt=0)


class CalculateResponse(BaseModel):
    store_id: uuid.UUID
    loyalty_card_id: uuid.UUID | None
    items: list[CalculatedItemOut]
    total_base: JsonDecimal
    total_paid: JsonDecimal
    total_saved: JsonDecimal
    cashback: CashbackBlock | None = None


# ---- Create Receipt ----

class ReceiptItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1)
    discount_id: uuid.UUID | None = None


class ReceiptCreate(BaseModel):
    loyalty_card_id: uuid.UUID | None = None
    store_id: uuid.UUID
    channel: str = "offline"
    payment_card_uid: str | None = None
    items: list[ReceiptItemCreate]
    points_to_spend: PointsToSpend = None


# ---- Receipt Response ----

class ReceiptItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    base_price_at_purchase: JsonDecimal
    paid_price: JsonDecimal
    discounted_amount: JsonDecimal
    discount_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ReceiptResponse(BaseModel):
    id: uuid.UUID
    purchase_date: datetime
    store_id: uuid.UUID
    loyalty_card_id: uuid.UUID | None
    channel: str
    items: list[ReceiptItemResponse]
    total_base: JsonDecimal
    total_paid: JsonDecimal
    total_saved: JsonDecimal
    discount_saved_rub: JsonDecimal = Decimal("0")
    cashback_applied_points: int = 0
    cashback_applied_rub: int = 0
    points_rate_at_purchase: int | None = None

    model_config = {"from_attributes": True}


# ---- List / Detail ----

class StoreShort(BaseModel):
    id: uuid.UUID
    format_name: str
    geo_cluster: str

    model_config = {"from_attributes": True}


class ReceiptListItem(BaseModel):
    id: uuid.UUID
    purchase_date: datetime
    store_id: uuid.UUID
    store_geo_cluster: str
    store_format_name: str
    total_base: JsonDecimal
    total_paid: JsonDecimal
    total_saved: JsonDecimal
    discount_saved_rub: JsonDecimal = Decimal("0")
    cashback_applied_points: int = 0
    cashback_applied_rub: int = 0
    items_count: int

    model_config = {"from_attributes": True}


class ReceiptDetailItem(BaseModel):
    product_id: uuid.UUID
    product_name: str
    quantity: int
    base_price_at_purchase: JsonDecimal
    paid_price: JsonDecimal
    discounted_amount: JsonDecimal
    discount_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ReceiptDetailResponse(BaseModel):
    id: uuid.UUID
    purchase_date: datetime
    store: StoreShort
    channel: str
    items: list[ReceiptDetailItem]
    total_base: JsonDecimal
    total_paid: JsonDecimal
    total_saved: JsonDecimal
    discount_saved_rub: JsonDecimal = Decimal("0")
    cashback_applied_points: int = 0
    cashback_applied_rub: int = 0
    points_rate_at_purchase: int | None = None

    model_config = {"from_attributes": True}


class PaginatedReceiptList(BaseModel):
    items: list[ReceiptListItem]
    total: int
    page: int
    size: int


# ---- Economy ----

class EconomyResponse(BaseModel):
    total_saved: JsonDecimal
    total_paid: JsonDecimal
    receipts_count: int
