"""Worker expiry: past-deadline subscriptions are expired and torn down."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.api_key import ApiKey
from app.models.device import Device
from app.models.enums import ApiKeyStatus, SubscriptionStatus
from app.models.session import Session as SessionRow
from app.services import revocation, session_store
from tests.factories import make_key, make_plan, make_subscription, make_user


async def test_expire_due_tears_down_access(db):
    user = await make_user(db)
    plan = await make_plan(db)
    sub = await make_subscription(db, user=user, plan=plan, days_left=30)
    # Force it past expiry.
    sub.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    key_id, _raw = await make_key(db, user=user)

    device = Device(key_id=key_id, fingerprint="dev-expire", first_seen_ip="8.8.8.8")
    db.add(device)
    await db.flush()

    # A live session for the key (Redis + DB row).
    sid = "sess-expire-1"
    db.add(SessionRow(
        id=sid, key_id=key_id, device_id=device.id,
        ip="8.8.8.8", expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    await session_store.create(
        session_id=sid, key_id=key_id, device_id=device.id, ip="8.8.8.8", signing_secret="x"
    )
    await db.commit()
    assert await session_store.get(sid) is not None

    expired = await revocation.expire_due(db)
    await db.commit()

    assert expired == 1
    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.EXPIRED

    key = await db.scalar(select(ApiKey).where(ApiKey.id == key_id))
    assert key.status == ApiKeyStatus.DISABLED
    # Redis session killed.
    assert await session_store.get(sid) is None


async def test_active_subscription_is_not_expired(db):
    user = await make_user(db)
    plan = await make_plan(db)
    await make_subscription(db, user=user, plan=plan, days_left=10)
    await db.commit()

    expired = await revocation.expire_due(db)
    await db.commit()
    assert expired == 0
