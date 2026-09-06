from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class GiftRewardOut(BaseModel):
    id: uuid.UUID
    reward_type: str = "gift"
    criterion_type: str
    criterion_entity_id: uuid.UUID
    quantity: int
    status: str
    valid_to: datetime
    applicable: bool = False

    model_config = {"from_attributes": True}


class GiftDiscountApplied(BaseModel):
    gift_reward_id: uuid.UUID
    applied_to_product_id: uuid.UUID
    discount_rub: Decimal
