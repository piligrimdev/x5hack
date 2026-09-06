from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")

from fastapi.testclient import TestClient

from webx5.core.server import app
from webx5.services.discount_calculator import CalculatedItem

client = TestClient(app)


def test_calculate_includes_referral_percent_in_total_saved():
    store_id = uuid.uuid4()
    product_id = uuid.uuid4()
    invitee = uuid.uuid4()
    store = MagicMock()
    store.id = store_id
    product = MagicMock()
    product.id = product_id
    product.name = "Молоко"
    item = CalculatedItem(
        product_id=product_id,
        product_name="Молоко",
        quantity=1,
        base_price=Decimal("100.00"),
        paid_price=Decimal("90.00"),
        discount_id=uuid.uuid4(),
        discounted_amount=Decimal("10.00"),
    )
    session = MagicMock()
    session.get.return_value = store
    session.scalars.return_value = [product_id]

    def _db():
        yield session

    from webx5.dependencies.db import get_db

    app.dependency_overrides[get_db] = _db
    try:
        with (
            patch(
                "webx5.core.purchases.discount_calculator_service.calculate",
                return_value=[item],
            ),
            patch(
                "webx5.core.points.points_service.preview_for_calculate",
                return_value=None,
            ),
        ):
            resp = client.post(
                "/receipts/calculate",
                headers={"X-Terminal-Token": "test-terminal-token"},
                json={
                    "loyalty_card_id": str(invitee),
                    "store_id": str(store_id),
                    "items": [{"product_id": str(product_id), "quantity": 1}],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(str(body["total_saved"])) == Decimal("10.00")
