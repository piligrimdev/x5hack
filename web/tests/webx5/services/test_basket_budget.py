from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

import pytest

from webx5.core.llm import ToolCall
from webx5.services.basket_assistant import BasketService


def setup():
    products = [SimpleNamespace(id=uuid.uuid4(), sku_id=sku, current_price=Decimal(price), name=sku)
                for sku, price in [('dinner', '650.10'), ('dessert', '49.90'), ('expensive', '800')]]
    return BasketService(*[MagicMock() for _ in range(6)]), {p.id: p for p in products}, products


def candidate(*skus):
    return {'items': [{'sku_id': sku, 'quantity': 1} for sku in skus]}


def test_selects_nearest_affordable_variant_with_decimal_prices():
    service, catalog, products = setup()
    result = service._apply_budget_basket({}, catalog, {'budget_rub': 700, 'mode': 'replace', 'candidates': [
        candidate('dinner'), candidate('expensive'), candidate('dinner', 'dessert')]}, '', '', None)
    assert result.applied
    assert sum(i.price * i.quantity for i in result.items) == Decimal('700.00')
    assert '700.00' in result.message


def test_retries_over_budget_proposal(monkeypatch):
    service, catalog, _ = setup()
    retry = MagicMock(return_value=[ToolCall('build_budget_basket', {'candidates': [candidate('dinner')]})])
    monkeypatch.setattr('webx5.services.basket_assistant.call_openrouter_tools', retry)
    result = service._apply_budget_basket({}, catalog, {'budget_rub': 700, 'mode': 'replace', 'candidates': [candidate('expensive')]}, '', 'ужин на 700', None)
    assert result.applied
    assert result.items[0].price == Decimal('650.10')
    retry.assert_called_once()


def test_failed_retry_cannot_raise_budget_or_change_existing_basket(monkeypatch):
    service, catalog, products = setup()
    monkeypatch.setattr('webx5.services.basket_assistant.call_openrouter_tools', lambda **kw: [
        ToolCall('build_budget_basket', {'budget_rub': 900, 'mode': 'replace', 'candidates': [candidate('expensive')]})])
    current = {products[1].id: 1}
    result = service._apply_budget_basket(current, catalog, {'budget_rub': 700, 'mode': 'add', 'candidates': [candidate('expensive')]}, '', '', None)
    assert not result.applied
    assert [(i.product_id, i.quantity) for i in result.items] == list(current.items())


def test_add_mode_counts_existing_items_in_total(monkeypatch):
    service, catalog, products = setup()
    monkeypatch.setattr('webx5.services.basket_assistant.call_openrouter_tools', MagicMock(side_effect=RuntimeError()))
    result = service._apply_budget_basket({products[1].id: 2}, catalog, {'budget_rub': 700, 'mode': 'add', 'candidates': [candidate('dinner')]}, '', '', None)
    assert not result.applied  # 650.10 + 99.80 exceeds 700


def test_budget_tool_is_atomic_even_with_extra_tool_calls(monkeypatch):
    service, catalog, products = setup()
    for p in products:
        p.category = None
    service.repo.get_full_catalog.return_value = list(catalog.values())
    monkeypatch.setattr('webx5.services.basket_assistant.call_openrouter_tools', lambda **kw: [
        ToolCall('build_budget_basket', {'budget_rub': 700, 'mode': 'replace', 'candidates': [candidate('dinner')]}),
        ToolCall('add_item', {'sku_id': 'expensive', 'quantity': 1})])
    result = service.apply_instruction(MagicMock(), items=[], instruction='ужин на 700')
    assert result.applied
    assert sum(i.price * i.quantity for i in result.items) <= 700


def test_budget_uses_discounted_prices_instead_of_base():
    service, catalog, products = setup()
    prices = {p.id: p.current_price for p in products}
    prices[products[2].id] = Decimal('600')  # base 800, actually 600 after discount
    result = service._apply_budget_basket({}, catalog, {'budget_rub': 700, 'mode': 'replace',
        'candidates': [candidate('expensive')]}, '', '', None, prices)
    assert result.applied
    assert '600.00' in result.message
    assert 'с учётом скидок' in result.message


def test_catalog_prices_use_checkout_store_and_loyalty_card():
    service, catalog, products = setup()
    session, store = MagicMock(), MagicMock()
    user_id = uuid.uuid4()
    service._resolve_store = MagicMock(return_value=store)
    service.discount_calc.calculate.return_value = [SimpleNamespace(product_id=p.id, paid_price=Decimal('50')) for p in products]
    prices = service._catalog_prices(session, user_id, catalog)
    assert all(price == 50 for price in prices.values())
    kwargs = service.discount_calc.calculate.call_args.kwargs
    assert kwargs['store'] is store and kwargs['loyalty_card_id'] == user_id
    assert {i.product_id for i in kwargs['items']} == set(catalog)
    for p in products:
        p.category = None
    import json
    data = json.loads(service._build_system_prompt({}, catalog, {}, prices).rsplit('\n', 1)[1])
    assert data['catalog'][0]['price_rub'] == 50
    assert data['catalog'][0]['base_price_rub'] == float(products[0].current_price)


@pytest.mark.parametrize('instruction', [
    'ужин на 700 рублей',
    'корзина на 1 500 ₽',
    'бюджет около 900',
    'не дороже 650',
    'обед на 800',
])
def test_explicit_budget_detection(instruction):
    assert BasketService._has_explicit_budget(instruction)


@pytest.mark.parametrize('instruction', [
    'ингредиенты для цезаря',
    'ужин на двоих',
    'борщ на 4 порции',
    'добавь 2 молока',
    'собери корзину на неделю',
])
def test_quantities_and_meal_size_are_not_mistaken_for_budget(instruction):
    assert not BasketService._has_explicit_budget(instruction)


def test_non_budget_request_does_not_expose_budget_tool_or_historical_spend(monkeypatch):
    service, catalog, products = setup()
    for product in products:
        product.category = None
    service.repo.get_full_catalog.return_value = products
    service.repo.get_shopping_context.return_value = {
        'typical_weekly_spend_rub': 1234,
        'purchases': [],
        'challenges': [],
    }
    service._catalog_prices = lambda session, user, items: {
        product_id: product.current_price for product_id, product in items.items()
    }
    llm = MagicMock(return_value=[ToolCall(
        'add_recipe_ingredients',
        {'items': [candidate('dinner')['items'][0]], 'missing_ingredients': []},
    )])
    monkeypatch.setattr('webx5.services.basket_assistant.call_openrouter_tools', llm)

    result = service.apply_instruction(
        MagicMock(), items=[], instruction='ингредиенты для ужина на двоих', user_id=uuid.uuid4()
    )

    assert result.applied
    tool_names = {tool['function']['name'] for tool in llm.call_args.kwargs['tools']}
    assert 'build_budget_basket' not in tool_names
    assert 'typical_weekly_spend_rub' not in llm.call_args.kwargs['system']
