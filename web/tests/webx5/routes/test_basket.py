import os
import uuid
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_TTL_DAYS", "7")
os.environ.setdefault("JWT_REFRESH_TTL_DAYS", "14")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")

from fastapi.testclient import TestClient  # noqa: E402

from webx5.core.server import app  # noqa: E402
from webx5.schemas.basket import AssistantResponse, BasketItem  # noqa: E402
from webx5.utils.auth import encode_access_jwt  # noqa: E402

client = TestClient(app)


def _token() -> str:
    return encode_access_jwt(uuid.uuid4())


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestGetSuggestedBasket:
    def test_returns_items(self) -> None:
        item = BasketItem(product_id=uuid.uuid4(), name="Молоко", quantity=2, price=Decimal("89.90"))
        with patch("webx5.services.basket_assistant.BasketService.suggest", return_value=[item]):
            resp = client.get("/basket/suggested", headers=_bearer(_token()))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == "Молоко"

    def test_requires_auth(self) -> None:
        resp = client.get("/basket/suggested")
        assert resp.status_code == 401


class TestPostBasketAssistant:
    def test_returns_updated_items(self) -> None:
        item = BasketItem(product_id=uuid.uuid4(), name="Кефир", quantity=2, price=Decimal("75.00"))
        fake_response = AssistantResponse(items=[item], applied=True, message=None)
        with patch(
            "webx5.services.basket_assistant.BasketService.apply_instruction",
            return_value=fake_response,
        ):
            resp = client.post(
                "/basket/assistant",
                json={"items": [], "instruction": "добавь кефир"},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied"] is True
        assert body["items"][0]["name"] == "Кефир"

    def test_requires_auth(self) -> None:
        resp = client.post("/basket/assistant", json={"items": [], "instruction": "x"})
        assert resp.status_code == 401

    def test_rejects_empty_instruction(self) -> None:
        resp = client.post(
            "/basket/assistant",
            json={"items": [], "instruction": ""},
            headers=_bearer(_token()),
        )
        assert resp.status_code == 422


class TestPostBasketCheckout:
    def test_returns_created_receipt(self) -> None:
        from webx5.schemas.receipt import ReceiptItemResponse, ReceiptResponse

        fake_response = ReceiptResponse(
            id=uuid.uuid4(),
            purchase_date="2026-09-05T12:00:00Z",
            store_id=uuid.uuid4(),
            loyalty_card_id=uuid.uuid4(),
            channel="offline",
            items=[
                ReceiptItemResponse(
                    id=uuid.uuid4(),
                    product_id=uuid.uuid4(),
                    quantity=2,
                    base_price_at_purchase=Decimal("100.00"),
                    paid_price=Decimal("90.00"),
                    discounted_amount=Decimal("10.00"),
                    discount_id=None,
                )
            ],
            total_base=Decimal("200.00"),
            total_paid=Decimal("180.00"),
            total_saved=Decimal("20.00"),
            discount_saved_rub=Decimal("20.00"),
        )
        with patch(
            "webx5.services.basket_assistant.BasketService.checkout",
            return_value=fake_response,
        ):
            resp = client.post(
                "/basket/checkout",
                json={"items": [{"product_id": str(uuid.uuid4()), "quantity": 2}]},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["total_saved"] == 20.0
        assert len(body["items"]) == 1

    def test_requires_auth(self) -> None:
        resp = client.post("/basket/checkout", json={"items": []})
        assert resp.status_code == 401

    def test_propagates_service_422(self) -> None:
        from fastapi import HTTPException

        with patch(
            "webx5.services.basket_assistant.BasketService.checkout",
            side_effect=HTTPException(status_code=422, detail="Корзина пуста"),
        ):
            resp = client.post(
                "/basket/checkout",
                json={"items": []},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 422

    def test_forwards_points_to_spend(self) -> None:
        from webx5.schemas.receipt import ReceiptResponse

        captured: dict = {}

        def _fake_checkout(self, session, user_id, items, points_to_spend=None):
            captured["points_to_spend"] = points_to_spend
            return ReceiptResponse(
                id=uuid.uuid4(),
                purchase_date="2026-09-05T12:00:00Z",
                store_id=uuid.uuid4(),
                loyalty_card_id=user_id,
                channel="offline",
                items=[],
                total_base=Decimal("0"),
                total_paid=Decimal("0"),
                total_saved=Decimal("0"),
            )

        with patch("webx5.services.basket_assistant.BasketService.checkout", _fake_checkout):
            resp = client.post(
                "/basket/checkout",
                json={"items": [{"product_id": str(uuid.uuid4()), "quantity": 1}], "points_to_spend": "all"},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 201
        assert captured["points_to_spend"] == "all"


class TestPostBasketPreview:
    def test_returns_priced_preview(self) -> None:
        from webx5.schemas.receipt import CalculatedItemOut, CalculateResponse

        fake_response = CalculateResponse(
            store_id=uuid.uuid4(),
            loyalty_card_id=uuid.uuid4(),
            items=[
                CalculatedItemOut(
                    product_id=uuid.uuid4(),
                    product_name="Молоко",
                    quantity=2,
                    base_price=Decimal("100.00"),
                    paid_price=Decimal("90.00"),
                    discount_id=None,
                    discounted_amount=Decimal("10.00"),
                )
            ],
            total_base=Decimal("200.00"),
            total_paid=Decimal("180.00"),
            total_saved=Decimal("20.00"),
            cashback=None,
        )
        with patch(
            "webx5.services.basket_assistant.BasketService.preview",
            return_value=fake_response,
        ):
            resp = client.post(
                "/basket/preview",
                json={"items": [{"product_id": str(uuid.uuid4()), "quantity": 2}]},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_saved"] == 20.0
        assert body["items"][0]["paid_price"] == 90.0

    def test_requires_auth(self) -> None:
        resp = client.post("/basket/preview", json={"items": []})
        assert resp.status_code == 401

    def test_empty_items_is_valid_request(self) -> None:
        from webx5.schemas.receipt import CalculateResponse

        fake_response = CalculateResponse(
            store_id=uuid.uuid4(),
            loyalty_card_id=uuid.uuid4(),
            items=[],
            total_base=Decimal("0"),
            total_paid=Decimal("0"),
            total_saved=Decimal("0"),
            cashback=None,
        )
        with patch(
            "webx5.services.basket_assistant.BasketService.preview",
            return_value=fake_response,
        ):
            resp = client.post("/basket/preview", json={"items": []}, headers=_bearer(_token()))
        assert resp.status_code == 200
