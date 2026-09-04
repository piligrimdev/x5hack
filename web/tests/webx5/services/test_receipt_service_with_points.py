"""Feature 007: POST /receipts accepts points_to_spend and atomically spends cashback.

Verifies:
- anonymous receipt (no loyalty_card_id) with points_to_spend > 0 → HTTPException 422 (FR-011);
- happy-path with loyalty_card_id + points_to_spend → points_service.spend_for_receipt is called
  with correct args; receipt.cashback_applied_* fields are populated;
- points_to_spend=None or 0 → spend_for_receipt not called; receipt saved as before.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from webx5.entities.product import Product
from webx5.entities.receipt import Receipt
from webx5.entities.store import Store
from webx5.schemas.receipt import ReceiptCreate, ReceiptItemCreate
from webx5.services.receipt import ReceiptService


def _make_product(price: str = "100.00") -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.name = "Test"
    p.sku_id = f"sku_{uuid.uuid4().hex[:6]}"
    p.current_price = Decimal(price)
    p.category_id = uuid.uuid4()
    return p


def _make_store() -> Store:
    s = Store()
    s.id = uuid.uuid4()
    s.geo_cluster = "test"
    return s


def _make_receipt(loyalty_card_id: uuid.UUID | None = None) -> Receipt:
    r = Receipt()
    r.id = uuid.uuid4()
    r.loyalty_card_id = loyalty_card_id
    r.channel = "offline"
    r.cashback_applied_points = 0
    r.cashback_applied_rub = 0
    r.points_rate_at_purchase = None
    return r


@pytest.fixture
def service():
    receipt_repo = MagicMock()
    discount_repo = MagicMock()
    return ReceiptService(receipt_repo=receipt_repo, discount_repo=discount_repo), receipt_repo


def test_anonymous_with_points_to_spend_returns_422(service):
    svc, receipt_repo = service
    product = _make_product()
    store = _make_store()
    session = MagicMock()
    session.get.return_value = store
    session.scalars.return_value = [product]

    data = ReceiptCreate(
        store_id=store.id,
        loyalty_card_id=None,
        items=[ReceiptItemCreate(product_id=product.id, quantity=1)],
        points_to_spend=100,
    )

    with pytest.raises(HTTPException) as exc:
        svc.create_receipt(session, uuid.uuid4(), data)
    assert exc.value.status_code == 422
    receipt_repo.create.assert_not_called()


def test_points_to_spend_zero_skips_spend(service):
    svc, receipt_repo = service
    product = _make_product("100.00")
    store = _make_store()
    loyalty_id = uuid.uuid4()
    receipt = _make_receipt(loyalty_id)
    session = MagicMock()
    session.get.return_value = store
    session.scalars.return_value = [product]
    receipt_repo.create.return_value = (receipt, True)

    data = ReceiptCreate(
        store_id=store.id,
        loyalty_card_id=loyalty_id,
        items=[ReceiptItemCreate(product_id=product.id, quantity=1)],
        points_to_spend=0,
    )

    fake_points = MagicMock()
    with patch("webx5.core.points.points_service", fake_points):
        svc.create_receipt(session, receipt.id, data)

    fake_points.spend_for_receipt.assert_not_called()
    assert receipt.cashback_applied_points == 0


def test_happy_path_spends_points_and_sets_receipt_fields(service):
    svc, receipt_repo = service
    product = _make_product("100.00")
    store = _make_store()
    loyalty_id = uuid.uuid4()
    receipt = _make_receipt(loyalty_id)
    session = MagicMock()
    session.get.return_value = store
    session.scalars.return_value = [product]
    receipt_repo.create.return_value = (receipt, True)

    data = ReceiptCreate(
        store_id=store.id,
        loyalty_card_id=loyalty_id,
        items=[ReceiptItemCreate(product_id=product.id, quantity=2)],
        points_to_spend=500,
    )

    fake_points = MagicMock()
    fake_points.spend_for_receipt.return_value = (500, 50, 10)
    with patch("webx5.core.points.points_service", fake_points):
        svc.create_receipt(session, receipt.id, data)

    # subtotal = 100 * 2 = 200 rub, integer
    call = fake_points.spend_for_receipt.call_args
    assert call.kwargs["loyalty_card_id"] == loyalty_id
    assert call.kwargs["points_requested_raw"] == 500
    assert call.kwargs["receipt_subtotal_rub"] == 200
    assert call.kwargs["receipt_id"] == receipt.id

    assert receipt.cashback_applied_points == 500
    assert receipt.cashback_applied_rub == 50
    assert receipt.points_rate_at_purchase == 10


def test_idempotent_replay_skips_spend(service):
    svc, receipt_repo = service
    product = _make_product()
    store = _make_store()
    loyalty_id = uuid.uuid4()
    existing = _make_receipt(loyalty_id)
    session = MagicMock()
    session.get.return_value = store
    session.scalars.return_value = [product]
    receipt_repo.create.return_value = (existing, False)  # already exists

    data = ReceiptCreate(
        store_id=store.id,
        loyalty_card_id=loyalty_id,
        items=[ReceiptItemCreate(product_id=product.id, quantity=1)],
        points_to_spend=500,
    )

    fake_points = MagicMock()
    with patch("webx5.core.points.points_service", fake_points):
        r, is_new = svc.create_receipt(session, existing.id, data)

    assert is_new is False
    fake_points.spend_for_receipt.assert_not_called()


def test_points_to_spend_all_string_passes_through(service):
    svc, receipt_repo = service
    product = _make_product("50.00")
    store = _make_store()
    loyalty_id = uuid.uuid4()
    receipt = _make_receipt(loyalty_id)
    session = MagicMock()
    session.get.return_value = store
    session.scalars.return_value = [product]
    receipt_repo.create.return_value = (receipt, True)

    data = ReceiptCreate(
        store_id=store.id,
        loyalty_card_id=loyalty_id,
        items=[ReceiptItemCreate(product_id=product.id, quantity=1)],
        points_to_spend="all",
    )

    fake_points = MagicMock()
    fake_points.spend_for_receipt.return_value = (0, 0, 10)
    with patch("webx5.core.points.points_service", fake_points):
        svc.create_receipt(session, receipt.id, data)

    fake_points.spend_for_receipt.assert_called_once()
    assert fake_points.spend_for_receipt.call_args.kwargs["points_requested_raw"] == "all"
