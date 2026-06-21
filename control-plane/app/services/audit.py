"""Append-only audit logging and abuse-event recording.

Every grant, revoke, session issue, and flag lands here for dispute resolution.
Helpers flush immediately so the trail survives even if the caller later rolls
back business state.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.abuse_event import AbuseEvent
from app.models.audit_log import AuditLog


async def record_audit(
    db: AsyncSession,
    *,
    actor: str,
    action: str,
    target: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(actor=actor, action=action, target=target, meta=meta or {}))
    await db.flush()


async def record_abuse(
    db: AsyncSession,
    *,
    type_: str,
    user_id: int | None = None,
    key_id: int | None = None,
    detail: str | None = None,
) -> None:
    db.add(AbuseEvent(type=type_, user_id=user_id, key_id=key_id, detail=detail))
    await db.flush()
