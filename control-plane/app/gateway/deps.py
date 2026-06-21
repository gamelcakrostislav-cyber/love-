"""FastAPI dependencies: DB session and protected-endpoint session validation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.db import SessionFactory
from app.services import session_store
from app.services.errors import SessionInvalid


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


@dataclass
class SessionContext:
    key_id: int
    session_id: str
    device_fp_digest: str
    ip: str | None


def client_ip(request: Request) -> str | None:
    # Honor X-Forwarded-For when present (set by the edge/proxy), else peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def require_session(
    request: Request,
    authorization: str | None = Header(default=None),
    x_device_fingerprint: str | None = Header(default=None),
) -> SessionContext:
    """Validate the bearer JWT, its device binding, and the live Redis session.

    The raw API key is NEVER accepted here — only a short-lived, device-bound
    session token, which must still be active in Redis.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise SessionInvalid("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()

    try:
        claims = security.decode_session_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise SessionInvalid("token expired") from exc
    except jwt.PyJWTError as exc:
        raise SessionInvalid("invalid token") from exc

    session_id = claims.get("sid")
    key_id = int(claims.get("sub", 0))
    dfp = claims.get("dfp", "")
    if not session_id or not key_id:
        raise SessionInvalid("malformed token")

    # Token is bound to a device: the caller must present the same fingerprint.
    if not x_device_fingerprint:
        raise SessionInvalid("missing device fingerprint")
    if security.fingerprint_digest(x_device_fingerprint) != dfp:
        raise SessionInvalid("device mismatch")

    # The session must still be live in Redis (revocation propagates here).
    live = await session_store.get(session_id)
    if live is None or int(live.get("key_id", 0)) != key_id:
        raise SessionInvalid("session not active")

    return SessionContext(
        key_id=key_id,
        session_id=session_id,
        device_fp_digest=dfp,
        ip=client_ip(request),
    )


DbDep = Depends(get_db)
SessionDep = Depends(require_session)
