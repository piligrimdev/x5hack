"""create gift_reward table

Revision ID: m1b2c3d4e5f6
Revises: l0a1b2c3d4e5
Create Date: 2026-09-06 10:20:00.000000

Introduces gift_reward to track gift-type rewards awarded to users. Each row
links optionally to a task and mandatorily to a user (via loyalty_card_id),
records what product/category gift was awarded, and tracks its lifecycle
status (active / used / expired).
"""
import sqlalchemy as sa
from alembic import op

revision = "m1b2c3d4e5f6"
down_revision = "l0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gift_reward",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("loyalty_card_id", sa.UUID(), nullable=False),
        sa.Column("criterion_type", sa.String(20), nullable=False),
        sa.Column("criterion_entity_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "criterion_type IN ('product', 'category')",
            name="ck_gift_reward_criterion_type",
        ),
        sa.CheckConstraint("quantity >= 1", name="ck_gift_reward_quantity"),
        sa.CheckConstraint(
            "status IN ('active', 'used', 'expired')",
            name="ck_gift_reward_status",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["loyalty_card_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gift_reward_user_status", "gift_reward", ["loyalty_card_id", "status"])


def downgrade() -> None:
    op.drop_table("gift_reward")
