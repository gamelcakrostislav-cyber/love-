"""add users.notifications_opt_out

Revision ID: 0004_user_notifications_opt_out
Revises: 0003_notion_sync
Create Date: 2026-06-24
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_user_notifications_opt_out"
down_revision: str | None = "0003_notion_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("notifications_opt_out", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("users", "notifications_opt_out")
