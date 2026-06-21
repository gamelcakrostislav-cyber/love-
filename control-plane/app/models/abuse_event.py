from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AbuseEvent(Base):
    __tablename__ = "abuse_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    key_id: Mapped[int | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), index=True, nullable=True
    )

    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
