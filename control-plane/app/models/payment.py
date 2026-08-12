from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import PaymentStatus


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    # Provider invoice id — unique so webhook replays are idempotent.
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    # Payer identity from the provider (e.g. crypto wallet / payer id) for
    # cross-account linkage during multi-account detection.
    payer_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.PENDING, nullable=False)

    # Set when a discount code was applied; `amount` already reflects the
    # discounted total. The redemption is recorded only once this payment is paid.
    promo_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("promo_codes.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
