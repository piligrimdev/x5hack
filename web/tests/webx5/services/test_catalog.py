import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi_pagination import Params

from webx5.crud.catalog import CatalogRepository
from webx5.entities.category import Category
from webx5.entities.product import Product
from webx5.services.catalog import CatalogService


def _make_category(name: str = "молочные продукты") -> Category:
    c = Category()
    c.id = uuid.uuid4()
    c.name = name
    return c


def _make_product(sku_id: str = "sku_0001", category: Category | None = None) -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku_id = sku_id
    p.name = "Молоко 2,5%"
    p.current_price = Decimal("135.79")
    cat = category or _make_category()
    p.category_id = cat.id
    p.category = cat
    p.brand_id = None
    return p


@pytest.fixture()
def repo() -> MagicMock:
    return MagicMock(spec=CatalogRepository)


@pytest.fixture()
def service(repo: MagicMock) -> CatalogService:
    return CatalogService(repo=repo)


@pytest.fixture()
def session() -> MagicMock:
    return MagicMock()


class TestListCategories:
    def test_returns_list_from_repo(self, service: CatalogService, repo: MagicMock, session: MagicMock) -> None:
        categories = [_make_category("молочные"), _make_category("хлеб")]
        repo.get_all_categories.return_value = categories

        result = service.list_categories(session)

        repo.get_all_categories.assert_called_once_with(session)
        assert result == categories

    def test_empty_list(self, service: CatalogService, repo: MagicMock, session: MagicMock) -> None:
        repo.get_all_categories.return_value = []
        assert service.list_categories(session) == []


class TestListProducts:
    def test_delegates_to_paginate(self, service: CatalogService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi_pagination import Page
        import webx5.services.catalog as catalog_module

        fake_query = MagicMock()
        repo.get_products_query.return_value = fake_query
        fake_page: MagicMock = MagicMock(spec=Page)
        mock_paginate = MagicMock(return_value=fake_page)
        monkeypatch.setattr(catalog_module, "paginate", mock_paginate)

        params = Params(page=1, size=10)
        result = service.list_products(session, None, params)

        repo.get_products_query.assert_called_once_with(session, None)
        mock_paginate.assert_called_once_with(session, fake_query, params)
        assert result is fake_page

    def test_filters_by_category_id(self, service: CatalogService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        import webx5.services.catalog as catalog_module

        cat_id = uuid.uuid4()
        repo.get_products_query.return_value = MagicMock()
        monkeypatch.setattr(catalog_module, "paginate", MagicMock())

        service.list_products(session, cat_id, Params())

        repo.get_products_query.assert_called_once_with(session, cat_id)


class TestGetProductBySku:
    def test_returns_product_when_found(self, service: CatalogService, repo: MagicMock, session: MagicMock) -> None:
        product = _make_product("sku_0042")
        repo.get_product_by_sku.return_value = product

        result = service.get_product_by_sku(session, "sku_0042")

        assert result is product
        repo.get_product_by_sku.assert_called_once_with(session, "sku_0042")

    def test_raises_404_when_not_found(self, service: CatalogService, repo: MagicMock, session: MagicMock) -> None:
        repo.get_product_by_sku.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.get_product_by_sku(session, "sku_9999")

        assert exc_info.value.status_code == 404
