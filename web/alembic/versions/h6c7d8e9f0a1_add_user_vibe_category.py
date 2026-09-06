"""add vibe_category and vibe_month to users

Revision ID: h6c7d8e9f0a1
Revises: g5b6c7d8e9f0
Create Date: 2026-09-05 12:00:00.000000

Each user is assigned a "vibe" theme for the calendar month (e.g. "Здоровье
и лёгкость") that constrains one of their four challenge slots
(synth.challenges.VIBE_CATEGORIES). Random for now (no selection UI yet) —
these two columns exist so a future manual-selection feature can simply
overwrite them instead of requiring a new migration.
"""
import sqlalchemy as sa
from alembic import op

revision = "h6c7d8e9f0a1"
down_revision = "g5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("vibe_category", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("vibe_month", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "vibe_month")
    op.drop_column("users", "vibe_category")
