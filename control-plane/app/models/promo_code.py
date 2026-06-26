"""Promo / discount codes and their per-user redemptions.

A code carries either a percentage or a fixed-amount discount, an optional plan
restriction, an optional redemption cap, and an optional expiry. Redemptions are
recorded only when a payment is actually *paid* (idempotent, one row per
user+code) so a user can never double-redeem and the cap reflects real sales.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Discount kinds (kept as plain strings, like the other status columns).
DISCOUNT_PERCENT = "percent"
DISCOUNT_FIXED = "fixed"


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stored upper-cased + trimmed; matched case-insensitively via normalize().
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    discount_type: Mapped[str] = mapped_column(String(8), nullable=False)  # percent | fixed
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # None = applies to any plan.
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    # None = unlimited redemptions.
    max_redemptions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    times_redeemed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # None = never expires.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    __table_args__ = (
        UniqueConstraint("promo_code_id", "user_id", name="uq_promo_redemption_code_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
