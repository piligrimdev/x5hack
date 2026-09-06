"""create task_item table and backfill from task

Revision ID: k9f0a1b2c3d4
Revises: j8e9f0a1b2c3
Create Date: 2026-09-06 10:10:00.000000

Introduces task_item to represent individual sub-criteria of a task, allowing
multi-item challenges. Existing task rows are backfilled: each task's single
criterion (criterion_type, criterion_entity_id, quantity_target,
quantity_current) is inserted as a task_item row.
"""
import sqlalchemy as sa
from alembic import op

revision = "k9f0a1b2c3d4"
down_revision = "j8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_item",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("criterion_type", sa.String(20), nullable=False),
        sa.Column("criterion_entity_id", sa.UUID(), nullable=False),
        sa.Column("quantity_target", sa.Integer(), nullable=False),
        sa.Column("quantity_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(200), nullable=True),
        sa.CheckConstraint(
            "criterion_type IN ('product', 'category', 'brand')",
            name="ck_task_item_criterion_type",
        ),
        sa.CheckConstraint("quantity_target >= 1", name="ck_task_item_quantity_target"),
        sa.CheckConstraint("quantity_current >= 0", name="ck_task_item_quantity_current"),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_item_task_id", "task_item", ["task_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO task_item (id, task_id, criterion_type, criterion_entity_id, quantity_target, quantity_current)
            SELECT gen_random_uuid(), id, criterion_type, criterion_entity_id, quantity_target, quantity_current
            FROM task
            """
        )
    )


def downgrade() -> None:
    op.drop_table("task_item")
