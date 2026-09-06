"""fortune wheel coupons: coupon wallet, spins, prize FKs

Revision ID: n2c3d4e5f6a7
Revises: m1b2c3d4e5f6
Create Date: 2026-09-06 15:45:00.000000

Feature 009: coupon_account + coupon_transaction + wheel_spin,
gift_reward.related_spin_id, points_transaction.related_spin_id.
"""

import sqlalchemy as sa
from alembic import op

revision = "n2c3d4e5f6a7"
down_revision = "m1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coupon_account",
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
        sa.UniqueConstraint("loyalty_card_id", name="uq_coupon_account_loyalty_card"),
        sa.CheckConstraint("balance >= 0", name="ck_coupon_account_balance_nonneg"),
    )
    op.create_index(
        "ix_coupon_account_loyalty_card_id",
        "coupon_account",
        ["loyalty_card_id"],
    )

    op.create_table(
        "wheel_spin",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "loyalty_card_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sector_code", sa.String(40), nullable=False),
        sa.Column("prize_type", sa.String(20), nullable=False),
        sa.Column("prize_label", sa.String(200), nullable=False),
        sa.Column("cashback_rub", sa.Integer(), nullable=True),
        sa.Column("coupons_spent", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("prize_type IN ('cashback', 'gift')", name="ck_wheel_spin_prize_type"),
        sa.CheckConstraint("coupons_spent = 1", name="ck_wheel_spin_coupons_spent"),
    )
    op.create_index("ix_wheel_spin_loyalty_card_id", "wheel_spin", ["loyalty_card_id"])
    op.create_index(
        "ix_wheel_spin_user_created",
        "wheel_spin",
        ["loyalty_card_id", "created_at"],
    )

    op.create_table(
        "coupon_transaction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "coupon_account_id",
            sa.Uuid(),
            sa.ForeignKey("coupon_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "related_task_id",
            sa.Uuid(),
            sa.ForeignKey("task.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "related_spin_id",
            sa.Uuid(),
            sa.ForeignKey("wheel_spin.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("week_start", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('weekly_grant', 'task_complete', 'spin')",
            name="ck_coupon_tx_type",
        ),
        sa.CheckConstraint("amount <> 0", name="ck_coupon_tx_amount_nonzero"),
    )
    op.create_index(
        "ix_coupon_transaction_coupon_account_id",
        "coupon_transaction",
        ["coupon_account_id"],
    )
    op.create_index(
        "ix_coupon_tx_account_created",
        "coupon_transaction",
        ["coupon_account_id", "created_at"],
    )
    op.create_index(
        "ux_coupon_tx_weekly",
        "coupon_transaction",
        ["coupon_account_id", "week_start"],
        unique=True,
        postgresql_where=sa.text("type = 'weekly_grant'"),
    )
    op.create_index(
        "ux_coupon_tx_task",
        "coupon_transaction",
        ["related_task_id"],
        unique=True,
        postgresql_where=sa.text("type = 'task_complete'"),
    )
    op.create_index(
        "ux_coupon_tx_spin",
        "coupon_transaction",
        ["related_spin_id"],
        unique=True,
        postgresql_where=sa.text("type = 'spin'"),
    )

    op.add_column(
        "gift_reward",
        sa.Column("related_spin_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_gift_reward_related_spin",
        "gift_reward",
        "wheel_spin",
        ["related_spin_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "points_transaction",
        sa.Column("related_spin_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_points_tx_related_spin",
        "points_transaction",
        "wheel_spin",
        ["related_spin_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ux_points_tx_earn_spin",
        "points_transaction",
        ["related_spin_id"],
        unique=True,
        postgresql_where=sa.text("type = 'earn' AND related_spin_id IS NOT NULL"),
    )

    op.add_column(
        "wheel_spin",
        sa.Column("gift_reward_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_wheel_spin_gift_reward",
        "wheel_spin",
        "gift_reward",
        ["gift_reward_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_wheel_spin_gift_reward", "wheel_spin", type_="foreignkey")
    op.drop_column("wheel_spin", "gift_reward_id")

    op.drop_index("ux_points_tx_earn_spin", table_name="points_transaction")
    op.drop_constraint("fk_points_tx_related_spin", "points_transaction", type_="foreignkey")
    op.drop_column("points_transaction", "related_spin_id")

    op.drop_constraint("fk_gift_reward_related_spin", "gift_reward", type_="foreignkey")
    op.drop_column("gift_reward", "related_spin_id")

    op.drop_index("ux_coupon_tx_spin", table_name="coupon_transaction")
    op.drop_index("ux_coupon_tx_task", table_name="coupon_transaction")
    op.drop_index("ux_coupon_tx_weekly", table_name="coupon_transaction")
    op.drop_index("ix_coupon_tx_account_created", table_name="coupon_transaction")
    op.drop_index("ix_coupon_transaction_coupon_account_id", table_name="coupon_transaction")
    op.drop_table("coupon_transaction")

    op.drop_index("ix_wheel_spin_user_created", table_name="wheel_spin")
    op.drop_index("ix_wheel_spin_loyalty_card_id", table_name="wheel_spin")
    op.drop_table("wheel_spin")

    op.drop_index("ix_coupon_account_loyalty_card_id", table_name="coupon_account")
    op.drop_table("coupon_account")
