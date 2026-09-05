"""Celery task: apply a natural-language instruction to a user's basket via LLM."""

from __future__ import annotations

import json

import structlog

from webx5.core.celery_app import celery_app

logger = structlog.get_logger("tasks.basket")


@celery_app.task(name="webx5.tasks.basket.basket_apply_instruction", queue="receipts")
def basket_apply_instruction(user_id_str: str, items_json: str, instruction: str) -> dict:
    from webx5.core.basket import basket_service
    from webx5.core.db import db
    from webx5.schemas.basket import BasketItemIn

    logger.info("basket_apply_instruction.enter", instruction_len=len(instruction))

    raw_items: list[dict] = json.loads(items_json)
    items = [BasketItemIn(**item) for item in raw_items]

    with db.get_sync_session() as session:
        result = basket_service.apply_instruction(session, items=items, instruction=instruction)

    logger.info(
        "basket_apply_instruction.done",
        applied=result.applied,
        items_count=len(result.items),
    )
    return result.model_dump(mode="json")
