from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
import json
import uuid

from webx5.crud.basket import BasketRepository
from webx5.core.llm import ToolCall
from webx5.schemas.basket import BasketItemIn
from webx5.services.basket_assistant import BasketService


def product(sku, category_id=None, category='Молочные продукты'):
    return SimpleNamespace(id=uuid.uuid4(), sku_id=sku, name=sku, current_price=Decimal('100'),
                           category_id=category_id or uuid.uuid4(), category=SimpleNamespace(name=category))


def task(criterion_type, entity_id):
    return SimpleNamespace(title='Купить продукты', description='Тестовое задание',
                           criterion_type=criterion_type, criterion_entity_id=entity_id,
                           quantity_target=4, quantity_current=1, deadline=datetime.now(timezone.utc),
                           criteria=[SimpleNamespace(kind='item_quantity', key=None, value_num=Decimal(4), value_text=None)])


def test_product_task_exposes_exact_sku_and_remaining_progress():
    milk, other = product('milk'), product('other')
    result = BasketRepository.challenge_context(task('product', milk.id), [milk, other], set())
    assert result['matching_sku_ids'] == ['milk']
    assert result['quantity_remaining'] == 3
    assert result['quantity_current'] == 1
    assert result['supported']


def test_category_task_exposes_alternatives_excluding_forbidden_products():
    category_id = uuid.uuid4()
    catalog = [product('milk', category_id), product('kefir', category_id),
               product('excluded', category_id, 'Алкоголь'), product('other')]
    result = BasketRepository.challenge_context(task('category', category_id), catalog, {'Алкоголь'})
    assert result['matching_sku_ids'] == ['milk', 'kefir']


def test_spend_threshold_is_exposed_separately_from_quantity():
    milk = product('milk')
    challenge = task('product', milk.id)
    challenge.criteria.append(SimpleNamespace(kind='spend_threshold_rub', key=None, value_num=Decimal('700'), value_text=None))
    result = BasketRepository.challenge_context(challenge, [milk], set())
    assert result['criteria'][1]['value_num'] == 700
    assert result['quantity_remaining'] == 3
    assert result['all_criteria_required']


def test_unsupported_brand_is_not_presented_as_completable():
    result = BasketRepository.challenge_context(task('brand', uuid.uuid4()), [product('milk')], set())
    assert not result['supported']
    assert result['matching_sku_ids'] == []


def test_assistant_receives_task_skus_and_existing_basket(monkeypatch):
    milk = product('milk')
    repo = MagicMock()
    repo.get_full_catalog.return_value = [milk]
    repo.get_shopping_context.return_value = {
        'challenges': [BasketRepository.challenge_context(task('product', milk.id), [milk], set())]}
    llm = MagicMock(return_value=[ToolCall('add_challenge_products', {'preferred_sku_ids': ['milk']})])
    monkeypatch.setattr('webx5.services.basket_assistant.call_openrouter_tools', llm)
    service = BasketService(repo, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
    service._catalog_prices = lambda session, user, catalog: {pid: p.current_price for pid, p in catalog.items()}
    user_id = uuid.uuid4()
    result = service.apply_instruction(MagicMock(), items=[BasketItemIn(product_id=milk.id, quantity=1)],
                                       instruction='Собери все товары из заданий', user_id=user_id)
    data = json.loads(llm.call_args.kwargs['system'].rsplit('\n', 1)[1])
    assert data['personal_context']['challenges'][0]['matching_sku_ids'] == ['milk']
    assert data['current_basket'][0]['quantity'] == 1
    assert data['personal_context']['challenges'][0]['quantity_in_basket'] == 1
    assert data['personal_context']['challenges'][0]['quantity_to_add'] == 2
    assert result.items[0].quantity == 3
    assert repo.get_shopping_context.call_args.args[1] == user_id


def test_overlapping_tasks_add_exact_missing_quantity():
    category = uuid.uuid4()
    milk, kefir, bread = product('milk', category), product('kefir', category), product('bread')
    exact = task('product', milk.id)  # remaining: 3
    broad = task('category', category)
    broad.quantity_target = 5  # remaining: 4
    catalog = [milk, kefir, bread]
    context = {'challenges': [BasketRepository.challenge_context(t, catalog, set()) for t in [broad, exact]]}
    result, message = BasketService._add_challenge_products(
        {milk.id: 1, bread.id: 2}, {p.id: p for p in catalog}, context, {'preferred_sku_ids': ['kefir']})
    assert result == {milk.id: 3, kefir.id: 1, bread.id: 2}
    assert message is None
    again, message = BasketService._add_challenge_products(result, {p.id: p for p in catalog}, context, {})
    assert again == result
    assert 'уже в корзине' in message


def test_no_tasks_leaves_basket_unchanged():
    milk = product('milk')
    current = {milk.id: 1}
    result, message = BasketService._add_challenge_products(current, {milk.id: milk}, {'challenges': []}, {})
    assert result == current
    assert 'нет активных заданий' in message
