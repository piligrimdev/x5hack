"""add task, task_status, task_criterion, task_receipt_increment, challenge_generation_log; extend discounts

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-04 20:00:00.000000

Feature: 006-user-challenges (spec.md, data-model.md).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- task_status (dictionary) ----------
    op.create_table(
        "task_status",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
    )

    # ---------- task ----------
    op.create_table(
        "task",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("loyalty_card_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_status_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_status.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), server_default=sa.text("now() + interval '7 days'"), nullable=False),
        sa.Column("criterion_type", sa.String(20), nullable=False),
        sa.Column("criterion_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity_target", sa.Integer, nullable=False, server_default="1"),
        sa.Column("quantity_current", sa.Integer, nullable=False, server_default="0"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("mechanic", sa.String(200), nullable=False),
        sa.Column("reward_rub", sa.Numeric(10, 2), nullable=False),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("path", sa.String(30), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("reward_type", sa.String(20), nullable=False, server_default="discount"),
        sa.Column("reward_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("criterion_type IN ('product', 'category', 'brand')", name="ck_task_criterion_type"),
        sa.CheckConstraint("quantity_target >= 1", name="ck_task_quantity_target"),
        sa.CheckConstraint("quantity_current >= 0", name="ck_task_quantity_current"),
        sa.CheckConstraint("reward_rub >= 0", name="ck_task_reward_rub"),
        sa.CheckConstraint(
            "path IN ('personal', 'generic', 'generic_fallback', 'no_challenge', 'personal_dry_run')",
            name="ck_task_path",
        ),
        sa.CheckConstraint("reward_type IN ('discount')", name="ck_task_reward_type"),
    )
    op.create_index("idx_task_user_status", "task", ["loyalty_card_id", "task_status_id"])
    op.create_index("idx_task_status_deadline", "task", ["task_status_id", "deadline"])

    # ---------- task_criterion (EAV) ----------
    op.create_table(
        "task_criterion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("key", sa.String(100), nullable=True),
        sa.Column("value_num", sa.Numeric(12, 2), nullable=True),
        sa.Column("value_text", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("value_num IS NOT NULL OR value_text IS NOT NULL", name="ck_task_criterion_value"),
    )
    op.create_index("idx_task_criterion_task", "task_criterion", ["task_id"])

    # ---------- task_receipt_increment (idempotency) ----------
    op.create_table(
        "task_receipt_increment",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("task_id", "receipt_id"),
    )
    op.create_index("idx_tri_receipt", "task_receipt_increment", ["receipt_id"])

    # ---------- challenge_generation_log (audit) ----------
    op.create_table(
        "challenge_generation_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt", sa.Text, nullable=True),
        sa.Column("response", sa.Text, nullable=True),
        sa.Column("path", sa.String(30), nullable=False),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("challenge_type", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_cgl_user", "challenge_generation_log", ["user_id", sa.text("created_at DESC")])

    # ---------- extend discounts: value_type, link_task_id ----------
    # Drop existing constraint on value (which caps at 100) — new value_type='fixed_rub' can exceed 100
    op.drop_constraint("ck_discounts_value", "discounts", type_="check")
    op.add_column("discounts", sa.Column("value_type", sa.String(20), nullable=False, server_default="percent"))
    op.add_column("discounts", sa.Column("link_task_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_check_constraint(
        "ck_discounts_value_type",
        "discounts",
        "value_type IN ('percent', 'fixed_rub')",
    )
    # value must be non-negative; percent additionally must be <= 100 (validated in app for now to keep migration simple)
    op.create_check_constraint("ck_discounts_value_nonneg", "discounts", "value >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_discounts_value_nonneg", "discounts", type_="check")
    op.drop_constraint("ck_discounts_value_type", "discounts", type_="check")
    op.drop_column("discounts", "link_task_id")
    op.drop_column("discounts", "value_type")
    op.create_check_constraint("ck_discounts_value", "discounts", "value >= 0 AND value <= 100")

    op.drop_index("idx_cgl_user", table_name="challenge_generation_log")
    op.drop_table("challenge_generation_log")

    op.drop_index("idx_tri_receipt", table_name="task_receipt_increment")
    op.drop_table("task_receipt_increment")

    op.drop_index("idx_task_criterion_task", table_name="task_criterion")
    op.drop_table("task_criterion")

    op.drop_index("idx_task_status_deadline", table_name="task")
    op.drop_index("idx_task_user_status", table_name="task")
    op.drop_table("task")

    op.drop_table("task_status")
