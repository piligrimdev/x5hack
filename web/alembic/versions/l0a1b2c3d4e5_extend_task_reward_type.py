"""extend task.reward_type CHECK to include cashback and gift

Revision ID: l0a1b2c3d4e5
Revises: k9f0a1b2c3d4
Create Date: 2026-09-06 10:15:00.000000

Adds 'cashback' and 'gift' as valid values for task.reward_type in addition
to the existing 'discount'. The old constraint is dropped first, then the
new broader constraint is created.
"""
import sqlalchemy as sa
from alembic import op

revision = "l0a1b2c3d4e5"
down_revision = "k9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_task_reward_type", "task", type_="check")
    op.create_check_constraint(
        "ck_task_reward_type",
        "task",
        "reward_type IN ('discount', 'cashback', 'gift')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_task_reward_type", "task", type_="check")
    op.create_check_constraint(
        "ck_task_reward_type",
        "task",
        "reward_type IN ('discount')",
    )
