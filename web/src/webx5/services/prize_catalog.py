from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from webx5.crud.catalog import CatalogRepository


class GiftCatalogNotConfiguredError(Exception):
    """Fixed gift sector cannot resolve category «кондитерка»."""


@dataclass(frozen=True)
class WheelSector:
    code: str
    label: str
    description: str
    prize_type: str
    probability_percent: int
    cashback_rub: int | None = None
    gift_criterion_type: str | None = None
    gift_category_name: str | None = None
    gift_quantity: int = 1
    gift_entity_id: uuid.UUID | None = None


_FIXED_SECTORS: tuple[WheelSector, ...] = (
    WheelSector(
        code="small_cashback",
        label="Небольшой кешбэк",
        description="10 ₽ на счёт баллов",
        prize_type="cashback",
        probability_percent=40,
        cashback_rub=10,
    ),
    WheelSector(
        code="medium_cashback",
        label="Средний кешбэк",
        description="30 ₽ на счёт баллов",
        prize_type="cashback",
        probability_percent=30,
        cashback_rub=30,
    ),
    WheelSector(
        code="gift_chocolate",
        label="Подарок: 1 шоколадка бесплатно",
        description="1 бесплатная единица товара категории «кондитерка»",
        prize_type="gift",
        probability_percent=20,
        gift_criterion_type="category",
        gift_category_name="кондитерка",
        gift_quantity=1,
    ),
    WheelSector(
        code="large_cashback",
        label="Крупный кешбэк",
        description="100 ₽ на счёт баллов",
        prize_type="cashback",
        probability_percent=10,
        cashback_rub=100,
    ),
)


class PrizeCatalogProvider(Protocol):
    def get_sectors(self, session: Session, user_id: uuid.UUID) -> list[WheelSector]:
        ...


class FixedPrizeCatalog:
    """Same sectors for every user. Swap for an LLM provider later (same method)."""

    GIFT_CATEGORY_NAME = "кондитерка"

    def __init__(self, catalog_repo: CatalogRepository | None = None) -> None:
        self._catalog_repo = catalog_repo or CatalogRepository()

    def get_sectors(self, session: Session, user_id: uuid.UUID) -> list[WheelSector]:
        _ = user_id
        gift_id = self._resolve_gift_category_id(session)
        out: list[WheelSector] = []
        for sector in _FIXED_SECTORS:
            if sector.prize_type == "gift":
                out.append(
                    WheelSector(
                        code=sector.code,
                        label=sector.label,
                        description=sector.description,
                        prize_type=sector.prize_type,
                        probability_percent=sector.probability_percent,
                        gift_criterion_type=sector.gift_criterion_type,
                        gift_category_name=sector.gift_category_name,
                        gift_quantity=sector.gift_quantity,
                        gift_entity_id=gift_id,
                    )
                )
            else:
                out.append(sector)
        return out

    def _resolve_gift_category_id(self, session: Session) -> uuid.UUID:
        category = self._catalog_repo.get_category_by_name(session, self.GIFT_CATEGORY_NAME)
        if category is None:
            raise GiftCatalogNotConfiguredError(
                f"category {self.GIFT_CATEGORY_NAME!r} is missing from the catalog"
            )
        return category.id
