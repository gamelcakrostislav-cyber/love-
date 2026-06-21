"""Risk signals for session issuance.

Phase 3 records the session IP trail in Redis so the data is available. Phase 4
adds impossible-travel / velocity scoring and the `flagged` state transition on
top of this trail.
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys
from app.core.redis import redis_client

_IP_TRAIL_MAX = 20
_IP_TRAIL_TTL = 7 * 24 * 3600  # keep a week of IP history per key


async def evaluate_session(
    db: AsyncSession,  # noqa: ARG001 - used by Phase 4 flagging
    *,
    key_id: int,
    user_id: int,  # noqa: ARG001 - used by Phase 4 flagging
    ip: str | None,
) -> None:
    """Record the session IP; full velocity scoring lands in Phase 4."""
    if not ip:
        return
    trail = redis_keys.key_ips(key_id)
    pipe = redis_client.pipeline()
    pipe.lpush(trail, f"{time.time()}|{ip}")
    pipe.ltrim(trail, 0, _IP_TRAIL_MAX - 1)
    pipe.expire(trail, _IP_TRAIL_TTL)
    await pipe.execute()
