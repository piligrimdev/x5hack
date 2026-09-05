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
from webx5.services.points import CashbackPreview, PointsService
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
    repo = MagicMock(spec=BasketRepository)
    repo.get_shopping_context.return_value = {"purchases": [], "challenges": []}
    return repo


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
def points_service() -> MagicMock:
    return MagicMock(spec=PointsService)


@pytest.fixture()
def service(
    repo: MagicMock,
    receipt_repo: MagicMock,
    store_repo: MagicMock,
    discount_calc: MagicMock,
    receipt_service: MagicMock,
    points_service: MagicMock,
) -> BasketService:
    service = BasketService(
        repo=repo,
        receipt_repo=receipt_repo,
        store_repo=store_repo,
        discount_calc=discount_calc,
        receipt_service=receipt_service,
        points_service=points_service,
        model="fake/model",
    )
    service._catalog_prices = MagicMock(side_effect=lambda session, user, catalog: {pid: p.current_price for pid, p in catalog.items()})
    return service


@pytest.fixture()
def session() -> MagicMock:
    return MagicMock()


class TestSuggest:
    def test_llm_selects_weekly_quantities_with_personal_context(
        self, service, repo, session, monkeypatch,
    ):
        milk = _make_product("sku_0001", "Молоко", "89.90")
        repo.get_full_catalog.return_value = [milk]
        repo.get_shopping_context.return_value = {"purchases": [{"sku_id": "sku_0001", "weekly_quantity": 4}]}
        call = MagicMock(return_value=[ToolCall("replace_basket", {"items": [{"sku_id": "sku_0001", "quantity": 4}]})])
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", call)
        user = uuid.uuid4()
        items = service.suggest(session, user)
        assert items[0].quantity == 4
        assert items[0].price == Decimal("89.90")
        repo.get_shopping_context.assert_called_once_with(session, user)
        assert '"weekly_quantity":4' in call.call_args.kwargs["system"]
        repo.suggest_items.assert_not_called()

    def test_new_user_is_also_served_by_llm(self, service, repo, session, monkeypatch):
        repo.get_full_catalog.return_value = [_make_product("milk", "Молоко")]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kw: [
            ToolCall("replace_basket", {"items": [{"sku_id": "milk", "quantity": 2}]})])
        assert service.suggest(session, uuid.uuid4())[0].quantity == 2

    @pytest.mark.parametrize("items", [[], [{"sku_id": "unknown", "quantity": 1}],
        [{"sku_id": "milk", "quantity": True}], [{"sku_id": "milk", "quantity": 51}],
        [{"sku_id": "milk", "quantity": 1}, {"sku_id": "milk", "quantity": 2}]])
    def test_invalid_output_fails_without_statistical_fallback(self, service, repo, session, monkeypatch, items):
        repo.get_full_catalog.return_value = [_make_product("milk", "Молоко")]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kw: [ToolCall("replace_basket", {"items": items})])
        with pytest.raises(HTTPException) as exc:
            service.suggest(session, uuid.uuid4())
        assert exc.value.status_code == 503
        repo.suggest_items.assert_not_called()

    def test_network_failure_is_retryable(self, service, repo, session, monkeypatch):
        repo.get_full_catalog.return_value = [_make_product("milk", "Молоко")]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", MagicMock(side_effect=RuntimeError("offline")))
        with pytest.raises(HTTPException) as exc:
            service.suggest(session, uuid.uuid4())
        assert exc.value.status_code == 503


class TestApplyInstruction:
    def test_recipe_tool_counts_existing_ingredients_and_keeps_missing_notice(self, service, repo, session, monkeypatch):
        chicken, salad, milk = _make_product("chicken", "Курица"), _make_product("salad", "Салат"), _make_product("milk", "Молоко")
        repo.get_full_catalog.return_value = [chicken, salad, milk]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kw: [
            ToolCall("add_recipe_ingredients", {"items": [{"sku_id": "chicken", "quantity": 1}, {"sku_id": "salad", "quantity": 1}],
                                                "missing_ingredients": ["Пармезан"]})])
        initial = [BasketItemIn(product_id=chicken.id, quantity=2), BasketItemIn(product_id=milk.id, quantity=1)]
        result = service.apply_instruction(session, items=initial, instruction="цезарь")
        assert {i.product_id: i.quantity for i in result.items} == {chicken.id: 2, milk.id: 1, salad.id: 1}
        assert "Пармезан" in result.message
        repeated = service.apply_instruction(session, items=[BasketItemIn(product_id=i.product_id, quantity=i.quantity) for i in result.items], instruction="цезарь")
        assert not repeated.applied
        assert repeated.items == result.items

    def test_invalid_recipe_is_atomic(self, service, repo, session, monkeypatch):
        milk = _make_product("milk", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kw: [
            ToolCall("add_recipe_ingredients", {"items": [{"sku_id": "milk", "quantity": 2}, {"sku_id": "unknown", "quantity": 1}], "missing_ingredients": []})])
        result = service.apply_instruction(session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="ингредиенты")
        assert not result.applied and result.items[0].quantity == 1


    def test_recipe_adds_multiple_ingredients_and_preserves_other_items(self, service, repo, session, monkeypatch):
        milk = _make_product("milk", "Молоко")
        chicken = _make_product("chicken", "Куриное филе")
        salad = _make_product("salad", "Салат романо")
        repo.get_full_catalog.return_value = [milk, chicken, salad]
        call = MagicMock(return_value=[
            ToolCall("add_item", {"sku_id": "chicken", "quantity": 1}),
            ToolCall("add_item", {"sku_id": "salad", "quantity": 1}),
        ])
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", call)
        result = service.apply_instruction(session, items=[BasketItemIn(product_id=milk.id, quantity=2)], instruction="ингридиенты для цезаря")
        assert result.applied
        assert {item.product_id: item.quantity for item in result.items} == {milk.id: 2, chicken.id: 1, salad.id: 1}
        assert call.call_args.kwargs["tool_choice"] == "required"

    @pytest.mark.parametrize("add_available", [False, True])
    def test_explanation_is_returned_with_or_without_changes(self, service, repo, session, monkeypatch, add_available):
        milk = _make_product("milk", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        calls = [ToolCall("explain", {"message": "Салата романо сейчас нет в каталоге"})]
        if add_available:
            calls.insert(0, ToolCall("add_item", {"sku_id": "milk", "quantity": 1}))
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kw: calls)
        result = service.apply_instruction(session, items=[], instruction="нужны молоко и романо")
        assert result.applied is add_available
        assert result.message == "Салата романо сейчас нет в каталоге"


    def test_replace_basket_uses_user_context(self, service, repo, session, monkeypatch):
        milk = _make_product("milk", "Молоко")
        bread = _make_product("bread", "Хлеб")
        repo.get_full_catalog.return_value = [milk, bread]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kw: [
            ToolCall("replace_basket", {"items": [{"sku_id": "bread", "quantity": 2}]})])
        user = uuid.uuid4()
        result = service.apply_instruction(session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="собери заново", user_id=user)
        assert result.applied
        assert [item.product_id for item in result.items] == [bread.id]
        repo.get_shopping_context.assert_called_once_with(session, user)


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

    def test_points_to_spend_forwarded_to_receipt_create(
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
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = [store]
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id, product_name=milk.name, quantity=1,
                base_price=Decimal("100.00"), paid_price=Decimal("100.00"),
                discount_id=None, discounted_amount=Decimal("0.00"),
            )
        ]
        receipt_service.create_receipt.return_value = (MagicMock(), True)

        service.checkout(
            session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)], points_to_spend="all"
        )

        created_data = receipt_service.create_receipt.call_args.args[2]
        assert created_data.points_to_spend == "all"

    def test_points_to_spend_defaults_to_none(
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
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = [store]
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id, product_name=milk.name, quantity=1,
                base_price=Decimal("100.00"), paid_price=Decimal("100.00"),
                discount_id=None, discounted_amount=Decimal("0.00"),
            )
        ]
        receipt_service.create_receipt.return_value = (MagicMock(), True)

        service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)])

        created_data = receipt_service.create_receipt.call_args.args[2]
        assert created_data.points_to_spend is None


class TestPreview:
    def test_returns_priced_items_with_discount_and_cashback(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        points_service: MagicMock,
        session: MagicMock,
    ) -> None:
        milk = _make_product("sku_0001", "Молоко", price="100.00")
        repo.get_full_catalog.return_value = [milk]

        store = _make_store()
        last_receipt = MagicMock(store_id=store.id)
        receipt_repo.list_by_loyalty_card.return_value = ([last_receipt], 1)
        store_repo.get_by_id.return_value = store

        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id,
                product_name=milk.name,
                quantity=2,
                base_price=Decimal("100.00"),
                paid_price=Decimal("90.00"),
                discount_id=uuid.uuid4(),
                discounted_amount=Decimal("10.00"),
            )
        ]
        points_service.preview_for_calculate.return_value = CashbackPreview(
            points_available=500,
            points_to_apply=0,
            cashback_rub=0,
            total_paid_rub=180,
            points_balance_after=500,
            points_capped_by="none",
            rate_points_per_rub=10,
        )

        user_id = uuid.uuid4()
        result = service.preview(session, user_id, [BasketItemIn(product_id=milk.id, quantity=2)])

        assert result.store_id == store.id
        assert result.items[0].base_price == Decimal("100.00")
        assert result.items[0].paid_price == Decimal("90.00")
        assert result.total_base == Decimal("200.00")
        assert result.total_paid == Decimal("180.00")
        assert result.total_saved == Decimal("20.00")
        assert result.cashback is not None
        assert result.cashback.points_available == 500
        points_service.preview_for_calculate.assert_called_once_with(
            session, loyalty_card_id=user_id, points_requested_raw=None, subtotal_rub=180
        )

    def test_empty_basket_returns_zero_totals_not_422(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        points_service: MagicMock,
        session: MagicMock,
    ) -> None:
        repo.get_full_catalog.return_value = []
        store = _make_store()
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = [store]
        discount_calc.calculate.return_value = []
        points_service.preview_for_calculate.return_value = None

        result = service.preview(session, uuid.uuid4(), [])

        assert result.items == []
        assert result.total_base == Decimal("0")
        assert result.total_paid == Decimal("0")
        assert result.cashback is None

    def test_unknown_product_id_raises_422(
        self, service: BasketService, repo: MagicMock, session: MagicMock
    ) -> None:
        repo.get_full_catalog.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            service.preview(session, uuid.uuid4(), [BasketItemIn(product_id=uuid.uuid4(), quantity=1)])
        assert exc_info.value.status_code == 422

    def test_points_to_spend_forwarded_to_points_service(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        points_service: MagicMock,
        session: MagicMock,
    ) -> None:
        repo.get_full_catalog.return_value = []
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = [_make_store()]
        discount_calc.calculate.return_value = []
        points_service.preview_for_calculate.return_value = None

        service.preview(session, uuid.uuid4(), [], points_to_spend="all")

        assert points_service.preview_for_calculate.call_args.kwargs["points_requested_raw"] == "all"


class TestResolveStoreViaCheckout:
    """checkout() must keep working unchanged after the _resolve_store extraction."""

    def test_checkout_still_uses_last_receipt_store(
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
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id, product_name=milk.name, quantity=1,
                base_price=Decimal("50.00"), paid_price=Decimal("50.00"),
                discount_id=None, discounted_amount=Decimal("0.00"),
            )
        ]
        receipt_service.create_receipt.return_value = (MagicMock(), True)

        service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)])

        store_repo.get_by_id.assert_called_once_with(session, store.id)
