"""referral program: codes, links, coupon/points FKs

Revision ID: o3d4e5f6a7b8
Revises: n2c3d4e5f6a7
Create Date: 2026-09-06 19:10:00.000000

Feature 011: referral_code + referral_link, coupon/points related_referral_link_id,
type='referral', seed discount_link_types 'all'.
"""

import sqlalchemy as sa
from alembic import op

revision = "o3d4e5f6a7b8"
down_revision = "n2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_code",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column(
            "inviter_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("code", name="uq_referral_code_code"),
        sa.CheckConstraint("code ~ '^[A-Za-z0-9]{6}$'", name="ck_referral_code_format"),
    )
    op.create_index("ix_referral_code_inviter_id", "referral_code", ["inviter_id"])
    op.create_index(
        "ix_referral_code_inviter_created",
        "referral_code",
        ["inviter_id", "created_at"],
    )

    op.create_table(
        "referral_link",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "referral_code_id",
            sa.Uuid(),
            sa.ForeignKey("referral_code.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "inviter_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invitee_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("inviter_coupons", sa.Integer(), nullable=False),
        sa.Column("inviter_cashback_rub", sa.Integer(), nullable=False),
        sa.Column("discount_valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purchase_window_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "discount_id",
            sa.Uuid(),
            sa.ForeignKey("discounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reward_status",
            sa.String(24),
            nullable=False,
            server_default="awaiting_purchase",
        ),
        sa.Column(
            "qualifying_receipt_id",
            sa.Uuid(),
            sa.ForeignKey("receipts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("referral_code_id", name="uq_referral_link_code"),
        sa.CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 100",
            name="ck_referral_link_discount_pct",
        ),
        sa.CheckConstraint("inviter_coupons >= 0", name="ck_referral_link_coupons"),
        sa.CheckConstraint("inviter_cashback_rub >= 0", name="ck_referral_link_cashback"),
        sa.CheckConstraint(
            "reward_status IN ('awaiting_purchase', 'rewarded')",
            name="ck_referral_link_reward_status",
        ),
        sa.CheckConstraint("inviter_id <> invitee_id", name="ck_referral_link_not_self"),
    )
    op.create_index(
        "ix_referral_link_invitee_activated",
        "referral_link",
        ["invitee_id", "activated_at"],
    )
    op.create_index(
        "ix_referral_link_inviter_activated",
        "referral_link",
        ["inviter_id", "activated_at"],
    )
    op.create_index(
        "ux_referral_link_qualifying_receipt",
        "referral_link",
        ["qualifying_receipt_id"],
        unique=True,
        postgresql_where=sa.text("qualifying_receipt_id IS NOT NULL"),
    )

    op.add_column(
        "coupon_transaction",
        sa.Column(
            "related_referral_link_id",
            sa.Uuid(),
            sa.ForeignKey("referral_link.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.drop_constraint("ck_coupon_tx_type", "coupon_transaction", type_="check")
    op.create_check_constraint(
        "ck_coupon_tx_type",
        "coupon_transaction",
        "type IN ('weekly_grant', 'task_complete', 'spin', 'referral')",
    )
    op.create_index(
        "ux_coupon_tx_referral",
        "coupon_transaction",
        ["related_referral_link_id"],
        unique=True,
        postgresql_where=sa.text("type = 'referral'"),
    )

    op.add_column(
        "points_transaction",
        sa.Column(
            "related_referral_link_id",
            sa.Uuid(),
            sa.ForeignKey("referral_link.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ux_points_tx_earn_referral",
        "points_transaction",
        ["related_referral_link_id"],
        unique=True,
        postgresql_where=sa.text(
            "type = 'earn' AND related_referral_link_id IS NOT NULL"
        ),
    )

    op.execute(
        "INSERT INTO discount_link_types (id, name) VALUES "
        "(gen_random_uuid(), 'all') ON CONFLICT (name) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_index("ux_points_tx_earn_referral", table_name="points_transaction")
    op.drop_column("points_transaction", "related_referral_link_id")
    op.drop_index("ux_coupon_tx_referral", table_name="coupon_transaction")
    op.drop_constraint("ck_coupon_tx_type", "coupon_transaction", type_="check")
    op.create_check_constraint(
        "ck_coupon_tx_type",
        "coupon_transaction",
        "type IN ('weekly_grant', 'task_complete', 'spin')",
    )
    op.drop_column("coupon_transaction", "related_referral_link_id")
    op.drop_index("ux_referral_link_qualifying_receipt", table_name="referral_link")
    op.drop_index("ix_referral_link_inviter_activated", table_name="referral_link")
    op.drop_index("ix_referral_link_invitee_activated", table_name="referral_link")
    op.drop_table("referral_link")
    op.drop_index("ix_referral_code_inviter_created", table_name="referral_code")
    op.drop_index("ix_referral_code_inviter_id", table_name="referral_code")
    op.drop_table("referral_code")
