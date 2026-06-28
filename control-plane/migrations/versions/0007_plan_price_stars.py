"""add plans.price_stars for native Telegram Stars checkout

Revision ID: 0007_plan_price_stars
Revises: 0006_promo_codes
Create Date: 2026-06-28
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_plan_price_stars"
down_revision: str | None = "0006_promo_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("price_stars", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("plans", "price_stars")
