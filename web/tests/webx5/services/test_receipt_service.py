from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from webx5.crud.discount import DiscountRepository
from webx5.crud.receipt import ReceiptRepository
from webx5.entities.discount import Discount
from webx5.entities.product import Product
from webx5.entities.receipt import Receipt
from webx5.entities.store import Store
from webx5.schemas.receipt import ReceiptCreate, ReceiptItemCreate
from webx5.services.receipt import ReceiptService


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


def _make_store() -> Store:
    s = Store()
    s.id = uuid.uuid4()
    s.format_id = uuid.uuid4()
    s.geo_cluster = "d_01"
    return s


def _make_discount(*, value: str = "10", valid_to: datetime | None = None) -> Discount:
    d = Discount()
    d.id = uuid.uuid4()
    d.value = Decimal(value)
    d.entity_id = uuid.uuid4()
    d.discount_type_id = uuid.uuid4()
    d.link_type_id = uuid.uuid4()
    d.scope = "all"
    d.valid_from = None
    d.valid_to = valid_to
    return d


def _make_receipt() -> Receipt:
    r = Receipt()
    r.id = uuid.uuid4()
    r.purchase_date = datetime.now(timezone.utc)
    r.store_id = uuid.uuid4()
    r.loyalty_card_id = None
    r.channel = "offline"
    r.payment_card_uid = None
    return r


@pytest.fixture()
def receipt_repo() -> MagicMock:
    return MagicMock(spec=ReceiptRepository)


@pytest.fixture()
def discount_repo() -> MagicMock:
    return MagicMock(spec=DiscountRepository)


@pytest.fixture()
def service(receipt_repo: MagicMock, discount_repo: MagicMock) -> ReceiptService:
    return ReceiptService(receipt_repo=receipt_repo, discount_repo=discount_repo)


@pytest.fixture()
def session() -> MagicMock:
    return MagicMock()


class TestCreateReceiptValidation:
    def test_raises_404_when_store_not_found(
        self,
        service: ReceiptService,
        session: MagicMock,
    ) -> None:
        session.get.return_value = None
        data = ReceiptCreate(
            store_id=uuid.uuid4(),
            items=[ReceiptItemCreate(product_id=uuid.uuid4(), quantity=1)],
        )
        with pytest.raises(HTTPException) as exc_info:
            service.create_receipt(session, uuid.uuid4(), data)
        assert exc_info.value.status_code == 404

    def test_raises_422_when_products_missing(
        self,
        service: ReceiptService,
        session: MagicMock,
    ) -> None:
        store = _make_store()
        session.get.return_value = store
        session.scalars.return_value = []  # no products found

        data = ReceiptCreate(
            store_id=store.id,
            items=[ReceiptItemCreate(product_id=uuid.uuid4(), quantity=1)],
        )
        with pytest.raises(HTTPException) as exc_info:
            service.create_receipt(session, uuid.uuid4(), data)
        assert exc_info.value.status_code == 422


class TestCreateReceiptNoDiscount:
    def test_creates_receipt_with_full_price_when_no_discount(
        self,
        service: ReceiptService,
        receipt_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        product = _make_product(price="150.00")
        store = _make_store()
        receipt = _make_receipt()

        session.get.return_value = store
        session.scalars.return_value = [product]
        receipt_repo.create.return_value = (receipt, True)

        data = ReceiptCreate(
            store_id=store.id,
            items=[ReceiptItemCreate(product_id=product.id, quantity=2)],
        )
        r, is_new = service.create_receipt(session, receipt.id, data)

        assert is_new is True
        call_kwargs = receipt_repo.create.call_args
        items_data = call_kwargs.kwargs["items"]
        assert len(items_data) == 1
        assert items_data[0]["base_price_at_purchase"] == Decimal("150.00")
        assert items_data[0]["paid_price"] == Decimal("150.00")
        assert items_data[0]["discounted_amount"] == Decimal("0.00")
        assert items_data[0]["discount_id"] is None


class TestCreateReceiptWithDiscount:
    def test_applies_discount_and_records_savings(
        self,
        service: ReceiptService,
        receipt_repo: MagicMock,
        discount_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        product = _make_product(price="200.00")
        store = _make_store()
        discount = _make_discount(value="25")
        receipt = _make_receipt()

        session.get.return_value = store
        session.scalars.return_value = [product]
        discount_repo.get_by_id.return_value = discount
        receipt_repo.create.return_value = (receipt, True)

        data = ReceiptCreate(
            store_id=store.id,
            items=[ReceiptItemCreate(product_id=product.id, quantity=1, discount_id=discount.id)],
        )
        service.create_receipt(session, receipt.id, data)

        items_data = receipt_repo.create.call_args.kwargs["items"]
        assert items_data[0]["paid_price"] == Decimal("150.00")
        assert items_data[0]["discounted_amount"] == Decimal("50.00")
        assert items_data[0]["discount_id"] == discount.id

    def test_raises_422_when_discount_not_found(
        self,
        service: ReceiptService,
        receipt_repo: MagicMock,
        discount_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        product = _make_product()
        store = _make_store()
        discount_id = uuid.uuid4()

        session.get.return_value = store
        session.scalars.return_value = [product]
        discount_repo.get_by_id.return_value = None

        data = ReceiptCreate(
            store_id=store.id,
            items=[ReceiptItemCreate(product_id=product.id, quantity=1, discount_id=discount_id)],
        )
        with pytest.raises(HTTPException) as exc_info:
            service.create_receipt(session, uuid.uuid4(), data)
        assert exc_info.value.status_code == 422

    def test_raises_422_when_discount_expired(
        self,
        service: ReceiptService,
        receipt_repo: MagicMock,
        discount_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        from datetime import timedelta

        product = _make_product()
        store = _make_store()
        expired_discount = _make_discount(
            valid_to=datetime.now(timezone.utc) - timedelta(days=1)
        )

        session.get.return_value = store
        session.scalars.return_value = [product]
        discount_repo.get_by_id.return_value = expired_discount

        data = ReceiptCreate(
            store_id=store.id,
            items=[ReceiptItemCreate(product_id=product.id, quantity=1, discount_id=expired_discount.id)],
        )
        with pytest.raises(HTTPException) as exc_info:
            service.create_receipt(session, uuid.uuid4(), data)
        assert exc_info.value.status_code == 422


class TestIdempotency:
    def test_returns_existing_receipt_when_duplicate(
        self,
        service: ReceiptService,
        receipt_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        product = _make_product()
        store = _make_store()
        existing_receipt = _make_receipt()

        session.get.return_value = store
        session.scalars.return_value = [product]
        receipt_repo.create.return_value = (existing_receipt, False)

        data = ReceiptCreate(
            store_id=store.id,
            items=[ReceiptItemCreate(product_id=product.id, quantity=1)],
        )
        r, is_new = service.create_receipt(session, existing_receipt.id, data)

        assert r is existing_receipt
        assert is_new is False


from webx5.entities.receipt import ReceiptItem
from webx5.schemas.receipt import ReceiptResponse


def _make_receipt_item(*, product_id: uuid.UUID, receipt_id: uuid.UUID) -> ReceiptItem:
    ri = ReceiptItem()
    ri.id = uuid.uuid4()
    ri.receipt_id = receipt_id
    ri.product_id = product_id
    ri.quantity = 2
    ri.base_price_at_purchase = Decimal("100.00")
    ri.paid_price = Decimal("90.00")
    ri.discounted_amount = Decimal("10.00")
    ri.discount_id = None
    return ri


class TestBuildReceiptResponse:
    def test_builds_response_with_totals(
        self, service: ReceiptService, receipt_repo: MagicMock, session: MagicMock
    ) -> None:
        product = _make_product()
        receipt = _make_receipt()
        receipt.cashback_applied_points = 0
        receipt.cashback_applied_rub = 0
        receipt.points_rate_at_purchase = None
        item = _make_receipt_item(product_id=product.id, receipt_id=receipt.id)
        receipt_repo.get_items_with_products.return_value = [(item, product)]

        result = service.build_receipt_response(session, receipt)

        assert isinstance(result, ReceiptResponse)
        assert result.id == receipt.id
        assert result.store_id == receipt.store_id
        assert len(result.items) == 1
        assert result.items[0].product_id == product.id
        assert result.total_base == Decimal("200.00")
        assert result.total_paid == Decimal("180.00")
        assert result.discount_saved_rub == Decimal("20.00")
        assert result.total_saved == Decimal("20.00")

    def test_subtracts_cashback_from_total_paid(
        self, service: ReceiptService, receipt_repo: MagicMock, session: MagicMock
    ) -> None:
        product = _make_product()
        receipt = _make_receipt()
        receipt.cashback_applied_points = 500
        receipt.cashback_applied_rub = 50
        receipt.points_rate_at_purchase = 10
        item = _make_receipt_item(product_id=product.id, receipt_id=receipt.id)
        item.discounted_amount = Decimal("0.00")
        item.paid_price = Decimal("100.00")
        receipt_repo.get_items_with_products.return_value = [(item, product)]

        result = service.build_receipt_response(session, receipt)

        assert result.total_paid == Decimal("150.00")  # 200 base paid - 50 cashback
        assert result.total_saved == Decimal("50.00")  # 0 discount + 50 cashback
        assert result.cashback_applied_rub == 50
        assert result.points_rate_at_purchase == 10
