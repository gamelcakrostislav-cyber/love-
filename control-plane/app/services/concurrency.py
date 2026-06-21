"""Per-key concurrency cap.

Policy (chosen during planning): when a new session would exceed
`max_concurrent_sessions`, evict the oldest active session and log an
abuse_event — smooth UX, but every overflow is still recorded so a shared key
that bounces between machines leaves a visible trail.
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AbuseType
from app.models.session import Session
from app.services import session_store
from app.services.audit import record_abuse, record_audit


async def enforce(
    db: AsyncSession,
    *,
    key_id: int,
    user_id: int,
    max_concurrent: int,
) -> list[str]:
    """Evict oldest sessions until a new one fits. Returns evicted session ids."""
    evicted: list[str] = []
    count = await session_store.active_count(key_id)
    while count >= max_concurrent:
        victim = await session_store.oldest(key_id)
        if victim is None:
            break
        await session_store.revoke(victim, key_id)
        await db.execute(
            update(Session).where(Session.id == victim).values(revoked=True)
        )
        await record_abuse(
            db,
            type_=AbuseType.CONCURRENCY_EVICT,
            user_id=user_id,
            key_id=key_id,
            detail=f"evicted session {victim}: over concurrency cap {max_concurrent}",
        )
        await record_audit(
            db,
            actor="system",
            action="session_evicted",
            target=victim,
            meta={"key_id": key_id, "reason": "concurrency_cap"},
        )
        evicted.append(victim)
        count = await session_store.active_count(key_id)
    return evicted
