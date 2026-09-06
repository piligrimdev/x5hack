from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ReferralStatus = Literal["issued", "awaiting_purchase", "rewarded", "expired"]
RewardStatus = Literal["awaiting_purchase", "rewarded"]


class ReferralOut(BaseModel):
    id: uuid.UUID
    code: str
    status: ReferralStatus
    created_at: datetime
    activated_at: datetime | None = None
    discount_valid_to: datetime | None = None
    purchase_window_until: datetime | None = None
    reward_status: RewardStatus | None = None


class ReferralListOut(BaseModel):
    items: list[ReferralOut]
