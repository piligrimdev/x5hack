"""loyalty_level on users, min_loyalty_level on discounts, all link type

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-04 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("loyalty_level", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("discounts", "entity_id", nullable=True)
    op.add_column("discounts", sa.Column("min_loyalty_level", sa.Integer(), nullable=True))
    op.execute(
        "INSERT INTO discount_link_types (id, name) VALUES (gen_random_uuid(), 'all') ON CONFLICT (name) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM discount_link_types WHERE name = 'all'")
    op.drop_column("discounts", "min_loyalty_level")
    op.alter_column("discounts", "entity_id", nullable=False)
    op.drop_column("users", "loyalty_level")
