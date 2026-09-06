from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from webx5.entities.reward import GiftReward


class GiftRewardRepository:
    def create(
        self,
        session: Session,
        *,
        task_id: uuid.UUID | None,
        loyalty_card_id: uuid.UUID,
        criterion_type: str,
        criterion_entity_id: uuid.UUID,
        quantity: int,
        valid_to: datetime,
    ) -> GiftReward:
        reward = GiftReward(
            task_id=task_id,
            loyalty_card_id=loyalty_card_id,
            criterion_type=criterion_type,
            criterion_entity_id=criterion_entity_id,
            quantity=quantity,
            status="active",
            valid_to=valid_to,
        )
        session.add(reward)
        session.flush()
        return reward

    def get_active_for_user(self, session: Session, user_id: uuid.UUID) -> list[GiftReward]:
        now = datetime.now(timezone.utc)
        return list(
            session.execute(
                select(GiftReward).where(
                    GiftReward.loyalty_card_id == user_id,
                    GiftReward.status == "active",
                    GiftReward.valid_to > now,
                )
            ).scalars().all()
        )

    def mark_used(self, session: Session, reward: GiftReward) -> GiftReward:
        reward.status = "used"
        session.flush()
        return reward

    def expire_overdue(self, session: Session) -> list[GiftReward]:
        now = datetime.now(timezone.utc)
        overdue = list(
            session.execute(
                select(GiftReward).where(
                    GiftReward.status == "active",
                    GiftReward.valid_to <= now,
                )
            ).scalars().all()
        )
        for r in overdue:
            r.status = "expired"
        session.flush()
        return overdue
