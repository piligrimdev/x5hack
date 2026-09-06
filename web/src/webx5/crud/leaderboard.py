from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webx5.entities.receipt import Receipt, ReceiptItem
from webx5.entities.store import Store


@dataclass(frozen=True)
class StoreVote:
    loyalty_card_id: uuid.UUID
    store_id: uuid.UUID
    vote_count: int
    last_purchase_at: datetime


@dataclass(frozen=True)
class MonthlySavings:
    loyalty_card_id: uuid.UUID
    total_saved: Decimal
    total_base: Decimal


class LeaderboardRepository:
    def list_recent_store_votes(
        self,
        session: Session,
        window: int,
    ) -> list[StoreVote]:
        """Count store visits in each user's last `window` receipts with a store."""
        ranked = (
            select(
                Receipt.loyalty_card_id,
                Receipt.store_id,
                Receipt.purchase_date,
                func.row_number()
                .over(
                    partition_by=Receipt.loyalty_card_id,
                    order_by=(Receipt.purchase_date.desc(), Receipt.id.desc()),
                )
                .label("rn"),
            )
            .where(
                Receipt.loyalty_card_id.is_not(None),
                Receipt.store_id.is_not(None),
            )
            .subquery()
        )
        stmt = (
            select(
                ranked.c.loyalty_card_id,
                ranked.c.store_id,
                func.count().label("vote_count"),
                func.max(ranked.c.purchase_date).label("last_purchase_at"),
            )
            .where(ranked.c.rn <= window)
            .group_by(ranked.c.loyalty_card_id, ranked.c.store_id)
        )
        rows = session.execute(stmt).all()
        return [
            StoreVote(
                loyalty_card_id=row.loyalty_card_id,
                store_id=row.store_id,
                vote_count=int(row.vote_count),
                last_purchase_at=row.last_purchase_at,
            )
            for row in rows
        ]

    def list_monthly_savings(
        self,
        session: Session,
        month_start: datetime,
        month_end: datetime,
    ) -> list[MonthlySavings]:
        """Per-user savings and shelf-price base for receipts in [month_start, month_end)."""
        in_month = (
            Receipt.loyalty_card_id.is_not(None),
            Receipt.purchase_date >= month_start,
            Receipt.purchase_date < month_end,
        )
        items_stmt = (
            select(
                Receipt.loyalty_card_id.label("uid"),
                func.coalesce(
                    func.sum(ReceiptItem.discounted_amount * ReceiptItem.quantity),
                    0,
                ).label("discount_saved"),
                func.coalesce(
                    func.sum(ReceiptItem.base_price_at_purchase * ReceiptItem.quantity),
                    0,
                ).label("total_base"),
            )
            .join(ReceiptItem, ReceiptItem.receipt_id == Receipt.id)
            .where(*in_month)
            .group_by(Receipt.loyalty_card_id)
        )
        cash_stmt = (
            select(
                Receipt.loyalty_card_id.label("uid"),
                func.coalesce(func.sum(Receipt.cashback_applied_rub), 0).label("cashback"),
            )
            .where(*in_month)
            .group_by(Receipt.loyalty_card_id)
        )
        cash_by_user = {
            row.uid: Decimal(str(row.cashback)) for row in session.execute(cash_stmt)
        }
        result: list[MonthlySavings] = []
        for row in session.execute(items_stmt):
            total_base = Decimal(str(row.total_base))
            if total_base <= 0:
                continue
            total_saved = Decimal(str(row.discount_saved)) + cash_by_user.get(
                row.uid, Decimal(0)
            )
            result.append(
                MonthlySavings(
                    loyalty_card_id=row.uid,
                    total_saved=total_saved,
                    total_base=total_base,
                )
            )
        return result

    def get_store_public(
        self,
        session: Session,
        store_id: uuid.UUID,
    ) -> tuple[uuid.UUID, str] | None:
        store = session.get(Store, store_id)
        if store is None:
            return None
        format_name = store.format.name if store.format is not None else "Магазин"
        return store.id, f"{format_name}, {store.geo_cluster}"
