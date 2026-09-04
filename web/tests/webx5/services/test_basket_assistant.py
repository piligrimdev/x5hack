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


def _make_product(sku_id: str, name: str, price: str = "100.00") -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku_id = sku_id
    p.name = name
    p.current_price = Decimal(price)
    p.category_id = uuid.uuid4()
    p.brand_id = None
    return p


@pytest.fixture()
def repo() -> MagicMock:
    return MagicMock(spec=BasketRepository)


@pytest.fixture()
def service(repo: MagicMock) -> BasketService:
    return BasketService(repo=repo, model="fake/model")


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
