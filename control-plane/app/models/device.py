from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import DeviceStatus


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        # A given fingerprint registers at most once per key.
        UniqueConstraint("key_id", "fingerprint", name="uq_device_key_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_id: Mapped[int] = mapped_column(
        ForeignKey("api_keys.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Stable client-generated hardware/install id. Indexed for cross-account dedup.
    fingerprint: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    first_seen_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default=DeviceStatus.ACTIVE, nullable=False)

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # When a cooldown-pending device becomes usable (registered beyond max_devices).
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
