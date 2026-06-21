"""Revocation & expiry — kills access server-side.

- Admin `/revoke`: subscriptions -> revoked, keys disabled, sessions killed now.
- Worker expiry: subscriptions past `expires_at` -> expired, same teardown.
Killing a session deletes its Redis state, so protected calls stop honoring the
token within the entitlement cache window even if the JWT hasn't expired yet.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.enums import ApiKeyStatus, SubscriptionStatus
from app.models.session import Session
from app.models.subscription import Subscription
from app.services import entitlements, session_store
from app.services.audit import record_audit


async def kill_key_sessions(db: AsyncSession, key_id: int) -> int:
    """Revoke all live sessions for a key (Redis + DB). Returns count killed."""
    sids = await session_store.list_sessions(key_id)
    for sid in sids:
        await session_store.revoke(sid, key_id)
    await db.execute(
        update(Session)
        .where(Session.key_id == key_id, Session.revoked.is_(False))
        .values(revoked=True)
    )
    await entitlements.invalidate(key_id)
    return len(sids)


async def _disable_user_keys(db: AsyncSession, user_id: int) -> None:
    keys = list(await db.scalars(
        select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.status == ApiKeyStatus.ACTIVE)
    ))
    for key in keys:
        key.status = ApiKeyStatus.DISABLED
        await kill_key_sessions(db, key.id)


async def revoke_user(db: AsyncSession, *, user_id: int, actor: str) -> None:
    await db.execute(
        update(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status == SubscriptionStatus.ACTIVE)
        .values(status=SubscriptionStatus.REVOKED)
    )
    await _disable_user_keys(db, user_id)
    await record_audit(db, actor=actor, action="user_revoked", target=str(user_id), meta={})


async def expire_due(db: AsyncSession) -> int:
    """Expire subscriptions past their deadline; tear down their access."""
    now = datetime.now(UTC)
    subs = list(await db.scalars(
        select(Subscription).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at <= now,
        )
    ))
    for sub in subs:
        sub.status = SubscriptionStatus.EXPIRED
        await _disable_user_keys(db, sub.user_id)
        await record_audit(
            db, actor="system", action="subscription_expired", target=str(sub.user_id),
            meta={"subscription_id": sub.id, "expired_at": sub.expires_at.isoformat()},
        )
    return len(subs)


async def reap_sessions(db: AsyncSession) -> int:
    """Mark DB session rows past expiry as revoked (Redis state self-expires)."""
    now = datetime.now(UTC)
    result = await db.execute(
        update(Session)
        .where(Session.revoked.is_(False), Session.expires_at <= now)
        .values(revoked=True)
    )
    return result.rowcount or 0
