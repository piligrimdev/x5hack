from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.orm import Session

from webx5.crud.reward import GiftRewardRepository
from webx5.crud.wheel import WheelSpinRepository
from webx5.entities.reward import GiftReward
from webx5.entities.wheel import WheelSpin
from webx5.services.coupon import CouponService
from webx5.services.prize_catalog import (
    GiftCatalogNotConfiguredError,
    PrizeCatalogProvider,
    WheelSector,
)

logger = structlog.get_logger("wheel")

GIFT_VALID_DAYS = 7


class InsufficientCouponsError(Exception):
    pass


class WheelService:
    def __init__(
        self,
        coupon_service: CouponService,
        spin_repo: WheelSpinRepository,
        catalog: PrizeCatalogProvider,
        gift_repo: GiftRewardRepository,
    ) -> None:
        self._coupons = coupon_service
        self._spins = spin_repo
        self._catalog = catalog
        self._gifts = gift_repo

    def get_state(self, session: Session, user_id: uuid.UUID) -> dict[str, Any]:
        sectors = self._catalog.get_sectors(session, user_id)
        coupons = self._coupons.get_balance(session, user_id)
        return {
            "coupons": coupons,
            "can_spin": coupons > 0,
            "sectors": [self._sector_to_out(s) for s in sectors],
        }

    def spin(
        self,
        session: Session,
        user_id: uuid.UUID,
        *,
        rng: random.Random | None = None,
    ) -> dict[str, Any]:
        picker = rng or random.SystemRandom()
        sectors = self._catalog.get_sectors(session, user_id)
        chosen = picker.choices(
            sectors, weights=[s.probability_percent for s in sectors], k=1
        )[0]

        spin = self._spins.create(
            session,
            loyalty_card_id=user_id,
            sector_code=chosen.code,
            prize_type=chosen.prize_type,
            prize_label=chosen.label,
            cashback_rub=chosen.cashback_rub if chosen.prize_type == "cashback" else None,
        )
        if not self._coupons.debit_for_spin(session, user_id, spin.id):
            raise InsufficientCouponsError("INSUFFICIENT_COUPONS")

        points_awarded: int | None = None
        gift_reward_id: uuid.UUID | None = None
        if chosen.prize_type == "cashback":
            from webx5.core.points import points_service

            points_awarded = points_service.award_for_spin(
                session, user_id, int(chosen.cashback_rub or 0), spin.id
            )
        else:
            gift = self._award_gift(session, user_id, spin, chosen)
            gift_reward_id = gift.id
            self._spins.set_gift_reward_id(session, spin, gift.id)

        coupons_after = self._coupons.get_balance(session, user_id)
        logger.info(
            "wheel.spin",
            loyalty_card_id=str(user_id),
            spin_id=str(spin.id),
            sector_code=chosen.code,
            prize_type=chosen.prize_type,
            coupons_after=coupons_after,
        )
        return {
            "spin_id": spin.id,
            "sector_code": spin.sector_code,
            "prize_type": spin.prize_type,
            "prize_label": spin.prize_label,
            "cashback_rub": spin.cashback_rub,
            "points_awarded": points_awarded,
            "gift_reward_id": gift_reward_id,
            "coupons_after": coupons_after,
            "created_at": spin.created_at or datetime.now(UTC),
        }

    def list_spins(
        self,
        session: Session,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._spins.list_for_user(session, user_id, limit, offset)
        total = self._spins.count_for_user(session, user_id)
        items = []
        for spin in rows:
            gift_status = None
            if spin.gift_reward_id is not None:
                gift = session.get(GiftReward, spin.gift_reward_id)
                gift_status = gift.status if gift is not None else None
            items.append(
                {
                    "id": spin.id,
                    "sector_code": spin.sector_code,
                    "prize_type": spin.prize_type,
                    "prize_label": spin.prize_label,
                    "cashback_rub": spin.cashback_rub,
                    "gift_reward_id": spin.gift_reward_id,
                    "gift_status": gift_status,
                    "coupons_spent": spin.coupons_spent,
                    "created_at": spin.created_at,
                }
            )
        return items, total

    def _award_gift(
        self,
        session: Session,
        user_id: uuid.UUID,
        spin: WheelSpin,
        sector: WheelSector,
    ) -> GiftReward:
        if sector.gift_entity_id is None:
            raise GiftCatalogNotConfiguredError("gift sector has no category id")
        valid_to = datetime.now(UTC) + timedelta(days=GIFT_VALID_DAYS)
        return self._gifts.create(
            session,
            task_id=None,
            loyalty_card_id=user_id,
            criterion_type=sector.gift_criterion_type or "category",
            criterion_entity_id=sector.gift_entity_id,
            quantity=sector.gift_quantity,
            valid_to=valid_to,
            related_spin_id=spin.id,
        )

    @staticmethod
    def _sector_to_out(sector: WheelSector) -> dict[str, Any]:
        gift = None
        if sector.prize_type == "gift" and sector.gift_entity_id is not None:
            gift = {
                "criterion_type": sector.gift_criterion_type,
                "criterion_entity_id": sector.gift_entity_id,
                "quantity": sector.gift_quantity,
            }
        return {
            "code": sector.code,
            "label": sector.label,
            "description": sector.description,
            "prize_type": sector.prize_type,
            "probability_percent": sector.probability_percent,
            "cashback_rub": sector.cashback_rub,
            "gift": gift,
        }
