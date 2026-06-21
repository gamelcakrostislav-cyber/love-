"""Concurrency cap: a new session evicts the oldest and logs it."""

from __future__ import annotations

from sqlalchemy import select

from app.models.abuse_event import AbuseEvent
from app.models.enums import AbuseType
from app.services import licensing, session_store
from tests.factories import make_key, make_plan, make_subscription, make_user


async def _setup(db, max_concurrent=1, max_devices=2):
    user = await make_user(db)
    plan = await make_plan(
        db, max_devices=max_devices, max_concurrent_sessions=max_concurrent
    )
    await make_subscription(db, user=user, plan=plan)
    key_id, raw = await make_key(db, user=user)
    await db.commit()
    return user, key_id, raw


async def test_second_session_evicts_first(db):
    user, key_id, raw = await _setup(db, max_concurrent=1)

    s1 = await licensing.create_session(db, raw_key=raw, fingerprint="dev-A", ip="8.8.8.8")
    await db.commit()
    assert await session_store.active_count(key_id) == 1

    s2 = await licensing.create_session(db, raw_key=raw, fingerprint="dev-A", ip="8.8.8.8")
    await db.commit()

    # Cap holds at 1; the first session was evicted.
    assert await session_store.active_count(key_id) == 1
    assert len(s2.evicted_sessions) == 1
    assert s1.session_id in s2.evicted_sessions
    assert await session_store.get(s1.session_id) is None
    assert await session_store.get(s2.session_id) is not None

    evt = await db.scalar(
        select(AbuseEvent).where(AbuseEvent.type == AbuseType.CONCURRENCY_EVICT)
    )
    assert evt is not None


async def test_within_cap_keeps_both(db):
    user, key_id, raw = await _setup(db, max_concurrent=2, max_devices=2)

    s1 = await licensing.create_session(db, raw_key=raw, fingerprint="dev-A", ip="8.8.8.8")
    await db.commit()
    s2 = await licensing.create_session(db, raw_key=raw, fingerprint="dev-B", ip="8.8.8.8")
    await db.commit()

    assert await session_store.active_count(key_id) == 2
    assert len(s2.evicted_sessions) == 0
    assert await session_store.get(s1.session_id) is not None
