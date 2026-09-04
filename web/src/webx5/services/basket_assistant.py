from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from sqlalchemy.orm import Session

from webx5.core.llm import call_openrouter_tools
from webx5.crud.basket import BasketRepository
from webx5.entities.product import Product
from webx5.schemas.basket import AssistantResponse, BasketItem, BasketItemIn

logger = structlog.get_logger(__name__)

CANNOT_UNDERSTAND_MESSAGE = "Не поняла запрос, попробуй иначе"
LLM_FAILURE_MESSAGE = "Не получилось обработать запрос, попробуй ещё раз"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_item",
            "description": "Add a product to the basket, or increase its quantity if already present",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_id": {"type": "string", "description": "catalog SKU id, e.g. sku_0042"},
                    "quantity": {"type": "integer", "description": "how many units to add"},
                },
                "required": ["sku_id", "quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_item",
            "description": "Remove a product from the basket entirely",
            "parameters": {
                "type": "object",
                "properties": {"sku_id": {"type": "string", "description": "catalog SKU id, e.g. sku_0042"}},
                "required": ["sku_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_quantity",
            "description": "Set the exact quantity of a product already in the basket",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_id": {"type": "string", "description": "catalog SKU id, e.g. sku_0042"},
                    "quantity": {"type": "integer", "description": "the new exact quantity"},
                },
                "required": ["sku_id", "quantity"],
            },
        },
    },
]


class BasketService:
    def __init__(self, repo: BasketRepository, model: str = "deepseek/deepseek-chat") -> None:
        self.repo = repo
        self.model = model

    def suggest(self, session: Session, user_id: uuid.UUID) -> list[BasketItem]:
        pairs = self.repo.suggest_items(session, user_id)
        return [self._to_basket_item(p, qty) for p, qty in pairs]

    def apply_instruction(
        self,
        session: Session,
        items: list[BasketItemIn],
        instruction: str,
        api_key: str | None = None,
    ) -> AssistantResponse:
        catalog = self.repo.get_full_catalog(session)
        catalog_by_id: dict[uuid.UUID, Product] = {p.id: p for p in catalog}
        catalog_by_sku: dict[str, Product] = {p.sku_id: p for p in catalog}

        current: dict[uuid.UUID, int] = {
            item.product_id: item.quantity for item in items if item.product_id in catalog_by_id
        }

        system = self._build_system_prompt(current, catalog_by_id)
        try:
            tool_calls = call_openrouter_tools(
                model=self.model, system=system, user=instruction, tools=TOOLS, api_key=api_key
            )
        except Exception as e:  # noqa: BLE001 — any LLM failure must fall back, not propagate
            logger.warning("basket_assistant.llm_call_failed", error=str(e))
            return self._response(current, catalog_by_id, applied=False, message=LLM_FAILURE_MESSAGE)

        applied_any = False
        for call in tool_calls:
            sku_id = call.arguments.get("sku_id")
            product = catalog_by_sku.get(sku_id) if isinstance(sku_id, str) else None
            if product is None:
                continue
            if call.name == "add_item":
                quantity = call.arguments.get("quantity")
                if not isinstance(quantity, int) or quantity < 1:
                    continue
                current[product.id] = current.get(product.id, 0) + quantity
                applied_any = True
            elif call.name == "remove_item":
                if current.pop(product.id, None) is not None:
                    applied_any = True
            elif call.name == "set_quantity":
                quantity = call.arguments.get("quantity")
                if not isinstance(quantity, int):
                    continue
                if quantity < 1:
                    current.pop(product.id, None)
                else:
                    current[product.id] = quantity
                applied_any = True

        if not applied_any:
            logger.info("basket_assistant.no_applicable_tool_calls", instruction=instruction)
            return self._response(current, catalog_by_id, applied=False, message=CANNOT_UNDERSTAND_MESSAGE)
        return self._response(current, catalog_by_id, applied=True, message=None)

    def _build_system_prompt(self, current: dict[uuid.UUID, int], catalog_by_id: dict[uuid.UUID, Product]) -> str:
        current_lines = (
            "\n".join(f"- {catalog_by_id[pid].sku_id} ({catalog_by_id[pid].name}): {qty} шт" for pid, qty in current.items())
            or "(пусто)"
        )
        catalog_lines = "\n".join(f"- {p.sku_id}: {p.name}" for p in catalog_by_id.values())
        return (
            "Ты — ассистент корзины покупок в приложении лояльности X5. "
            "Пользователь просит добавить или убрать товары из своей текущей корзины. "
            "Используй ТОЛЬКО доступные функции (add_item/remove_item/set_quantity), "
            "передавай sku_id ровно как он указан в каталоге ниже, ничего не выдумывай.\n\n"
            f"Текущая корзина:\n{current_lines}\n\n"
            f"Каталог доступных товаров:\n{catalog_lines}"
        )

    @staticmethod
    def _to_basket_item(product: Product, quantity: int) -> BasketItem:
        return BasketItem(
            product_id=product.id, name=product.name, quantity=quantity, price=Decimal(str(product.current_price))
        )

    def _response(
        self,
        current: dict[uuid.UUID, int],
        catalog_by_id: dict[uuid.UUID, Product],
        applied: bool,
        message: str | None,
    ) -> AssistantResponse:
        items = [self._to_basket_item(catalog_by_id[pid], qty) for pid, qty in current.items()]
        return AssistantResponse(items=items, applied=applied, message=message)
