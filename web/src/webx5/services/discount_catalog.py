from __future__ import annotations

import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from webx5.entities.category import Category
from webx5.entities.discount import Discount
from webx5.entities.product import Product
from webx5.schemas.discount import UserDiscountOut

MOSCOW = ZoneInfo("Europe/Moscow")

_LINK_SCOPE = {
    "all": "на все покупки",
    "category": "на категорию",
    "product": "на товар",
    "brand": "на бренд",
}


def format_discount_value(value: object, value_type: str) -> str:
    amount = Decimal(str(value))
    if value_type == "fixed_rub":
        if amount == amount.to_integral():
            return f"{int(amount)} ₽"
        return f"{amount.normalize()} ₽"
    if amount == amount.to_integral():
        return f"{int(amount)}%"
    return f"{amount.normalize()}%"


def resolve_entity_names(session: Session, discounts: list[Discount]) -> dict[uuid.UUID, str]:
    names: dict[uuid.UUID, str] = {}
    category_ids = {
        d.entity_id
        for d in discounts
        if d.entity_id is not None and d.link_type.name == "category"
    }
    product_ids = {
        d.entity_id
        for d in discounts
        if d.entity_id is not None and d.link_type.name == "product"
    }
    if category_ids:
        for category in session.scalars(select(Category).where(Category.id.in_(category_ids))):
            names[category.id] = category.name
    if product_ids:
        for product in session.scalars(select(Product).where(Product.id.in_(product_ids))):
            names[product.id] = product.name
    return names


def describe_discount(discount: Discount, entity_name: str | None = None) -> UserDiscountOut:
    is_personal = discount.discount_type.name == "персональная"
    kind = "Персональная скидка" if is_personal else "Акция"
    amount = format_discount_value(discount.value, getattr(discount, "value_type", "percent"))
    title = f"{kind} {amount}"

    scope = _LINK_SCOPE.get(discount.link_type.name, "на выбранные товары")
    if entity_name:
        target = f"{scope} «{entity_name}»"
    else:
        target = scope if discount.link_type.name == "all" else f"{scope} каталога"

    parts = [f"{amount} {target}."]
    if is_personal and discount.link_type.name == "all":
        parts.append(
            "Обычно это награда за реферальный код: применяется на кассе автоматически, "
            "если выгоднее других акций."
        )
    elif is_personal:
        parts.append("Действует только для вас и применяется автоматически.")
    else:
        parts.append("На кассе побеждает скидка с большей выгодой — эта не суммируется с меньшей.")

    if discount.valid_to is not None:
        until = discount.valid_to
        if until.tzinfo is None:
            until = until.replace(tzinfo=MOSCOW)
        parts.append(f"До {until.astimezone(MOSCOW).strftime('%d.%m.%Y')}.")

    return UserDiscountOut(
        id=discount.id,
        title=title,
        description=" ".join(parts),
        value=Decimal(str(discount.value)),
        discount_type=discount.discount_type.name,
        link_type=discount.link_type.name,
        is_personal=is_personal,
        valid_from=discount.valid_from,
        valid_to=discount.valid_to,
    )
