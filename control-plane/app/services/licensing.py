"""`/auth/session` orchestration: key -> device-bound short-lived token.

Enforcement order (all server-side, zero trust):
  1. validate key (active, not disabled)
  2. entitlement recompute from Postgres (subscription active & unexpired)
  3. device binding (known+active, or within max_devices, else cooldown)
  4. concurrency cap (evict oldest if over)
  5. risk checks (IP velocity / impossible travel)  -- Phase 4
  6. issue JWT bound to device + session id; mirror session in Redis
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models.session import Session
from app.services import (
    abuse,
    concurrency,
    devices,
    entitlements,
    keys,
    risk,
    session_store,
)
from app.services.audit import record_audit
from app.services.entitlements import Entitlement
from app.services.errors import NoActiveSubscription


@dataclass
class SessionResult:
    token: str
    session_id: str
    signing_secret: str
    expires_at: datetime
    entitlement: Entitlement
    evicted_sessions: list[str]
    flagged: bool


async def create_session(
    db: AsyncSession,
    *,
    raw_key: str,
    fingerprint: str,
    ip: str | None,
    context: dict | None = None,
) -> SessionResult:
    # 1. Key.
    key = await keys.validate(db, raw_key)

    # 2. Entitlement (authoritative recompute + cache). None => unentitled.
    ent = await entitlements.recompute(db, key.id)
    if ent is None:
        raise NoActiveSubscription()

    # 3. Device binding / limit.
    device = await devices.resolve_for_session(
        db,
        key_id=key.id,
        user_id=key.user_id,
        fingerprint=fingerprint,
        ip=ip,
        max_devices=ent.max_devices,
    )

    # 3b. Multi-account: same fingerprint under other accounts -> flag cluster.
    cluster = await abuse.detect_multi_account(
        db, key_id=key.id, user_id=key.user_id, fingerprint=fingerprint,
    )

    # 4. Concurrency cap.
    evicted = await concurrency.enforce(
        db, key_id=key.id, user_id=key.user_id,
        max_concurrent=ent.max_concurrent_sessions,
    )

    # 5. Risk checks (IP velocity / impossible travel).
    travel_flagged = await risk.evaluate_session(
        db, key_id=key.id, user_id=key.user_id, ip=ip,
    )

    # 6. Issue token + signing secret + mirror session.
    session_id = security.new_session_id()
    signing_secret = security.new_signing_secret()
    token, expires_at = security.create_session_token(
        key_id=key.id, session_id=session_id, fingerprint=fingerprint,
    )
    db.add(
        Session(
            id=session_id,
            key_id=key.id,
            device_id=device.id,
            ip=ip,
            expires_at=expires_at,
        )
    )
    await session_store.create(
        session_id=session_id, key_id=key.id, device_id=device.id, ip=ip,
        signing_secret=signing_secret,
    )
    await record_audit(
        db, actor=f"user:{key.user_id}", action="session_issued", target=session_id,
        meta={"key_id": key.id, "device_id": device.id, "ip": ip, "plan": ent.plan_name},
    )

    return SessionResult(
        token=token,
        session_id=session_id,
        signing_secret=signing_secret,
        expires_at=expires_at,
        entitlement=ent,
        evicted_sessions=evicted,
        flagged=bool(cluster) or travel_flagged,
    )
