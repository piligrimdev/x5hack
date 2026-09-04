"""add loyalty_card_id to discounts

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-09-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discounts",
        sa.Column("loyalty_card_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "discounts_loyalty_card_id_fkey",
        "discounts",
        "users",
        ["loyalty_card_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_discounts_loyalty_card_id", "discounts", ["loyalty_card_id"])


def downgrade() -> None:
    op.drop_index("ix_discounts_loyalty_card_id", "discounts")
    op.drop_constraint("discounts_loyalty_card_id_fkey", "discounts", type_="foreignkey")
    op.drop_column("discounts", "loyalty_card_id")
