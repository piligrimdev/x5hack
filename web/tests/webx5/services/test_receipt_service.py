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
