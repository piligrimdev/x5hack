from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from webx5.core.llm import ToolCall
from webx5.crud.basket import BasketRepository
from webx5.entities.product import Product
from webx5.schemas.basket import BasketItemIn
from webx5.services.basket_assistant import BasketService

from fastapi import HTTPException

from webx5.crud.receipt import ReceiptRepository
from webx5.crud.store import StoreRepository
from webx5.entities.store import Store
from webx5.services.discount_calculator import CalculatedItem, DiscountCalculatorService
from webx5.services.receipt import ReceiptService


def _make_product(sku_id: str, name: str, price: str = "100.00") -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku_id = sku_id
    p.name = name
    p.current_price = Decimal(price)
    p.category_id = uuid.uuid4()
    p.brand_id = None
    return p


def _make_store() -> Store:
    s = Store()
    s.id = uuid.uuid4()
    s.format_id = uuid.uuid4()
    s.geo_cluster = "d_01"
    return s


@pytest.fixture()
def repo() -> MagicMock:
    return MagicMock(spec=BasketRepository)


@pytest.fixture()
def receipt_repo() -> MagicMock:
    return MagicMock(spec=ReceiptRepository)


@pytest.fixture()
def store_repo() -> MagicMock:
    return MagicMock(spec=StoreRepository)


@pytest.fixture()
def discount_calc() -> MagicMock:
    return MagicMock(spec=DiscountCalculatorService)


@pytest.fixture()
def receipt_service() -> MagicMock:
    return MagicMock(spec=ReceiptService)


@pytest.fixture()
def service(
    repo: MagicMock,
    receipt_repo: MagicMock,
    store_repo: MagicMock,
    discount_calc: MagicMock,
    receipt_service: MagicMock,
) -> BasketService:
    return BasketService(
        repo=repo,
        receipt_repo=receipt_repo,
        store_repo=store_repo,
        discount_calc=discount_calc,
        receipt_service=receipt_service,
        model="fake/model",
    )


@pytest.fixture()
def session() -> MagicMock:
    return MagicMock()


class TestSuggest:
    def test_maps_repo_pairs_to_basket_items(
        self, service: BasketService, repo: MagicMock, session: MagicMock
    ) -> None:
        product = _make_product("sku_0001", "Молоко", price="89.90")
        repo.suggest_items.return_value = [(product, 2)]

        items = service.suggest(session, uuid.uuid4())

        assert len(items) == 1
        assert items[0].product_id == product.id
        assert items[0].name == "Молоко"
        assert items[0].quantity == 2
        assert items[0].price == Decimal("89.90")

    def test_empty_history_returns_empty_list(
        self, service: BasketService, repo: MagicMock, session: MagicMock
    ) -> None:
        repo.suggest_items.return_value = []
        assert service.suggest(session, uuid.uuid4()) == []


class TestApplyInstruction:
    def test_add_item_tool_call_adds_product(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr(
            "webx5.services.basket_assistant.call_openrouter_tools",
            lambda **kwargs: [ToolCall(name="add_item", arguments={"sku_id": "sku_0001", "quantity": 2})],
        )

        result = service.apply_instruction(session, items=[], instruction="добавь молоко")

        assert result.applied is True
        assert len(result.items) == 1
        assert result.items[0].product_id == milk.id
        assert result.items[0].quantity == 2

    def test_remove_item_tool_call_removes_existing_item(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr(
            "webx5.services.basket_assistant.call_openrouter_tools",
            lambda **kwargs: [ToolCall(name="remove_item", arguments={"sku_id": "sku_0001"})],
        )

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="убери молоко"
        )

        assert result.applied is True
        assert result.items == []

    def test_set_quantity_tool_call_overwrites_quantity(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr(
            "webx5.services.basket_assistant.call_openrouter_tools",
            lambda **kwargs: [ToolCall(name="set_quantity", arguments={"sku_id": "sku_0001", "quantity": 5})],
        )

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="пусть будет 5 молока"
        )

        assert result.items[0].quantity == 5

    def test_no_tool_calls_returns_unchanged_basket_with_message(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kwargs: [])

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="???"
        )

        assert result.applied is False
        assert result.message == "Не поняла запрос, попробуй иначе"
        assert result.items[0].quantity == 1

    def test_llm_failure_returns_unchanged_basket_with_message(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]

        def _raise(**kwargs):
            raise RuntimeError("network error")

        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", _raise)

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="добавь что-нибудь"
        )

        assert result.applied is False
        assert result.items[0].quantity == 1

    def test_unknown_sku_in_tool_call_is_ignored(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr(
            "webx5.services.basket_assistant.call_openrouter_tools",
            lambda **kwargs: [ToolCall(name="add_item", arguments={"sku_id": "sku_9999", "quantity": 1})],
        )

        result = service.apply_instruction(session, items=[], instruction="добавь что-то странное")

        assert result.applied is False
        assert result.items == []

    def test_item_with_unknown_product_id_in_request_is_dropped(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kwargs: [])

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=uuid.uuid4(), quantity=1)], instruction="???"
        )

        assert result.items == []


class TestCheckout:
    def test_applies_discount_and_uses_last_receipt_store(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        receipt_service: MagicMock,
        session: MagicMock,
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]

        store = _make_store()
        last_receipt = MagicMock(store_id=store.id)
        receipt_repo.list_by_loyalty_card.return_value = ([last_receipt], 1)
        store_repo.get_by_id.return_value = store

        discount_id = uuid.uuid4()
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id,
                product_name=milk.name,
                quantity=2,
                base_price=Decimal("100.00"),
                paid_price=Decimal("90.00"),
                discount_id=discount_id,
                discounted_amount=Decimal("10.00"),
            )
        ]

        fake_receipt = MagicMock()
        receipt_service.create_receipt.return_value = (fake_receipt, True)
        expected_response = MagicMock()
        receipt_service.build_receipt_response.return_value = expected_response

        user_id = uuid.uuid4()
        result = service.checkout(session, user_id, [BasketItemIn(product_id=milk.id, quantity=2)])

        assert result is expected_response
        store_repo.get_by_id.assert_called_once_with(session, store.id)
        receipt_service.create_receipt.assert_called_once()
        call_args = receipt_service.create_receipt.call_args.args
        assert call_args[0] is session
        created_data = call_args[2]
        assert created_data.store_id == store.id
        assert created_data.loyalty_card_id == user_id
        assert created_data.channel == "offline"
        assert created_data.items[0].discount_id == discount_id
        assert created_data.items[0].quantity == 2
        receipt_service.build_receipt_response.assert_called_once_with(session, fake_receipt)

    def test_falls_back_to_first_store_when_no_receipt_history(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        receipt_service: MagicMock,
        session: MagicMock,
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store = _make_store()
        store_repo.list_all.return_value = [store]
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id,
                product_name=milk.name,
                quantity=1,
                base_price=Decimal("50.00"),
                paid_price=Decimal("50.00"),
                discount_id=None,
                discounted_amount=Decimal("0.00"),
            )
        ]
        receipt_service.create_receipt.return_value = (MagicMock(), True)

        service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)])

        store_repo.list_all.assert_called_once_with(session)
        created_data = receipt_service.create_receipt.call_args.args[2]
        assert created_data.store_id == store.id

    def test_empty_basket_raises_422(self, service: BasketService, session: MagicMock) -> None:
        with pytest.raises(HTTPException) as exc_info:
            service.checkout(session, uuid.uuid4(), [])
        assert exc_info.value.status_code == 422

    def test_unknown_product_id_raises_422(
        self, service: BasketService, repo: MagicMock, session: MagicMock
    ) -> None:
        repo.get_full_catalog.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=uuid.uuid4(), quantity=1)])
        assert exc_info.value.status_code == 422

    def test_no_stores_available_raises_422(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)])
        assert exc_info.value.status_code == 422
