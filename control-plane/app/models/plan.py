from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)

    rate_limit_per_min: Mapped[int] = mapped_column(Integer, nullable=False)
    max_devices: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_concurrent_sessions: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Trial gating: when set, the protected endpoint only returns opportunities
    # whose profitability is <= this cap (trial sees the 2% tier). NULL = no cap.
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_profitability: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
