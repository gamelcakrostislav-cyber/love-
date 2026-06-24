"""Expiry reminders — DM users before their subscription lapses (localized).

A worker sweep finds active subscriptions falling into a "days-left band" and
sends one nudge per band, deduped by a Redis marker so a user is never spammed.
Bands are non-overlapping: with EXPIRY_REMINDER_DAYS="3,1" a sub is reminded once
when it enters the 3-day band (1 < days_left ≤ 3) and once at the 1-day band
(0 < days_left ≤ 1). Read-only against the domain; it only sends messages.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import i18n
from app.core import redis_keys
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.models.enums import SubscriptionStatus
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.bot import notify

log = get_logger("reminders")


def parse_days(raw: str) -> list[int]:
    """Parse "3,1" → [3, 1] (positive, unique, sorted high→low)."""
    out: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            out.add(int(part))
    return sorted(out, reverse=True)


def bands(days: list[int]) -> list[tuple[int, int]]:
    """Turn thresholds into non-overlapping (high, low) day bands.

    [3, 1] → [(3, 1), (1, 0)] meaning: remind when low < days_left ≤ high.
    """
    desc = sorted(set(days), reverse=True)
    return [(d, desc[i + 1] if i + 1 < len(desc) else 0) for i, d in enumerate(desc)]


def is_enabled() -> bool:
    return bool(settings.expiry_reminders_enabled and parse_days(settings.expiry_reminder_days))


async def sweep(db: AsyncSession) -> int:
    """Send any due expiry reminders. Returns the number of messages sent."""
    if not is_enabled():
        return 0
    now = datetime.now(UTC)
    sent = 0
    for high, low in bands(parse_days(settings.expiry_reminder_days)):
        lo, hi = now + timedelta(days=low), now + timedelta(days=high)
        rows = (await db.execute(
            select(Subscription.id, Subscription.expires_at, Plan.name,
                   User.telegram_id, User.language)
            .join(Plan, Plan.id == Subscription.plan_id)
            .join(User, User.id == Subscription.user_id)
            .where(Subscription.status == SubscriptionStatus.ACTIVE,
                   Subscription.expires_at > lo, Subscription.expires_at <= hi)
        )).all()
        for sub_id, expires_at, plan_name, telegram_id, language in rows:
            # SET NX is both the dedup check and the marker (single worker, so no
            # race). TTL outlives the band so a renewed sub can remind again later.
            marker = redis_keys.expiry_reminder(sub_id, high)
            got = await redis_client.set(marker, "1", nx=True, ex=(high + 2) * 86400)
            if not got:
                continue
            days_left = max(1, (expires_at - now).days)
            text = i18n.t(i18n.normalize(language), "reminder_expiring",
                          plan=plan_name, days=days_left, date=f"{expires_at:%Y-%m-%d}")
            try:
                await notify.send_message(telegram_id, text)
                sent += 1
            except Exception as exc:  # noqa: BLE001 - one bad DM must not stop the sweep
                log.warning("reminder DM to %s failed: %s", telegram_id, exc)
    return sent
