"""add_purchases_tables

Revision ID: b3c4d5e6f7a8
Revises: 6a9a8b4e1234
Create Date: 2026-09-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "6a9a8b4e1234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. store_formats
    op.create_table(
        "store_formats",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_store_formats_name"),
    )

    # 2. stores
    op.create_table(
        "stores",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("format_id", sa.UUID(), nullable=False),
        sa.Column("geo_cluster", sa.String(200), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["format_id"], ["store_formats.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stores_format_id", "stores", ["format_id"])

    # 3. discount_types
    op.create_table(
        "discount_types",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_discount_types_name"),
    )

    # 4. discount_link_types
    op.create_table(
        "discount_link_types",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_discount_link_types_name"),
    )

    # 5. discounts
    op.create_table(
        "discounts",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("value", sa.Numeric(5, 2), nullable=False),
        sa.Column("discount_type_id", sa.UUID(), nullable=False),
        sa.Column("link_type_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False, server_default="all"),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["discount_type_id"], ["discount_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["link_type_id"], ["discount_link_types.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("scope IN ('all', 'by_format', 'by_store')", name="ck_discounts_scope"),
        sa.CheckConstraint("value >= 0 AND value <= 100", name="ck_discounts_value"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discounts_entity_id", "discounts", ["entity_id"])
    op.create_index("ix_discounts_scope", "discounts", ["scope"])

    # 6. format_discounts (M2M)
    op.create_table(
        "format_discounts",
        sa.Column("discount_id", sa.UUID(), nullable=False),
        sa.Column("format_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["discount_id"], ["discounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["format_id"], ["store_formats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("discount_id", "format_id"),
    )

    # 7. store_discounts (M2M)
    op.create_table(
        "store_discounts",
        sa.Column("discount_id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["discount_id"], ["discounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("discount_id", "store_id"),
    )

    # 8. segments
    op.create_table(
        "segments",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_segments_name"),
    )

    # 9. loyalty_cards
    op.create_table(
        "loyalty_cards",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("loyalty_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("gender", sa.String(10), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("segment_id", sa.UUID(), nullable=True),
        sa.Column("geo_cluster", sa.String(200), nullable=True),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 10. receipts
    op.create_table(
        "receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("purchase_date", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("payment_card_uid", sa.String(200), nullable=True),
        sa.Column("loyalty_card_id", sa.UUID(), nullable=True),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False, server_default="offline"),
        sa.ForeignKeyConstraint(["loyalty_card_id"], ["loyalty_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("channel IN ('online', 'offline')", name="ck_receipts_channel"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_receipts_loyalty_card_id", "receipts", ["loyalty_card_id"])
    op.create_index("ix_receipts_store_id", "receipts", ["store_id"])
    op.create_index("ix_receipts_purchase_date", "receipts", ["purchase_date"])

    # 11. receipt_items
    op.create_table(
        "receipt_items",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("receipt_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("base_price_at_purchase", sa.Numeric(10, 2), nullable=False),
        sa.Column("paid_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("discounted_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("discount_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["discount_id"], ["discounts.id"], ondelete="SET NULL"),
        sa.CheckConstraint("quantity > 0", name="ck_receipt_items_quantity"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_receipt_items_receipt_id", "receipt_items", ["receipt_id"])
    op.create_index("ix_receipt_items_product_id", "receipt_items", ["product_id"])

    # Seeds: discount_types
    op.execute(
        "INSERT INTO discount_types (id, name) VALUES "
        "(gen_random_uuid(), 'акция'), "
        "(gen_random_uuid(), 'лояльность'), "
        "(gen_random_uuid(), 'персональная'), "
        "(gen_random_uuid(), 'уценка') "
        "ON CONFLICT (name) DO NOTHING"
    )

    # Seeds: discount_link_types
    op.execute(
        "INSERT INTO discount_link_types (id, name) VALUES "
        "(gen_random_uuid(), 'product'), "
        "(gen_random_uuid(), 'category'), "
        "(gen_random_uuid(), 'brand') "
        "ON CONFLICT (name) DO NOTHING"
    )

    # Seeds: segments
    op.execute(
        "INSERT INTO segments (id, name) VALUES "
        "(gen_random_uuid(), 'подросток'), "
        "(gen_random_uuid(), 'семьянин'), "
        "(gen_random_uuid(), 'пожилой'), "
        "(gen_random_uuid(), 'Зрелые'), "
        "(gen_random_uuid(), 'Молодые'), "
        "(gen_random_uuid(), 'Пенсионеры') "
        "ON CONFLICT (name) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_index("ix_receipt_items_product_id", table_name="receipt_items")
    op.drop_index("ix_receipt_items_receipt_id", table_name="receipt_items")
    op.drop_table("receipt_items")
    op.drop_index("ix_receipts_purchase_date", table_name="receipts")
    op.drop_index("ix_receipts_store_id", table_name="receipts")
    op.drop_index("ix_receipts_loyalty_card_id", table_name="receipts")
    op.drop_table("receipts")
    op.drop_table("loyalty_cards")
    op.drop_table("segments")
    op.drop_table("store_discounts")
    op.drop_table("format_discounts")
    op.drop_index("ix_discounts_scope", table_name="discounts")
    op.drop_index("ix_discounts_entity_id", table_name="discounts")
    op.drop_table("discounts")
    op.drop_table("discount_link_types")
    op.drop_table("discount_types")
    op.drop_index("ix_stores_format_id", table_name="stores")
    op.drop_table("stores")
    op.drop_table("store_formats")
