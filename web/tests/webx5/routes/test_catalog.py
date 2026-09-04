import os
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_TTL_DAYS", "7")
os.environ.setdefault("JWT_REFRESH_TTL_DAYS", "14")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")

from fastapi.testclient import TestClient  # noqa: E402

from webx5.core.server import app  # noqa: E402
from webx5.entities.category import Category  # noqa: E402
from webx5.entities.product import Product  # noqa: E402
from webx5.utils.auth import encode_access_jwt  # noqa: E402

client = TestClient(app)

TERMINAL = "test-terminal-token"


def _token() -> str:
    return encode_access_jwt(uuid.uuid4())


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_category(name: str = "молочные продукты") -> Category:
    c = Category()
    c.id = uuid.uuid4()
    c.name = name
    return c


def _make_product(category: Category | None = None) -> Product:
    cat = category or _make_category()
    p = Product()
    p.id = uuid.uuid4()
    p.sku_id = "sku_0001"
    p.name = "Молоко 2,5%"
    p.current_price = Decimal("135.79")
    p.category_id = cat.id
    p.category = cat
    p.brand_id = None
    return p


class TestListCategories:
    def test_returns_category_list(self) -> None:
        cats = [_make_category("хлеб"), _make_category("молоко")]
        with patch("webx5.services.catalog.CatalogService.list_categories", return_value=cats):
            resp = client.get("/catalog/categories", headers=_bearer(_token()))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "хлеб"

    def test_requires_auth(self) -> None:
        resp = client.get("/catalog/categories")
        assert resp.status_code == 401

    def test_empty_returns_list(self) -> None:
        with patch("webx5.services.catalog.CatalogService.list_categories", return_value=[]):
            resp = client.get("/catalog/categories", headers=_bearer(_token()))
        assert resp.status_code == 200
        assert resp.json() == []


class TestListProducts:
    def test_returns_paginated_response(self) -> None:
        from fastapi_pagination import Page

        product = _make_product()
        fake_page = Page(items=[product], total=1, page=1, size=20, pages=1)
        with patch("webx5.services.catalog.CatalogService.list_products", return_value=fake_page):
            resp = client.get("/catalog/products", headers=_bearer(_token()))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "pages" in body

    def test_requires_auth(self) -> None:
        resp = client.get("/catalog/products")
        assert resp.status_code == 401


class TestGetProductBySku:
    def test_found_returns_product(self) -> None:
        product = _make_product()
        with patch("webx5.services.catalog.CatalogService.get_product_by_sku", return_value=product):
            resp = client.get("/catalog/products/sku_0001", headers=_bearer(_token()))
        assert resp.status_code == 200
        body = resp.json()
        assert body["sku_id"] == "sku_0001"
        assert "category" in body

    def test_not_found_returns_404(self) -> None:
        from fastapi import HTTPException

        with patch(
            "webx5.services.catalog.CatalogService.get_product_by_sku",
            side_effect=HTTPException(status_code=404, detail="Product not found"),
        ):
            resp = client.get("/catalog/products/sku_9999", headers=_bearer(_token()))
        assert resp.status_code == 404

    def test_requires_auth(self) -> None:
        resp = client.get("/catalog/products/sku_0001")
        assert resp.status_code == 401


class TestCreateCategory:
    def test_creates_with_terminal_token(self) -> None:
        cat = _make_category("напитки")
        with patch("webx5.services.catalog.CatalogService.create_category", return_value=cat):
            resp = client.post(
                "/catalog/categories",
                json={"name": "напитки"},
                headers={"X-Terminal-Token": TERMINAL},
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "напитки"

    def test_rejects_without_terminal_token(self) -> None:
        resp = client.post("/catalog/categories", json={"name": "напитки"})
        assert resp.status_code == 401

    def test_rejects_with_user_jwt(self) -> None:
        resp = client.post(
            "/catalog/categories",
            json={"name": "напитки"},
            headers=_bearer(_token()),
        )
        assert resp.status_code == 401


class TestCreateProduct:
    def test_creates_with_terminal_token(self) -> None:
        product = _make_product()
        with patch("webx5.services.catalog.CatalogService.create_product", return_value=product):
            resp = client.post(
                "/catalog/products",
                json={
                    "sku_id": "sku_9999",
                    "name": "Йогурт",
                    "current_price": "89.90",
                    "category_id": str(uuid.uuid4()),
                },
                headers={"X-Terminal-Token": TERMINAL},
            )
        assert resp.status_code == 201

    def test_invalid_price_returns_422(self) -> None:
        resp = client.post(
            "/catalog/products",
            json={
                "sku_id": "sku_0",
                "name": "Test",
                "current_price": "-5.00",
                "category_id": str(uuid.uuid4()),
            },
            headers={"X-Terminal-Token": TERMINAL},
        )
        assert resp.status_code == 422


class TestUpdateProduct:
    def test_updates_with_terminal_token(self) -> None:
        product = _make_product()
        product.current_price = Decimal("99.00")
        with patch("webx5.services.catalog.CatalogService.update_product", return_value=product):
            resp = client.put(
                "/catalog/products/sku_0001",
                json={"current_price": "99.00"},
                headers={"X-Terminal-Token": TERMINAL},
            )
        assert resp.status_code == 200

    def test_rejects_without_token(self) -> None:
        resp = client.put("/catalog/products/sku_0001", json={"current_price": "99.00"})
        assert resp.status_code == 401


class TestDeleteProduct:
    def test_deletes_with_terminal_token(self) -> None:
        with patch("webx5.services.catalog.CatalogService.delete_product", return_value=None):
            resp = client.delete(
                "/catalog/products/sku_0001",
                headers={"X-Terminal-Token": TERMINAL},
            )
        assert resp.status_code == 204

    def test_rejects_without_token(self) -> None:
        resp = client.delete("/catalog/products/sku_0001")
        assert resp.status_code == 401
