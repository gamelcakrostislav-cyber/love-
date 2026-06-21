"""POST /auth/session — exchange a long-lived API key for a short-lived,
device-bound session token. This is the single chokepoint where key sharing and
abuse are detected."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.deps import DbDep, client_ip
from app.gateway.schemas import SessionRequest, SessionResponse
from app.services import licensing
from app.services.errors import LicensingError

router = APIRouter(tags=["auth"])


@router.post("/auth/session", response_model=SessionResponse)
async def create_session(
    payload: SessionRequest,
    request: Request,
    db: AsyncSession = DbDep,
) -> SessionResponse:
    try:
        result = await licensing.create_session(
            db,
            raw_key=payload.api_key,
            fingerprint=payload.device_fingerprint,
            ip=client_ip(request),
            context=payload.context,
        )
    except LicensingError:
        # Persist the audit/abuse/cooldown trail accumulated before rejection
        # (e.g. a new device parked in cooldown), then surface the error.
        await db.commit()
        raise
    await db.commit()

    ent = result.entitlement
    return SessionResponse(
        token=result.token,
        session_id=result.session_id,
        expires_at=result.expires_at,
        plan=ent.plan_name,
        rate_limit_per_min=ent.rate_limit_per_min,
        max_profitability=ent.max_profitability,
        evicted_sessions=len(result.evicted_sessions),
    )
