"""add notion_sync mapping table

Revision ID: 0003_notion_sync
Revises: 0002_user_language
Create Date: 2026-06-24
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_notion_sync"
down_revision: str | None = "0002_user_language"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notion_sync",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("ref", sa.String(128), nullable=False),
        sa.Column("notion_id", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("kind", "ref", name="uq_notion_sync_kind_ref"),
    )
    op.create_index("ix_notion_sync_kind", "notion_sync", ["kind"])


def downgrade() -> None:
    op.drop_table("notion_sync")
