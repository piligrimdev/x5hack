import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi_pagination import Page

from webx5.dependencies.auth import CurrentUserUUID, TerminalTokenDep
from webx5.dependencies.db import SessionDep
from webx5.dependencies.pagination import PaginationParams
from webx5.schemas.catalog import (
    CategoryCreate,
    CategoryResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)

catalog_router = APIRouter(prefix="/catalog", tags=["Catalog"])


@catalog_router.get("/categories", response_model=list[CategoryResponse])
def list_categories(session: SessionDep, _user_id: CurrentUserUUID) -> list[CategoryResponse]:
    from webx5.core.catalog import catalog_service

    return catalog_service.list_categories(session)


@catalog_router.get("/products", response_model=Page[ProductResponse])
def list_products(
    session: SessionDep,
    _user_id: CurrentUserUUID,
    params: PaginationParams,
    category_id: uuid.UUID | None = None,
) -> Page[ProductResponse]:
    from webx5.core.catalog import catalog_service

    return catalog_service.list_products(session, category_id, params)


@catalog_router.get("/products/{sku_id}", response_model=ProductResponse)
def get_product_by_sku(sku_id: str, session: SessionDep, _user_id: CurrentUserUUID) -> ProductResponse:
    from webx5.core.catalog import catalog_service

    return catalog_service.get_product_by_sku(session, sku_id)


@catalog_router.post("/categories", response_model=CategoryResponse, status_code=201)
def create_category(data: CategoryCreate, session: SessionDep, _terminal: TerminalTokenDep) -> CategoryResponse:
    from webx5.core.catalog import catalog_service

    return catalog_service.create_category(session, data)


@catalog_router.post("/products", response_model=ProductResponse, status_code=201)
def create_product(data: ProductCreate, session: SessionDep, _terminal: TerminalTokenDep) -> ProductResponse:
    from webx5.core.catalog import catalog_service

    return catalog_service.create_product(session, data)


@catalog_router.put("/products/{sku_id}", response_model=ProductResponse)
def update_product(sku_id: str, data: ProductUpdate, session: SessionDep, _terminal: TerminalTokenDep) -> ProductResponse:
    from webx5.core.catalog import catalog_service

    return catalog_service.update_product(session, sku_id, data)


@catalog_router.delete("/products/{sku_id}", status_code=204)
def delete_product(sku_id: str, session: SessionDep, _terminal: TerminalTokenDep) -> Response:
    from webx5.core.catalog import catalog_service

    catalog_service.delete_product(session, sku_id)
    return Response(status_code=204)
