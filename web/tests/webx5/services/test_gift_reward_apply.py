"""Unit tests for gift reward application logic.

Tests cover:
1. Gift reward not applied when product not in cart
2. Gift reward applied to cheapest item in a category
3. Gift reward marked used after receipt creation with matching product
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from webx5.crud.discount import DiscountRepository
from webx5.crud.reward import GiftRewardRepository
from webx5.entities.product import Product
from webx5.entities.reward import GiftReward
from webx5.services.discount_calculator import CalculatedItem, CartItem, DiscountCalculatorService


def _make_product(
    *,
    price: str = "100.00",
    category_id: uuid.UUID | None = None,
) -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.name = "Test Product"
    p.sku_id = f"sku_{uuid.uuid4().hex[:6]}"
    p.current_price = Decimal(price)
    p.category_id = category_id or uuid.uuid4()
    p.brand_id = None
    return p


def _make_gift_reward(
    *,
    criterion_type: str = "product",
    criterion_entity_id: uuid.UUID | None = None,
    loyalty_card_id: uuid.UUID | None = None,
    quantity: int = 1,
) -> GiftReward:
    r = GiftReward()
    r.id = uuid.uuid4()
    r.task_id = None
    r.loyalty_card_id = loyalty_card_id or uuid.uuid4()
    r.criterion_type = criterion_type
    r.criterion_entity_id = criterion_entity_id or uuid.uuid4()
    r.quantity = quantity
    r.status = "active"
    return r


def _make_calculated_item(
    *,
    product_id: uuid.UUID,
    paid_price: str = "100.00",
) -> CalculatedItem:
    return CalculatedItem(
        product_id=product_id,
        product_name="Test",
        quantity=1,
        base_price=Decimal(paid_price),
        paid_price=Decimal(paid_price),
        discount_id=None,
        discounted_amount=Decimal("0.00"),
    )


@pytest.fixture()
def discount_repo() -> MagicMock:
    return MagicMock(spec=DiscountRepository)


@pytest.fixture()
def calc_service(discount_repo: MagicMock) -> DiscountCalculatorService:
    return DiscountCalculatorService(discount_repo=discount_repo)


def test_gift_reward_not_applied_when_product_not_in_cart(
    calc_service: DiscountCalculatorService,
) -> None:
    """Gift reward for a product that is not in the cart produces no applied discounts."""
    product = _make_product(price="200.00")
    reward = _make_gift_reward(criterion_type="product", criterion_entity_id=uuid.uuid4())

    cart_items = [CartItem(product_id=product.id, quantity=1)]
    session = MagicMock()
    session.scalars.return_value = [product]

    _items, applied = calc_service.apply_gift_rewards(cart_items, session, [reward])

    assert applied == []


def test_gift_reward_applied_to_cheapest_category_item(
    calc_service: DiscountCalculatorService,
) -> None:
    """Among multiple items in the same category, the gift reward targets the cheapest one."""
    category_id = uuid.uuid4()
    cheap_product = _make_product(price="50.00", category_id=category_id)
    expensive_product = _make_product(price="200.00", category_id=category_id)

    reward = _make_gift_reward(criterion_type="category", criterion_entity_id=category_id)

    cheap_item = _make_calculated_item(product_id=cheap_product.id, paid_price="50.00")
    expensive_item = _make_calculated_item(product_id=expensive_product.id, paid_price="200.00")

    session = MagicMock()
    session.scalars.return_value = [cheap_product, expensive_product]

    _items, applied = calc_service.apply_gift_rewards(
        [cheap_item, expensive_item],
        session,
        [reward],
    )

    assert len(applied) == 1
    assert applied[0].gift_reward_id == reward.id
    assert applied[0].applied_to_product_id == cheap_product.id
    assert applied[0].discount_rub == Decimal("50.00")


def test_gift_reward_mark_used_after_receipt(
) -> None:
    """When a receipt is created with a product matching an active gift reward, the reward is marked used."""
    from webx5.crud.receipt import ReceiptRepository
    from webx5.entities.receipt import Receipt
    from webx5.entities.store import Store
    from webx5.schemas.receipt import ReceiptCreate, ReceiptItemCreate
    from webx5.services.receipt import ReceiptService

    product = _make_product(price="100.00")
    store = Store()
    store.id = uuid.uuid4()
    store.format_id = uuid.uuid4()
    store.geo_cluster = "d_01"

    receipt = Receipt()
    receipt.id = uuid.uuid4()
    from datetime import datetime, timezone
    receipt.purchase_date = datetime.now(timezone.utc)
    receipt.store_id = store.id
    receipt.loyalty_card_id = uuid.uuid4()
    receipt.channel = "offline"
    receipt.payment_card_uid = None
    receipt.cashback_applied_points = 0
    receipt.cashback_applied_rub = 0
    receipt.points_rate_at_purchase = None

    reward = _make_gift_reward(
        criterion_type="product",
        criterion_entity_id=product.id,
        loyalty_card_id=receipt.loyalty_card_id,
    )

    receipt_repo = MagicMock(spec=ReceiptRepository)
    receipt_repo.create.return_value = (receipt, True)

    discount_repo = MagicMock(spec=DiscountRepository)

    gift_repo_mock = MagicMock(spec=GiftRewardRepository)
    gift_repo_mock.get_active_for_user.return_value = [reward]

    service = ReceiptService(receipt_repo=receipt_repo, discount_repo=discount_repo)

    session = MagicMock()
    session.get.return_value = store
    session.scalars.return_value = [product]

    data = ReceiptCreate(
        loyalty_card_id=receipt.loyalty_card_id,
        store_id=store.id,
        items=[ReceiptItemCreate(product_id=product.id, quantity=1)],
    )

    with patch("webx5.crud.reward.GiftRewardRepository", return_value=gift_repo_mock) as mock_cls:
        service.create_receipt(session, receipt.id, data)

    gift_repo_mock.get_active_for_user.assert_called_once_with(session, receipt.loyalty_card_id)
    gift_repo_mock.mark_used.assert_called_once_with(session, reward)
