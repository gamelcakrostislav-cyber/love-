from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Risk weighting accumulated by the anti-abuse layer (0 = trusted).
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Bloggers earn a higher referral rate (admin-flagged).
    is_blogger: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Preferred conversation language (ISO-ish code: en/ru/uk/es/fr).
    language: Mapped[str] = mapped_column(String(8), default="en", server_default="en", nullable=False)

    # Opt-out of marketing pushes (drip / digest / announcements). Transactional
    # messages (payment confirmed, expiry reminders, support) are always sent.
    notifications_opt_out: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # True once the bot has invited this user to the exclusive subscriber group;
    # flipped back to False when their access is revoked on expiry.
    club_member: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Self-referential: who invited this user (nullable).
    referred_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
