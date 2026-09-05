from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from webx5.core.basket import basket_service
from webx5.core.celery_app import celery_app
from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.basket import (
    AssistantRequest,
    AssistantTaskEnqueuedResponse,
    AssistantTaskResultResponse,
    BasketPreviewRequest,
    CheckoutRequest,
    SuggestedBasketResponse,
)
from webx5.schemas.receipt import CalculateResponse, ReceiptResponse

basket_router = APIRouter(prefix="/basket", tags=["Basket"])


@basket_router.get("/suggested", response_model=SuggestedBasketResponse)
def get_suggested_basket(session: SessionDep, user_id: CurrentUserUUID) -> SuggestedBasketResponse:
    items = basket_service.suggest(session, user_id)
    return SuggestedBasketResponse(items=items)


@basket_router.post("/preview", response_model=CalculateResponse)
def post_basket_preview(
    data: BasketPreviewRequest,
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> CalculateResponse:
    return basket_service.preview(session, user_id, data.items, data.points_to_spend)


@basket_router.post("/assistant", response_model=AssistantTaskEnqueuedResponse, status_code=202)
def post_basket_assistant(
    data: AssistantRequest,
    _user_id: CurrentUserUUID,
) -> JSONResponse:
    from webx5.tasks.basket import basket_apply_instruction

    items_json = json.dumps([item.model_dump(mode="json") for item in data.items])
    async_result = basket_apply_instruction.delay(
        str(_user_id), items_json, data.instruction
    )
    return JSONResponse(
        status_code=202,
        content={"task_id": async_result.id, "status": "pending"},
    )


@basket_router.get("/assistant/{task_id}", response_model=AssistantTaskResultResponse)
def get_basket_assistant_result(task_id: str) -> AssistantTaskResultResponse:
    from webx5.schemas.basket import AssistantResponse

    result = celery_app.AsyncResult(task_id)
    if result.state == "SUCCESS":
        return AssistantTaskResultResponse(
            status="complete",
            result=AssistantResponse(**result.result),
        )
    if result.state == "FAILURE":
        return AssistantTaskResultResponse(status="failed")
    return AssistantTaskResultResponse(status="pending")


@basket_router.post("/checkout", response_model=ReceiptResponse, status_code=201)
def post_basket_checkout(
    data: CheckoutRequest,
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> ReceiptResponse:
    return basket_service.checkout(session, user_id, data.items, data.points_to_spend)
