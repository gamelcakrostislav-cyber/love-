from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import ApiKeyStatus


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Only the sha256 of the key is stored — the raw key is shown to the user once.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(8), nullable=False)

    status: Mapped[str] = mapped_column(String(16), default=ApiKeyStatus.ACTIVE, nullable=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
