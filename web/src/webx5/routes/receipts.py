from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response
from sqlalchemy.orm import Session

from webx5.dependencies.auth import CurrentUserUUID, TerminalTokenDep
from webx5.dependencies.db import SessionDep
from webx5.schemas.receipt import (
    CalculateRequest,
    CalculateResponse,
    CalculatedItemOut,
    EconomyResponse,
    PaginatedReceiptList,
    ReceiptCreate,
    ReceiptDetailItem,
    ReceiptDetailResponse,
    ReceiptItemResponse,
    ReceiptListItem,
    ReceiptResponse,
    StoreShort,
)
from webx5.services.discount_calculator import CartItem

receipts_router = APIRouter(prefix="/receipts", tags=["Receipts"])


@receipts_router.post("/calculate", response_model=CalculateResponse)
def calculate_discounts(
    data: CalculateRequest,
    session: SessionDep,
    _terminal: TerminalTokenDep,
) -> CalculateResponse:
    from sqlalchemy import select

    from webx5.core.purchases import discount_calculator_service
    from webx5.entities.store import Store

    store = session.get(Store, data.store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    from webx5.entities.product import Product

    product_ids = [item.product_id for item in data.items]
    found_ids = set(
        session.scalars(select(Product.id).where(Product.id.in_(product_ids)))
    )
    missing = [str(pid) for pid in product_ids if pid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"detail": "Unknown product_ids", "unknown_product_ids": missing},
        )

    cart_items = [CartItem(product_id=i.product_id, quantity=i.quantity) for i in data.items]
    calculated = discount_calculator_service.calculate(
        items=cart_items,
        store=store,
        loyalty_card_id=data.loyalty_card_id,
        session=session,
    )

    items_out = [
        CalculatedItemOut(
            product_id=c.product_id,
            product_name=c.product_name,
            quantity=c.quantity,
            base_price=c.base_price,
            paid_price=c.paid_price,
            discount_id=c.discount_id,
            discounted_amount=c.discounted_amount,
        )
        for c in calculated
    ]

    total_base = sum(i.base_price * i.quantity for i in items_out)
    total_paid = sum(i.paid_price * i.quantity for i in items_out)

    return CalculateResponse(
        store_id=data.store_id,
        loyalty_card_id=data.loyalty_card_id,
        items=items_out,
        total_base=total_base,
        total_paid=total_paid,
        total_saved=total_base - total_paid,
    )


@receipts_router.post("", response_model=ReceiptResponse, status_code=201)
def create_receipt(
    data: ReceiptCreate,
    session: SessionDep,
    _terminal: TerminalTokenDep,
    response: Response,
    x_idempotency_key: Annotated[str | None, Header()] = None,
) -> ReceiptResponse:
    from webx5.core.purchases import receipt_service

    if not x_idempotency_key:
        raise HTTPException(status_code=401, detail="X-Idempotency-Key header is required")

    try:
        receipt_id = uuid.UUID(x_idempotency_key)
    except ValueError:
        raise HTTPException(status_code=422, detail="X-Idempotency-Key must be a valid UUID")

    receipt, is_new = receipt_service.create_receipt(session, receipt_id, data)

    if not is_new:
        response.status_code = 200

    # Load items for response
    from webx5.crud.receipt import ReceiptRepository

    repo = ReceiptRepository()
    items_with_products = repo.get_items_with_products(session, receipt.id)

    item_responses = []
    for ri, _p in items_with_products:
        item_responses.append(
            ReceiptItemResponse(
                id=ri.id,
                product_id=ri.product_id,
                quantity=ri.quantity,
                base_price_at_purchase=Decimal(str(ri.base_price_at_purchase)),
                paid_price=Decimal(str(ri.paid_price)),
                discounted_amount=Decimal(str(ri.discounted_amount)),
                discount_id=ri.discount_id,
            )
        )

    total_base = sum(i.base_price_at_purchase * i.quantity for i in item_responses)
    total_paid = sum(i.paid_price * i.quantity for i in item_responses)

    return ReceiptResponse(
        id=receipt.id,
        purchase_date=receipt.purchase_date,
        store_id=receipt.store_id,
        loyalty_card_id=receipt.loyalty_card_id,
        channel=receipt.channel,
        items=item_responses,
        total_base=total_base,
        total_paid=total_paid,
        total_saved=total_base - total_paid,
    )


@receipts_router.get("", response_model=PaginatedReceiptList)
def list_receipts(
    session: SessionDep,
    user_id: CurrentUserUUID,
    page: int = 1,
    size: int = 20,
) -> PaginatedReceiptList:
    from webx5.core.purchases import receipt_repo

    receipts, total = receipt_repo.list_by_loyalty_card(session, user_id, page, size)

    items = []
    for receipt in receipts:
        items_data = receipt_repo.get_items_with_products(session, receipt.id)
        total_base = sum(Decimal(str(ri.base_price_at_purchase)) * ri.quantity for ri, _ in items_data)
        total_paid = sum(Decimal(str(ri.paid_price)) * ri.quantity for ri, _ in items_data)
        total_saved = total_base - total_paid

        store = session.get(__import__("webx5.entities.store", fromlist=["Store"]).Store, receipt.store_id)

        items.append(
            ReceiptListItem(
                id=receipt.id,
                purchase_date=receipt.purchase_date,
                store_id=receipt.store_id,
                store_geo_cluster=store.geo_cluster if store else "",
                store_format_name=store.format.name if store and store.format else "",
                total_base=total_base,
                total_paid=total_paid,
                total_saved=total_saved,
                items_count=len(items_data),
            )
        )

    return PaginatedReceiptList(items=items, total=total, page=page, size=size)


@receipts_router.get("/economy", response_model=EconomyResponse)
def get_economy(
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> EconomyResponse:
    from webx5.core.purchases import receipt_repo

    summary = receipt_repo.get_economy_summary(session, user_id)
    return EconomyResponse(
        total_saved=Decimal(str(summary["total_saved"])),
        total_paid=Decimal(str(summary["total_paid"])),
        receipts_count=summary["receipts_count"],
    )


@receipts_router.get("/{receipt_id}", response_model=ReceiptDetailResponse)
def get_receipt(
    receipt_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> ReceiptDetailResponse:
    from webx5.core.purchases import receipt_repo
    from webx5.entities.store import Store

    receipt = receipt_repo.get_by_id(session, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if receipt.loyalty_card_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    store = session.get(Store, receipt.store_id)
    items_data = receipt_repo.get_items_with_products(session, receipt.id)

    detail_items = [
        ReceiptDetailItem(
            product_id=ri.product_id,
            product_name=product.name,
            quantity=ri.quantity,
            base_price_at_purchase=Decimal(str(ri.base_price_at_purchase)),
            paid_price=Decimal(str(ri.paid_price)),
            discounted_amount=Decimal(str(ri.discounted_amount)),
            discount_id=ri.discount_id,
        )
        for ri, product in items_data
    ]

    total_base = sum(i.base_price_at_purchase * i.quantity for i in detail_items)
    total_paid = sum(i.paid_price * i.quantity for i in detail_items)

    return ReceiptDetailResponse(
        id=receipt.id,
        purchase_date=receipt.purchase_date,
        store=StoreShort(
            id=store.id,
            format_name=store.format.name if store and store.format else "",
            geo_cluster=store.geo_cluster if store else "",
        ),
        channel=receipt.channel,
        items=detail_items,
        total_base=total_base,
        total_paid=total_paid,
        total_saved=total_base - total_paid,
    )
