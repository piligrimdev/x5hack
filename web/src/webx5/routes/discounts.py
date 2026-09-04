from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from webx5.dependencies.auth import TerminalTokenDep
from webx5.dependencies.db import SessionDep
from webx5.schemas.discount import DiscountCreate, DiscountResponse, DiscountTypeResponse, DiscountUpdate

discounts_router = APIRouter(prefix="/discounts", tags=["Discounts"])


@discounts_router.get("/link-types", response_model=list[DiscountTypeResponse])
def list_discount_link_types(session: SessionDep) -> list[DiscountTypeResponse]:
    from webx5.crud.discount import DiscountRepository

    repo = DiscountRepository()
    from webx5.entities.discount import DiscountLinkType
    from sqlalchemy import select
    link_types = list(session.scalars(select(DiscountLinkType).order_by(DiscountLinkType.name)))
    return [DiscountTypeResponse(id=lt.id, name=lt.name) for lt in link_types]


@discounts_router.get("/types", response_model=list[DiscountTypeResponse])
def list_discount_types(session: SessionDep) -> list[DiscountTypeResponse]:
    from webx5.crud.discount import DiscountRepository

    repo = DiscountRepository()
    types = repo.list_types(session)
    return [DiscountTypeResponse(id=t.id, name=t.name) for t in types]


@discounts_router.get("", response_model=list[DiscountResponse])
def list_discounts(
    session: SessionDep,
    entity_id: uuid.UUID | None = None,
    link_type: str | None = None,
) -> list[DiscountResponse]:
    from webx5.crud.discount import DiscountRepository

    repo = DiscountRepository()
    discounts = repo.list_active(session, entity_id=entity_id, link_type_name=link_type)
    return [DiscountResponse.from_discount(d) for d in discounts]


@discounts_router.get("/{discount_id}", response_model=DiscountResponse)
def get_discount(discount_id: uuid.UUID, session: SessionDep) -> DiscountResponse:
    from webx5.crud.discount import DiscountRepository

    repo = DiscountRepository()
    discount = repo.get_by_id(session, discount_id)
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    return DiscountResponse.from_discount(discount)


@discounts_router.post("", response_model=DiscountResponse, status_code=201)
def create_discount(
    data: DiscountCreate,
    session: SessionDep,
    _terminal: TerminalTokenDep,
) -> DiscountResponse:
    from webx5.crud.discount import DiscountRepository
    from webx5.entities.loyalty import LoyaltyCard

    if data.loyalty_card_id is not None:
        from webx5.entities.user import User
        if session.get(User, data.loyalty_card_id) is None:
            raise HTTPException(status_code=404, detail="User not found")

    repo = DiscountRepository()
    discount = repo.create(session, data.model_dump())
    return DiscountResponse.from_discount(discount)


@discounts_router.put("/{discount_id}", response_model=DiscountResponse)
def update_discount(
    discount_id: uuid.UUID,
    data: DiscountUpdate,
    session: SessionDep,
    _terminal: TerminalTokenDep,
) -> DiscountResponse:
    from webx5.crud.discount import DiscountRepository

    repo = DiscountRepository()
    discount = repo.update(session, discount_id, data.model_dump(exclude_none=True))
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    return DiscountResponse.from_discount(discount)
