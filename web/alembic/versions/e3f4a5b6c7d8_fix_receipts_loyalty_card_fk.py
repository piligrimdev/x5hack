"""fix receipts loyalty_card_id FK to reference users instead of loyalty_cards

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-04 14:00:00.000000

"""
from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("receipts_loyalty_card_id_fkey", "receipts", type_="foreignkey")
    op.create_foreign_key(
        "receipts_loyalty_card_id_fkey",
        "receipts",
        "users",
        ["loyalty_card_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("receipts_loyalty_card_id_fkey", "receipts", type_="foreignkey")
    op.create_foreign_key(
        "receipts_loyalty_card_id_fkey",
        "receipts",
        "loyalty_cards",
        ["loyalty_card_id"],
        ["id"],
        ondelete="SET NULL",
    )
