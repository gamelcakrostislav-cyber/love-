from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class NotionSync(Base):
    """Maps a control-plane object to its mirrored Notion page (or database).

    One row per synced thing, keyed by (kind, ref):
      - kind="database", ref="<db key>"  -> notion_id is a Notion *database* id.
      - kind="<entity>",  ref="<row id>" -> notion_id is a Notion *page* id, and
        content_hash records the last-pushed payload so unchanged rows are skipped.
    This is what makes the sync idempotent and cheap on every reconcile pass.
    """

    __tablename__ = "notion_sync"
    __table_args__ = (
        UniqueConstraint("kind", "ref", name="uq_notion_sync_kind_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    ref: Mapped[str] = mapped_column(String(128), nullable=False)
    notion_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
