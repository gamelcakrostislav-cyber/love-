"""Risk signals for session issuance: IP velocity / impossible travel.

Each session's IP+time is recorded in Redis. If consecutive sessions for the
same key imply a ground speed above the configured threshold (faster than a
plane), that's physically impossible for one human => flag the key (not a ban).
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys
from app.core.config import settings
from app.core.redis import redis_client
from app.models.enums import AbuseType
from app.services import abuse, geoip

_IP_TRAIL_MAX = 20
_IP_TRAIL_TTL = 7 * 24 * 3600  # keep a week of IP history per key


async def _last_entry(key_id: int) -> tuple[float, str] | None:
    items = await redis_client.lrange(redis_keys.key_ips(key_id), 0, 0)
    if not items:
        return None
    ts_str, _, ip = items[0].partition("|")
    try:
        return float(ts_str), ip
    except ValueError:
        return None


async def _record(key_id: int, ip: str) -> None:
    trail = redis_keys.key_ips(key_id)
    pipe = redis_client.pipeline()
    pipe.lpush(trail, f"{time.time()}|{ip}")
    pipe.ltrim(trail, 0, _IP_TRAIL_MAX - 1)
    pipe.expire(trail, _IP_TRAIL_TTL)
    await pipe.execute()


async def evaluate_session(
    db: AsyncSession,
    *,
    key_id: int,
    user_id: int,
    ip: str | None,
) -> bool:
    """Record the IP and flag the key on impossible travel. Returns True if flagged."""
    if not ip:
        return False

    flagged = False
    prev = await _last_entry(key_id)
    if prev is not None:
        prev_ts, prev_ip = prev
        if prev_ip and prev_ip != ip:
            here = geoip.resolve(ip)
            there = geoip.resolve(prev_ip)
            dt_hours = max((time.time() - prev_ts) / 3600.0, 1e-6)
            if here and there:
                distance_km = geoip.haversine_km(here, there)
                speed_kmh = distance_km / dt_hours
                if speed_kmh > settings.impossible_travel_max_kmh:
                    await abuse.flag_key(
                        db,
                        key_id=key_id,
                        user_id=user_id,
                        type_=AbuseType.IMPOSSIBLE_TRAVEL,
                        detail=(
                            f"{prev_ip} ({there.country}) -> {ip} ({here.country}): "
                            f"{distance_km:.0f} km in {dt_hours * 60:.1f} min "
                            f"= {speed_kmh:.0f} km/h"
                        ),
                    )
                    flagged = True

    await _record(key_id, ip)
    return flagged
