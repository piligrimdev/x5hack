import uuid

from fastapi import HTTPException
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy.orm import Session

from webx5.crud.catalog import CatalogRepository
from webx5.entities.category import Category
from webx5.entities.product import Product
from webx5.schemas.catalog import CategoryCreate, ProductCreate, ProductResponse, ProductUpdate


class CatalogService:
    def __init__(self, repo: CatalogRepository) -> None:
        self.repo = repo

    def list_categories(self, session: Session) -> list[Category]:
        return self.repo.get_all_categories(session)

    def list_products(
        self, session: Session, category_id: uuid.UUID | None, params: Params
    ) -> Page[ProductResponse]:
        query = self.repo.get_products_query(session, category_id)
        return paginate(session, query, params)

    def get_product_by_sku(self, session: Session, sku_id: str) -> Product:
        product = self.repo.get_product_by_sku(session, sku_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return product

    def create_category(self, session: Session, data: CategoryCreate) -> Category:
        return self.repo.create_category(session, data.name)

    def create_product(self, session: Session, data: ProductCreate) -> Product:
        return self.repo.create_product(session, data)

    def update_product(self, session: Session, sku_id: str, data: ProductUpdate) -> Product:
        return self.repo.update_product(session, sku_id, data)

    def delete_product(self, session: Session, sku_id: str) -> None:
        self.repo.delete_product(session, sku_id)
