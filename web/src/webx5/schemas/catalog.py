import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku_id: str
    name: str
    current_price: Decimal
    category: CategoryResponse


class CategoryCreate(BaseModel):
    name: str


class ProductCreate(BaseModel):
    sku_id: str
    name: str
    current_price: Decimal
    category_id: uuid.UUID
    brand_id: uuid.UUID | None = None

    @field_validator("current_price")
    @classmethod
    def price_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("current_price must be greater than 0")
        return v


class ProductUpdate(BaseModel):
    name: str | None = None
    current_price: Decimal | None = None
    category_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None

    @field_validator("current_price")
    @classmethod
    def price_must_be_positive(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("current_price must be greater than 0")
        return v
