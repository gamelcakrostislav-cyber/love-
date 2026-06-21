"""Device binding.

Each key allows a small number of registered devices (from the plan). A new
device beyond the limit is created in COOLDOWN with a 24h timer; it auto-promotes
to ACTIVE on the first session attempt after the timer elapses. This stops a key
from silently fanning out to many machines at once.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.device import Device
from app.models.enums import AbuseType, DeviceStatus
from app.services.audit import record_abuse, record_audit
from app.services.errors import DeviceInCooldown


async def resolve_for_session(
    db: AsyncSession,
    *,
    key_id: int,
    user_id: int,
    fingerprint: str,
    ip: str | None,
    max_devices: int,
) -> Device:
    """Return an ACTIVE device for this (key, fingerprint), enforcing the limit.

    Raises DeviceInCooldown if the device is new-beyond-limit (now registered in
    cooldown) or still inside its cooldown window.
    """
    now = datetime.now(UTC)
    device = await db.scalar(
        select(Device).where(Device.key_id == key_id, Device.fingerprint == fingerprint)
    )

    if device is not None:
        if device.status == DeviceStatus.ACTIVE:
            return device
        if device.status == DeviceStatus.COOLDOWN:
            if device.cooldown_until is not None and device.cooldown_until <= now:
                device.status = DeviceStatus.ACTIVE
                device.cooldown_until = None
                await record_audit(
                    db, actor="system", action="device_promoted", target=str(device.id),
                    meta={"key_id": key_id, "fingerprint": fingerprint},
                )
                return device
            raise DeviceInCooldown(
                f"device in cooldown until {device.cooldown_until.isoformat()}"
                if device.cooldown_until else "device in cooldown"
            )
        # REMOVED device re-registering is treated like a new device below.

    active_count = await db.scalar(
        select(func.count())
        .select_from(Device)
        .where(Device.key_id == key_id, Device.status == DeviceStatus.ACTIVE)
    )

    if device is None:
        device = Device(key_id=key_id, fingerprint=fingerprint, first_seen_ip=ip)
        db.add(device)

    if (active_count or 0) < max_devices:
        device.status = DeviceStatus.ACTIVE
        device.cooldown_until = None
        await db.flush()
        return device

    # Over the limit: park in cooldown and refuse this attempt.
    cooldown_until = now + timedelta(hours=settings.device_register_cooldown_hours)
    device.status = DeviceStatus.COOLDOWN
    device.cooldown_until = cooldown_until
    await db.flush()
    await record_abuse(
        db, type_=AbuseType.DEVICE_LIMIT, user_id=user_id, key_id=key_id,
        detail=f"new device {fingerprint[:16]}… over max_devices={max_devices}",
    )
    await record_audit(
        db, actor="system", action="device_cooldown", target=str(device.id),
        meta={"key_id": key_id, "cooldown_until": cooldown_until.isoformat()},
    )
    raise DeviceInCooldown(f"device registered in cooldown until {cooldown_until.isoformat()}")


async def list_for_key(db: AsyncSession, key_id: int) -> list[Device]:
    result = await db.scalars(
        select(Device)
        .where(Device.key_id == key_id, Device.status != DeviceStatus.REMOVED)
        .order_by(Device.registered_at)
    )
    return list(result)


async def remove(db: AsyncSession, *, key_id: int, device_id: int) -> bool:
    device = await db.scalar(
        select(Device).where(Device.id == device_id, Device.key_id == key_id)
    )
    if device is None or device.status == DeviceStatus.REMOVED:
        return False
    device.status = DeviceStatus.REMOVED
    await record_audit(
        db, actor="user", action="device_removed", target=str(device_id),
        meta={"key_id": key_id},
    )
    return True
