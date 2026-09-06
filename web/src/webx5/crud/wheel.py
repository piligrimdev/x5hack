from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webx5.entities.wheel import WheelSpin


class WheelSpinRepository:
    def create(
        self,
        session: Session,
        *,
        loyalty_card_id: uuid.UUID,
        sector_code: str,
        prize_type: str,
        prize_label: str,
        cashback_rub: int | None = None,
        spin_id: uuid.UUID | None = None,
    ) -> WheelSpin:
        spin = WheelSpin(
            id=spin_id or uuid.uuid4(),
            loyalty_card_id=loyalty_card_id,
            sector_code=sector_code,
            prize_type=prize_type,
            prize_label=prize_label,
            cashback_rub=cashback_rub,
            coupons_spent=1,
        )
        session.add(spin)
        session.flush()
        return spin

    def set_gift_reward_id(
        self, session: Session, spin: WheelSpin, gift_reward_id: uuid.UUID
    ) -> WheelSpin:
        spin.gift_reward_id = gift_reward_id
        session.flush()
        return spin

    def get(self, session: Session, spin_id: uuid.UUID) -> WheelSpin | None:
        return session.get(WheelSpin, spin_id)

    def list_for_user(
        self,
        session: Session,
        loyalty_card_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> list[WheelSpin]:
        rows = session.execute(
            select(WheelSpin)
            .where(WheelSpin.loyalty_card_id == loyalty_card_id)
            .order_by(WheelSpin.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars().all()
        return list(rows)

    def count_for_user(self, session: Session, loyalty_card_id: uuid.UUID) -> int:
        return int(
            session.execute(
                select(func.count(WheelSpin.id)).where(
                    WheelSpin.loyalty_card_id == loyalty_card_id
                )
            ).scalar_one()
        )
