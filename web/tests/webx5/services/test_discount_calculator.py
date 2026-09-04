from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from webx5.crud.discount import DiscountRepository
from webx5.entities.discount import Discount, DiscountType
from webx5.entities.product import Product
from webx5.entities.store import Store
from webx5.services.discount_calculator import CalculatedItem, CartItem, DiscountCalculatorService


def _make_product(
    *,
    price: str = "100.00",
    category_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
) -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.name = "Test Product"
    p.sku_id = f"sku_{uuid.uuid4().hex[:6]}"
    p.current_price = Decimal(price)
    p.category_id = category_id or uuid.uuid4()
    p.brand_id = brand_id
    return p


def _make_discount(*, value: str = "10", entity_id: uuid.UUID | None = None) -> Discount:
    d = Discount()
    d.id = uuid.uuid4()
    d.value = Decimal(value)
    d.entity_id = entity_id or uuid.uuid4()
    d.discount_type_id = uuid.uuid4()
    d.link_type_id = uuid.uuid4()
    d.scope = "all"
    d.valid_from = None
    d.valid_to = None
    return d


def _make_store() -> Store:
    s = Store()
    s.id = uuid.uuid4()
    s.format_id = uuid.uuid4()
    s.geo_cluster = "d_01"
    return s


@pytest.fixture()
def discount_repo() -> MagicMock:
    return MagicMock(spec=DiscountRepository)


@pytest.fixture()
def service(discount_repo: MagicMock) -> DiscountCalculatorService:
    return DiscountCalculatorService(discount_repo=discount_repo)


@pytest.fixture()
def session() -> MagicMock:
    return MagicMock()


class TestCalculateNoDiscount:
    def test_returns_full_price_when_no_discounts(
        self,
        service: DiscountCalculatorService,
        discount_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        product = _make_product(price="200.00")
        store = _make_store()
        session.scalars.return_value = [product]
        discount_repo.find_applicable_for_cart.return_value = []
        session.scalar.return_value = None

        items = [CartItem(product_id=product.id, quantity=2)]
        result = service.calculate(items, store, None, session)

        assert len(result) == 1
        r = result[0]
        assert r.base_price == Decimal("200.00")
        assert r.paid_price == Decimal("200.00")
        assert r.discount_id is None
        assert r.discounted_amount == Decimal("0.00")


class TestCalculateBestPriceWins:
    def test_picks_highest_value_discount(
        self,
        service: DiscountCalculatorService,
        discount_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        product = _make_product(price="100.00")
        store = _make_store()

        d10 = _make_discount(value="10", entity_id=product.category_id)
        d25 = _make_discount(value="25", entity_id=product.category_id)
        d5 = _make_discount(value="5", entity_id=product.id)

        session.scalars.return_value = [product]
        discount_repo.find_applicable_for_cart.return_value = [d10, d25, d5]
        session.scalar.return_value = None

        items = [CartItem(product_id=product.id, quantity=1)]
        result = service.calculate(items, store, None, session)

        assert result[0].discount_id == d25.id
        assert result[0].paid_price == Decimal("75.00")
        assert result[0].discounted_amount == Decimal("25.00")

    def test_multiple_products_each_gets_best_discount(
        self,
        service: DiscountCalculatorService,
        discount_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        cat1 = uuid.uuid4()
        cat2 = uuid.uuid4()
        p1 = _make_product(price="100.00", category_id=cat1)
        p2 = _make_product(price="200.00", category_id=cat2)

        d_cat1 = _make_discount(value="20", entity_id=cat1)
        d_cat2 = _make_discount(value="10", entity_id=cat2)

        session.scalars.return_value = [p1, p2]
        discount_repo.find_applicable_for_cart.return_value = [d_cat1, d_cat2]
        session.scalar.return_value = None

        items = [
            CartItem(product_id=p1.id, quantity=1),
            CartItem(product_id=p2.id, quantity=3),
        ]
        result = service.calculate(items, store=_make_store(), loyalty_card_id=None, session=session)

        assert len(result) == 2
        r1 = next(r for r in result if r.product_id == p1.id)
        r2 = next(r for r in result if r.product_id == p2.id)
        assert r1.paid_price == Decimal("80.00")
        assert r2.paid_price == Decimal("180.00")


class TestCalculatePersonalDiscounts:
    def test_excludes_personal_discounts_without_loyalty_card(
        self,
        service: DiscountCalculatorService,
        discount_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        product = _make_product(price="100.00")
        store = _make_store()

        personal_type_id = uuid.uuid4()
        personal_type = MagicMock(spec=DiscountType)
        personal_type.id = personal_type_id

        d_personal = _make_discount(value="50", entity_id=product.category_id)
        d_personal.discount_type_id = personal_type_id

        session.scalars.return_value = [product]
        discount_repo.find_applicable_for_cart.return_value = [d_personal]
        session.scalar.return_value = personal_type

        items = [CartItem(product_id=product.id, quantity=1)]
        result = service.calculate(items, store, loyalty_card_id=None, session=session)

        assert result[0].discount_id is None
        assert result[0].paid_price == Decimal("100.00")

    def test_applies_personal_discounts_with_loyalty_card(
        self,
        service: DiscountCalculatorService,
        discount_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        product = _make_product(price="100.00")
        store = _make_store()
        loyalty_card_id = uuid.uuid4()

        d_personal = _make_discount(value="50", entity_id=product.category_id)

        session.scalars.return_value = [product]
        discount_repo.find_applicable_for_cart.return_value = [d_personal]

        items = [CartItem(product_id=product.id, quantity=1)]
        result = service.calculate(items, store, loyalty_card_id=loyalty_card_id, session=session)

        assert result[0].discount_id == d_personal.id
        assert result[0].paid_price == Decimal("50.00")


class TestCalculatePriceRounding:
    def test_rounds_paid_price_to_two_decimal_places(
        self,
        service: DiscountCalculatorService,
        discount_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        product = _make_product(price="135.79")
        store = _make_store()

        d = _make_discount(value="15", entity_id=product.id)
        session.scalars.return_value = [product]
        discount_repo.find_applicable_for_cart.return_value = [d]
        session.scalar.return_value = None

        items = [CartItem(product_id=product.id, quantity=1)]
        result = service.calculate(items, store, None, session)

        # 135.79 * 0.85 = 115.4215 → rounds to 115.42
        assert result[0].paid_price == Decimal("115.42")
