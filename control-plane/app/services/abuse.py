"""Multi-account detection and flagging.

Philosophy from the spec: flag, don't silently ban. Tripping a threshold sets
`api_keys.flagged`, records an abuse_event, bumps the user's risk_score, and
surfaces to the admin — but the key keeps working until an admin acts. This
keeps false positives cheap.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.device import Device
from app.models.enums import AbuseType, DeviceStatus
from app.models.payment import Payment
from app.models.user import User
from app.services.audit import record_abuse, record_audit


async def flag_key(
    db: AsyncSession,
    *,
    key_id: int | None,
    user_id: int | None,
    type_: str,
    detail: str,
    risk_delta: int = 10,
) -> None:
    """Set the key's flagged state, log the abuse event, and raise risk."""
    if key_id:
        await db.execute(update(ApiKey).where(ApiKey.id == key_id).values(flagged=True))
    if user_id is not None:
        await db.execute(
            update(User).where(User.id == user_id).values(risk_score=User.risk_score + risk_delta)
        )
    await record_abuse(db, type_=type_, user_id=user_id, key_id=key_id, detail=detail)
    await record_audit(
        db, actor="system", action="key_flagged", target=str(key_id),
        meta={"type": type_, "detail": detail, "user_id": user_id},
    )


async def detect_multi_account(
    db: AsyncSession,
    *,
    key_id: int,
    user_id: int,
    fingerprint: str,
) -> list[int]:
    """Flag when the same device fingerprint appears under other users' keys.

    Returns the list of *other* user ids sharing this fingerprint (the cluster).
    """
    rows = await db.execute(
        select(User.id)
        .join(ApiKey, ApiKey.user_id == User.id)
        .join(Device, Device.key_id == ApiKey.id)
        .where(
            Device.fingerprint == fingerprint,
            Device.status != DeviceStatus.REMOVED,
            User.id != user_id,
        )
        .distinct()
    )
    others = [r[0] for r in rows.all()]
    if others:
        await flag_key(
            db,
            key_id=key_id,
            user_id=user_id,
            type_=AbuseType.MULTI_ACCOUNT,
            detail=(
                f"fingerprint {fingerprint[:16]}… shared with users {others}"
            ),
        )
    return others


async def link_payer_fingerprint(
    db: AsyncSession,
    *,
    user_id: int,
    payer_fingerprint: str,
) -> list[int]:
    """Detect the same payer identity used across different accounts.

    Called from the payment webhook (Phase 6). Returns other user ids that paid
    with the same payer fingerprint; flags those users' active keys if any.
    """
    rows = await db.execute(
        select(Payment.user_id)
        .where(Payment.payer_fingerprint == payer_fingerprint, Payment.user_id != user_id)
        .distinct()
    )
    others = [r[0] for r in rows.all()]
    if others:
        key = await db.scalar(select(ApiKey).where(ApiKey.user_id == user_id))
        await flag_key(
            db,
            key_id=key.id if key else None,
            user_id=user_id,
            type_=AbuseType.MULTI_ACCOUNT,
            detail=f"payer fingerprint reused across users {others}",
        )
    return others
