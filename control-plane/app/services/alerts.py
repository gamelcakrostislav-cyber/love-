"""Admin alerts — DM the owners when new anti-abuse events appear.

A worker sweep tracks the highest AbuseEvent id already alerted (a Redis
watermark) and DMs the admins a digest of anything newer, so the owner hears
about shared-key / multi-account / impossible-travel flags without watching the
dashboard. Best-effort: never raises into the worker.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import notify
from app.core import redis_keys
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.models.abuse_event import AbuseEvent

log = get_logger("alerts")

_MAX_PER_DIGEST = 50


def is_enabled() -> bool:
    return bool(settings.admin_ids)


async def abuse_sweep(db: AsyncSession) -> int:
    """DM admins about AbuseEvents newer than the last alerted id. Returns count."""
    if not is_enabled():
        return 0
    raw = await redis_client.get(redis_keys.abuse_alert_watermark())
    watermark = int(raw) if raw else 0
    events = list(await db.scalars(
        select(AbuseEvent).where(AbuseEvent.id > watermark)
        .order_by(AbuseEvent.id).limit(_MAX_PER_DIGEST)))
    if not events:
        return 0
    lines = ["🚨 <b>New anti-abuse events</b>"]
    for e in events:
        detail = f" — {e.detail}" if e.detail else ""
        lines.append(f"• [{e.type}] user={e.user_id} key={e.key_id}{detail}")
    text = "\n".join(lines)
    for admin_id in settings.admin_ids:
        await notify.send_message(admin_id, text)
    await redis_client.set(redis_keys.abuse_alert_watermark(), str(events[-1].id))
    log.info("alerted admins of %d new abuse events", len(events))
    return len(events)
