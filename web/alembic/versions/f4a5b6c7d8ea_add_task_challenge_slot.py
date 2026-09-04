"""add task.challenge_slot to track which synth.challenge slot a task filled

Revision ID: f4a5b6c7d8ea
Revises: f4a5b6c7d8e9
Create Date: 2026-09-04 21:00:00.000000

After feature 006 was applied, synth.challenges.generate_challenge_for_user
gained a `challenge_slot` field on every result ('llm' / 'spend_threshold' /
'category_expansion'). Store it directly to avoid inferring from mechanic text.
"""
import sqlalchemy as sa
from alembic import op

revision = "f4a5b6c7d8ea"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task", sa.Column("challenge_slot", sa.String(30), nullable=True))
    op.create_index("idx_task_user_slot_status", "task", ["loyalty_card_id", "challenge_slot", "task_status_id"])


def downgrade() -> None:
    op.drop_index("idx_task_user_slot_status", table_name="task")
    op.drop_column("task", "challenge_slot")
