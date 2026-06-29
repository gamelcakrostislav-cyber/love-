"""POST /internal/announce — server-to-server hook to post into the subscriber group.

Lets the arbitrage product (or any trusted backend) push a message — e.g. a fresh
opportunity — into the members group without a human running /announce. Guarded by
a shared secret (INTERNAL_API_TOKEN) compared in constant time; the endpoint is
disabled entirely until that token is set, so it can never be hit anonymously.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.services import club

router = APIRouter(prefix="/internal", tags=["internal"])
log = get_logger("internal")


class AnnounceIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)  # Telegram's hard message cap
    topic_id: int | None = None
    pin: bool = False


def _authorize(authorization: str | None) -> None:
    token = settings.internal_api_token
    if not token:  # fail closed: the feature is off until a secret is configured
        raise HTTPException(status_code=503, detail="internal_api_disabled")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    presented = authorization[7:].strip()
    if not hmac.compare_digest(presented, token):
        raise HTTPException(status_code=401, detail="bad_token")


@router.post("/announce")
async def announce(body: AnnounceIn, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    if not club.is_enabled():
        raise HTTPException(status_code=503, detail="subscriber_group_not_configured")
    try:
        message_id = await club.announce(body.text, topic_id=body.topic_id, pin=body.pin)
    except Exception as exc:  # noqa: BLE001 - Telegram/config error → clean 502
        log.warning("internal announce failed: %s", exc)
        raise HTTPException(status_code=502, detail="post_failed") from exc
    return {"ok": True, "message_id": message_id}
