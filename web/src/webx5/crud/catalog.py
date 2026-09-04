import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from webx5.entities.category import Category
from webx5.entities.product import Product
from webx5.schemas.catalog import ProductCreate, ProductUpdate


class CatalogRepository:
    def get_all_categories(self, session: Session) -> list[Category]:
        return list(session.scalars(select(Category).order_by(Category.name)))

    def get_products_query(self, session: Session, category_id: uuid.UUID | None):
        stmt = select(Product)
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        return stmt

    def get_product_by_sku(self, session: Session, sku_id: str) -> Product | None:
        return session.scalars(select(Product).where(Product.sku_id == sku_id)).first()

    def get_category_by_name(self, session: Session, name: str) -> Category | None:
        return session.scalars(select(Category).where(Category.name == name)).first()

    def get_or_create_category_by_name(self, session: Session, name: str) -> Category:
        category = session.scalars(select(Category).where(Category.name == name)).first()
        if category is None:
            category = Category(id=uuid.uuid4(), name=name)
            session.add(category)
            session.flush()
        return category

    def upsert_product(
        self,
        session: Session,
        sku_id: str,
        name: str,
        current_price: Decimal,
        category_id: uuid.UUID,
    ) -> None:
        stmt = pg_insert(Product).values(
            id=uuid.uuid4(),
            sku_id=sku_id,
            name=name,
            current_price=current_price,
            category_id=category_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["sku_id"],
            set_={"name": stmt.excluded.name, "current_price": stmt.excluded.current_price, "category_id": stmt.excluded.category_id},
        )
        session.execute(stmt)

    # --- write methods ---

    def create_category(self, session: Session, name: str) -> Category:
        from sqlalchemy.exc import IntegrityError

        category = Category(id=uuid.uuid4(), name=name)
        session.add(category)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=409, detail="Category with this name already exists")
        return category

    def create_product(self, session: Session, data: ProductCreate) -> Product:
        from sqlalchemy.exc import IntegrityError

        category = session.get(Category, data.category_id)
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found")

        product = Product(
            id=uuid.uuid4(),
            sku_id=data.sku_id,
            name=data.name,
            current_price=data.current_price,
            category_id=data.category_id,
            brand_id=data.brand_id,
        )
        session.add(product)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=409, detail="Product with this SKU already exists")
        session.refresh(product)
        return product

    def update_product(self, session: Session, sku_id: str, data: ProductUpdate) -> Product:
        product = self.get_product_by_sku(session, sku_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")

        if data.name is not None:
            product.name = data.name
        if data.current_price is not None:
            product.current_price = data.current_price
        if data.category_id is not None:
            category = session.get(Category, data.category_id)
            if category is None:
                raise HTTPException(status_code=404, detail="Category not found")
            product.category_id = data.category_id
        if data.brand_id is not None:
            product.brand_id = data.brand_id

        session.flush()
        session.refresh(product)
        return product

    def delete_product(self, session: Session, sku_id: str) -> None:
        product = self.get_product_by_sku(session, sku_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        session.delete(product)
        session.flush()
