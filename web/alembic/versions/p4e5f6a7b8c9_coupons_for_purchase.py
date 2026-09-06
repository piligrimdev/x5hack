"""coupons for every 1000 rub spent

Revision ID: p4e5f6a7b8c9
Revises: o3d4e5f6a7b8
Create Date: 2026-09-06 21:55:00.000000

Award wheel coupons from receipt spend. Adds spend_remainder_rub,
purchase tx type, related_receipt_id.
"""

import sqlalchemy as sa
from alembic import op

revision = "p4e5f6a7b8c9"
down_revision = "o3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "coupon_account",
        sa.Column("spend_remainder_rub", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_coupon_account_spend_remainder",
        "coupon_account",
        "spend_remainder_rub >= 0 AND spend_remainder_rub < 1000",
    )
    op.add_column(
        "coupon_transaction",
        sa.Column(
            "related_receipt_id",
            sa.Uuid(),
            sa.ForeignKey("receipts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.drop_constraint("ck_coupon_tx_type", "coupon_transaction", type_="check")
    op.create_check_constraint(
        "ck_coupon_tx_type",
        "coupon_transaction",
        "type IN ('weekly_grant', 'task_complete', 'spin', 'referral', 'purchase')",
    )
    op.create_index(
        "ux_coupon_tx_purchase",
        "coupon_transaction",
        ["related_receipt_id"],
        unique=True,
        postgresql_where=sa.text("type = 'purchase'"),
    )


def downgrade() -> None:
    op.drop_index("ux_coupon_tx_purchase", table_name="coupon_transaction")
    op.drop_constraint("ck_coupon_tx_type", "coupon_transaction", type_="check")
    op.create_check_constraint(
        "ck_coupon_tx_type",
        "coupon_transaction",
        "type IN ('weekly_grant', 'task_complete', 'spin', 'referral')",
    )
    op.drop_column("coupon_transaction", "related_receipt_id")
    op.drop_constraint(
        "ck_coupon_account_spend_remainder", "coupon_account", type_="check"
    )
    op.drop_column("coupon_account", "spend_remainder_rub")
