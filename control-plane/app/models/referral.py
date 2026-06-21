from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import CommissionStatus, ReferralStatus, ReferrerType


class Referral(Base):
    """An invite edge: referrer -> referred. One referrer per referred user."""

    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    referred_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Snapshot of the referrer's type/rate at referral time.
    referrer_type: Mapped[str] = mapped_column(
        String(16), default=ReferrerType.STANDARD, nullable=False
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), default=ReferralStatus.PENDING, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Set when the referred user makes their first paid invoice.
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Commission(Base):
    """A reward owed to a referrer for a specific qualifying payment."""

    __tablename__ = "commissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    referred_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # One commission per payment — unique guards against double-crediting on replay.
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    rate: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), default=CommissionStatus.PENDING, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
