from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from webx5.entities.receipt import Receipt
from webx5.entities.referral import ReferralCode, ReferralLink


class ReferralRepository:
    def insert_code(
        self, session: Session, inviter_id: uuid.UUID, code: str
    ) -> ReferralCode:
        row = ReferralCode(id=uuid.uuid4(), code=code, inviter_id=inviter_id)
        session.add(row)
        session.flush()
        return row

    def get_by_code(self, session: Session, code: str) -> ReferralCode | None:
        return session.scalar(select(ReferralCode).where(ReferralCode.code == code))

    def lock_code_for_update(self, session: Session, code: str) -> ReferralCode | None:
        return session.scalar(
            select(ReferralCode).where(ReferralCode.code == code).with_for_update()
        )

    def insert_link(self, session: Session, link: ReferralLink) -> ReferralLink:
        session.add(link)
        session.flush()
        return link

    def get_link_by_code_id(
        self, session: Session, code_id: uuid.UUID
    ) -> ReferralLink | None:
        return session.scalar(
            select(ReferralLink).where(ReferralLink.referral_code_id == code_id)
        )

    def list_codes_for_inviter(
        self, session: Session, inviter_id: uuid.UUID
    ) -> list[tuple[ReferralCode, ReferralLink | None]]:
        rows = session.execute(
            select(ReferralCode, ReferralLink)
            .outerjoin(ReferralLink, ReferralLink.referral_code_id == ReferralCode.id)
            .where(ReferralCode.inviter_id == inviter_id)
            .order_by(ReferralCode.created_at.desc())
        ).all()
        return [(code, link) for code, link in rows]

    def get_active_link_for_invitee(
        self, session: Session, invitee_id: uuid.UUID, now: datetime
    ) -> ReferralLink | None:
        return session.scalar(
            select(ReferralLink)
            .where(ReferralLink.invitee_id == invitee_id)
            .where(
                or_(
                    ReferralLink.discount_valid_to > now,
                    ReferralLink.purchase_window_until > now,
                )
            )
            .order_by(ReferralLink.activated_at.desc())
        )

    def get_awaiting_link_for_invitee(
        self, session: Session, invitee_id: uuid.UUID, now: datetime
    ) -> ReferralLink | None:
        return session.scalar(
            select(ReferralLink)
            .where(ReferralLink.invitee_id == invitee_id)
            .where(ReferralLink.reward_status == "awaiting_purchase")
            .where(ReferralLink.purchase_window_until >= now)
            .order_by(ReferralLink.activated_at.desc())
            .with_for_update()
        )

    def has_recent_receipt(
        self, session: Session, invitee_id: uuid.UUID, since: datetime
    ) -> bool:
        row = session.execute(
            select(Receipt.id)
            .where(Receipt.loyalty_card_id == invitee_id)
            .where(Receipt.purchase_date >= since)
            .limit(1)
        ).first()
        return row is not None
