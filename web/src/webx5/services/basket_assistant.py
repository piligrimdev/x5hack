from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from webx5.core.llm import call_openrouter_tools
from webx5.crud.basket import BasketRepository
from webx5.crud.receipt import ReceiptRepository
from webx5.crud.store import StoreRepository
from webx5.entities.product import Product
from webx5.schemas.basket import AssistantResponse, BasketItem, BasketItemIn
from webx5.schemas.receipt import ReceiptCreate, ReceiptItemCreate, ReceiptResponse
from webx5.services.discount_calculator import CartItem, DiscountCalculatorService
from webx5.services.receipt import ReceiptService

logger = structlog.get_logger(__name__)

CANNOT_UNDERSTAND_MESSAGE = "Не поняла запрос, попробуй иначе"
LLM_FAILURE_MESSAGE = "Не получилось обработать запрос, попробуй ещё раз"
CHECKOUT_EMPTY_BASKET_MESSAGE = "Корзина пуста"
CHECKOUT_NO_STORES_MESSAGE = "Не найдено ни одного магазина"

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
    def __init__(
        self,
        repo: BasketRepository,
        receipt_repo: ReceiptRepository,
        store_repo: StoreRepository,
        discount_calc: DiscountCalculatorService,
        receipt_service: ReceiptService,
        model: str = "anthropic/claude-haiku-4.5",
    ) -> None:
        self.repo = repo
        self.receipt_repo = receipt_repo
        self.store_repo = store_repo
        self.discount_calc = discount_calc
        self.receipt_service = receipt_service
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

    def checkout(
        self,
        session: Session,
        user_id: uuid.UUID,
        items: list[BasketItemIn],
    ) -> ReceiptResponse:
        if not items:
            raise HTTPException(status_code=422, detail=CHECKOUT_EMPTY_BASKET_MESSAGE)

        catalog = self.repo.get_full_catalog(session)
        catalog_by_id = {p.id: p for p in catalog}
        missing = [str(i.product_id) for i in items if i.product_id not in catalog_by_id]
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"detail": "Unknown product_ids", "unknown_product_ids": missing},
            )

        receipts, _total = self.receipt_repo.list_by_loyalty_card(session, user_id, page=1, size=1)
        if receipts:
            store = self.store_repo.get_by_id(session, receipts[0].store_id)
        else:
            stores = self.store_repo.list_all(session)
            if not stores:
                raise HTTPException(status_code=422, detail=CHECKOUT_NO_STORES_MESSAGE)
            store = stores[0]

        cart_items = [CartItem(product_id=i.product_id, quantity=i.quantity) for i in items]
        calculated = self.discount_calc.calculate(
            items=cart_items, store=store, loyalty_card_id=user_id, session=session
        )
        receipt_items = [
            ReceiptItemCreate(product_id=c.product_id, quantity=c.quantity, discount_id=c.discount_id)
            for c in calculated
        ]
        data = ReceiptCreate(
            loyalty_card_id=user_id,
            store_id=store.id,
            channel="offline",
            items=receipt_items,
        )
        receipt, _is_new = self.receipt_service.create_receipt(session, uuid.uuid4(), data)
        return self.receipt_service.build_receipt_response(session, receipt)

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
