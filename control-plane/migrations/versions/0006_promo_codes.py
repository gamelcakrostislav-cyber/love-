"""add promo codes, redemptions, and payments.promo_code_id

Revision ID: 0006_promo_codes
Revises: 0005_feedback
Create Date: 2026-06-26
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_promo_codes"
down_revision: str | None = "0005_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("discount_type", sa.String(length=8), nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("times_redeemed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"], unique=True)

    op.create_table(
        "promo_redemptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("promo_code_id", sa.Integer(),
                  sa.ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("promo_code_id", "user_id", name="uq_promo_redemption_code_user"),
    )
    op.create_index("ix_promo_redemptions_promo_code_id", "promo_redemptions", ["promo_code_id"])
    op.create_index("ix_promo_redemptions_user_id", "promo_redemptions", ["user_id"])

    op.add_column("payments", sa.Column("promo_code_id", sa.Integer(),
                                        sa.ForeignKey("promo_codes.id"), nullable=True))
    op.create_index("ix_payments_promo_code_id", "payments", ["promo_code_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_promo_code_id", table_name="payments")
    op.drop_column("payments", "promo_code_id")
    op.drop_index("ix_promo_redemptions_user_id", table_name="promo_redemptions")
    op.drop_index("ix_promo_redemptions_promo_code_id", table_name="promo_redemptions")
    op.drop_table("promo_redemptions")
    op.drop_index("ix_promo_codes_code", table_name="promo_codes")
    op.drop_table("promo_codes")
