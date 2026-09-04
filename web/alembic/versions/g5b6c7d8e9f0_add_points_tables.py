"""add points_account, points_transaction, points_settings and cashback fields on receipts

Revision ID: g5b6c7d8e9f0
Revises: f4a5b6c7d8ea
Create Date: 2026-09-04 21:30:00.000000

Feature 007 (cashback-points): reward за задание теперь начисляется в баллах
вместо создания Discount. Баллами можно оплатить чек (кешбек к итогу).
"""

import sqlalchemy as sa
from alembic import op

revision = "g5b6c7d8e9f0"
down_revision = "f4a5b6c7d8ea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "points_account",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "loyalty_card_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("loyalty_card_id", name="uq_points_account_loyalty_card"),
        sa.CheckConstraint("balance >= 0", name="ck_points_account_balance_nonneg"),
    )
    op.create_index(
        "ix_points_account_loyalty_card_id",
        "points_account",
        ["loyalty_card_id"],
    )

    op.create_table(
        "points_transaction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "points_account_id",
            sa.Uuid(),
            sa.ForeignKey("points_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "related_task_id",
            sa.Uuid(),
            sa.ForeignKey("task.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "related_receipt_id",
            sa.Uuid(),
            sa.ForeignKey("receipts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rate_at_time", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("type IN ('earn', 'spend')", name="ck_points_tx_type"),
        sa.CheckConstraint("amount <> 0", name="ck_points_tx_amount_nonzero"),
    )
    op.create_index(
        "ix_points_transaction_points_account_id",
        "points_transaction",
        ["points_account_id"],
    )
    op.create_index(
        "ix_points_tx_account_created",
        "points_transaction",
        ["points_account_id", "created_at"],
    )
    op.create_index(
        "ux_points_tx_earn_task",
        "points_transaction",
        ["related_task_id"],
        unique=True,
        postgresql_where=sa.text("type = 'earn'"),
    )

    op.create_table(
        "points_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "rate_points_per_rub", sa.Integer(), nullable=False, server_default="10"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_points_settings_singleton"),
        sa.CheckConstraint(
            "rate_points_per_rub > 0", name="ck_points_settings_rate_positive"
        ),
    )
    op.execute(
        "INSERT INTO points_settings (id, rate_points_per_rub, updated_at) "
        "VALUES (1, 10, now())"
    )

    op.add_column(
        "receipts",
        sa.Column(
            "cashback_applied_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "receipts",
        sa.Column(
            "cashback_applied_rub",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "receipts",
        sa.Column("points_rate_at_purchase", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_receipts_cashback_points_nonneg",
        "receipts",
        "cashback_applied_points >= 0",
    )
    op.create_check_constraint(
        "ck_receipts_cashback_rub_nonneg",
        "receipts",
        "cashback_applied_rub >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_receipts_cashback_rub_nonneg", "receipts", type_="check")
    op.drop_constraint("ck_receipts_cashback_points_nonneg", "receipts", type_="check")
    op.drop_column("receipts", "points_rate_at_purchase")
    op.drop_column("receipts", "cashback_applied_rub")
    op.drop_column("receipts", "cashback_applied_points")

    op.drop_table("points_settings")

    op.drop_index("ux_points_tx_earn_task", table_name="points_transaction")
    op.drop_index("ix_points_tx_account_created", table_name="points_transaction")
    op.drop_index(
        "ix_points_transaction_points_account_id", table_name="points_transaction"
    )
    op.drop_table("points_transaction")

    op.drop_index("ix_points_account_loyalty_card_id", table_name="points_account")
    op.drop_table("points_account")
