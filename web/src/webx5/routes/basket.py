from __future__ import annotations

from fastapi import APIRouter

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.basket import (
    AssistantRequest,
    AssistantResponse,
    BasketPreviewRequest,
    CheckoutRequest,
    SuggestedBasketResponse,
)
from webx5.schemas.receipt import CalculateResponse, ReceiptResponse

basket_router = APIRouter(prefix="/basket", tags=["Basket"])


@basket_router.get("/suggested", response_model=SuggestedBasketResponse)
def get_suggested_basket(session: SessionDep, user_id: CurrentUserUUID) -> SuggestedBasketResponse:
    from webx5.core.basket import basket_service

    items = basket_service.suggest(session, user_id)
    return SuggestedBasketResponse(items=items)


@basket_router.post("/preview", response_model=CalculateResponse)
def post_basket_preview(
    data: BasketPreviewRequest,
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> CalculateResponse:
    from webx5.core.basket import basket_service

    return basket_service.preview(session, user_id, data.items, data.points_to_spend)


@basket_router.post("/assistant", response_model=AssistantResponse)
def post_basket_assistant(
    data: AssistantRequest,
    session: SessionDep,
    _user_id: CurrentUserUUID,
) -> AssistantResponse:
    from webx5.core.basket import basket_service

    return basket_service.apply_instruction(session, items=data.items, instruction=data.instruction)


@basket_router.post("/checkout", response_model=ReceiptResponse, status_code=201)
def post_basket_checkout(
    data: CheckoutRequest,
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> ReceiptResponse:
    from webx5.core.basket import basket_service

    return basket_service.checkout(session, user_id, data.items)
