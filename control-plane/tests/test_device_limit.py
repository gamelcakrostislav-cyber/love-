"""Device-binding limit + 24h cooldown auto-approve."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.device import Device
from app.models.enums import AbuseType, DeviceStatus
from app.models.abuse_event import AbuseEvent
from app.services import devices, licensing
from app.services.errors import DeviceInCooldown
from tests.factories import make_key, make_plan, make_subscription, make_user


async def _setup(db, max_devices=1):
    user = await make_user(db)
    plan = await make_plan(db, max_devices=max_devices, max_concurrent_sessions=2)
    await make_subscription(db, user=user, plan=plan)
    key_id, raw = await make_key(db, user=user)
    await db.commit()
    return user, key_id, raw


async def test_first_device_registers_active(db):
    user, key_id, raw = await _setup(db)
    result = await licensing.create_session(
        db, raw_key=raw, fingerprint="device-A", ip="8.8.8.8"
    )
    await db.commit()
    assert result.entitlement.max_devices == 1
    dev = await db.scalar(select(Device).where(Device.key_id == key_id))
    assert dev.status == DeviceStatus.ACTIVE


async def test_second_device_goes_to_cooldown_and_logs(db):
    user, key_id, raw = await _setup(db, max_devices=1)
    await licensing.create_session(db, raw_key=raw, fingerprint="device-A", ip="8.8.8.8")
    await db.commit()

    with pytest.raises(DeviceInCooldown):
        await devices.resolve_for_session(
            db, key_id=key_id, user_id=user.id, fingerprint="device-B",
            ip="8.8.8.8", max_devices=1,
        )
    await db.commit()

    dev_b = await db.scalar(select(Device).where(Device.fingerprint == "device-B"))
    assert dev_b.status == DeviceStatus.COOLDOWN
    assert dev_b.cooldown_until is not None

    abuse = await db.scalar(select(AbuseEvent).where(AbuseEvent.type == AbuseType.DEVICE_LIMIT))
    assert abuse is not None


async def test_cooldown_device_auto_approves_after_window(db):
    user, key_id, raw = await _setup(db, max_devices=1)
    await licensing.create_session(db, raw_key=raw, fingerprint="device-A", ip="8.8.8.8")
    await db.commit()

    with pytest.raises(DeviceInCooldown):
        await devices.resolve_for_session(
            db, key_id=key_id, user_id=user.id, fingerprint="device-B",
            ip="8.8.8.8", max_devices=1,
        )
    await db.commit()

    # Fast-forward the cooldown.
    dev_b = await db.scalar(select(Device).where(Device.fingerprint == "device-B"))
    dev_b.cooldown_until = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()

    promoted = await devices.resolve_for_session(
        db, key_id=key_id, user_id=user.id, fingerprint="device-B",
        ip="8.8.8.8", max_devices=1,
    )
    assert promoted.status == DeviceStatus.ACTIVE
