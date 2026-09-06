"""replace users.vibe_category/vibe_month with vibe_type_id FK

Revision ID: j8e9f0a1b2c3
Revises: i7d8e9f0a1b2
Create Date: 2026-09-06 10:05:00.000000

Migrates existing vibe_category string values to the normalised vibe_type_id
FK. Rows whose vibe_category matches a vibe_type.name are linked; all others
get NULL. vibe_month is dropped as it is no longer needed.
"""
import sqlalchemy as sa
from alembic import op

revision = "j8e9f0a1b2c3"
down_revision = "i7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("vibe_type_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_users_vibe_type_id",
        "users",
        "vibe_type",
        ["vibe_type_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        sa.text(
            """
            UPDATE users
            SET vibe_type_id = (SELECT id FROM vibe_type WHERE name = users.vibe_category)
            WHERE users.vibe_category IS NOT NULL
            """
        )
    )

    op.drop_column("users", "vibe_category")
    op.drop_column("users", "vibe_month")

    op.create_index("ix_users_vibe_type_id", "users", ["vibe_type_id"])


def downgrade() -> None:
    op.drop_index("ix_users_vibe_type_id", table_name="users")
    op.drop_constraint("fk_users_vibe_type_id", "users", type_="foreignkey")
    op.drop_column("users", "vibe_type_id")
    op.add_column("users", sa.Column("vibe_category", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("vibe_month", sa.Date(), nullable=True))
