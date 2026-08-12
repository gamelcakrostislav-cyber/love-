from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BotContent(Base):
    """Admin-editable bot copy / branding, stored as key → value.

    Lets admins change the welcome message, the /start banner, and the
    'What can this bot do?' description live (via admin commands) without a code
    change or redeploy.
    """

    __tablename__ = "bot_content"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
