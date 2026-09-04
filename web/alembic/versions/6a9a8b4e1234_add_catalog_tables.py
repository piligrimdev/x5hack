"""add_catalog_tables

Revision ID: 6a9a8b4e1234
Revises: a1b2c3d4e5f6
Create Date: 2026-09-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6a9a8b4e1234"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )
    op.create_index("ix_categories_name", "categories", ["name"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("current_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku_id", name="uq_products_sku_id"),
    )
    op.create_index("ix_products_sku_id", "products", ["sku_id"], unique=True)
    op.create_index("ix_products_category_id", "products", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_index("ix_products_sku_id", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_categories_name", table_name="categories")
    op.drop_table("categories")
