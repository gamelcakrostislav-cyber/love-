"""Client push & automation — onboarding drip, weekly digest, segmented pushes.

All marketing sends respect the user's `notifications_opt_out` flag (transactional
messages elsewhere ignore it). Worker-driven, best-effort, deduped via Redis so
nobody is spammed. Never raises into the worker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import i18n, notify
from app.core import redis_keys
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.models.enums import SubscriptionStatus
from app.models.plan import Plan
from app.models.referral import Commission
from app.models.subscription import Subscription
from app.models.user import User
from app.services.reminders import _plans_kb, parse_days

log = get_logger("notifications")

_DRIP_WINDOW_DAYS = 2     # width of each day-band so old users aren't re-nudged
_DIGEST_TTL = 7 * 86400   # one digest per user per 7 days
_DRIP_TTL = 30 * 86400

# Admin /push segments -> human description.
SEGMENTS = ("all", "active", "trial", "inactive")


def drip_enabled() -> bool:
    return bool(settings.onboarding_drip_enabled and parse_days(settings.onboarding_drip_days))


def digest_enabled() -> bool:
    return bool(settings.weekly_digest_enabled)


async def _has_active_sub(db, user_id: int, now: datetime) -> bool:
    return bool(await db.scalar(
        select(func.count()).select_from(Subscription)
        .where(Subscription.user_id == user_id,
               Subscription.status == SubscriptionStatus.ACTIVE,
               Subscription.expires_at > now)))


async def drip_sweep(db: AsyncSession) -> int:
    """Nudge not-yet-subscribed users at each onboarding day-band. Returns count."""
    if not drip_enabled():
        return 0
    now = datetime.now(UTC)
    sent = 0
    for day in parse_days(settings.onboarding_drip_days):
        lo = now - timedelta(days=day + _DRIP_WINDOW_DAYS)
        hi = now - timedelta(days=day)
        users = list(await db.scalars(
            select(User).where(User.created_at > lo, User.created_at <= hi,
                               User.notifications_opt_out.is_(False))))
        for u in users:
            if await _has_active_sub(db, u.id, now):
                continue
            if not await redis_client.set(redis_keys.drip(u.id, day), "1", nx=True, ex=_DRIP_TTL):
                continue
            lang = i18n.normalize(u.language)
            try:
                await notify.send_message(u.telegram_id, i18n.t(lang, "drip_nudge"),
                                          reply_markup=_plans_kb(lang))
                sent += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("drip DM to %s failed: %s", u.telegram_id, exc)
    return sent


async def digest_sweep(db: AsyncSession) -> int:
    """Weekly summary DM to active subscribers (once per 7 days each)."""
    if not digest_enabled():
        return 0
    now = datetime.now(UTC)
    rows = (await db.execute(
        select(User, Plan.name, Subscription.expires_at)
        .join(Subscription, Subscription.user_id == User.id)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(Subscription.status == SubscriptionStatus.ACTIVE,
               Subscription.expires_at > now, User.notifications_opt_out.is_(False))
        .order_by(Subscription.expires_at.desc()))).all()
    seen: set[int] = set()
    sent = 0
    for user, plan_name, expires_at in rows:
        if user.id in seen:  # one digest per user even with multiple subs
            continue
        seen.add(user.id)
        if not await redis_client.set(redis_keys.digest(user.id), "1", nx=True, ex=_DIGEST_TTL):
            continue
        earned = await db.scalar(
            select(func.coalesce(func.sum(Commission.amount), 0))
            .where(Commission.referrer_user_id == user.id)) or 0
        days = max(0, (expires_at - now).days)
        lang = i18n.normalize(user.language)
        try:
            await notify.send_message(user.telegram_id, i18n.t(
                lang, "digest", plan=plan_name, days=days, earned=f"{earned} USD"))
            sent += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("digest DM to %s failed: %s", user.telegram_id, exc)
    return sent


async def segment_telegram_ids(db: AsyncSession, segment: str) -> list[int]:
    """Telegram ids for an admin /push segment (always excludes opted-out users)."""
    now = datetime.now(UTC)
    active_sub = (
        select(Subscription.user_id)
        .where(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at > now)
        .scalar_subquery())
    q = select(User.telegram_id).where(User.notifications_opt_out.is_(False))
    if segment == "active":
        q = q.where(User.id.in_(active_sub))
    elif segment == "inactive":
        q = q.where(User.id.not_in(active_sub))
    elif segment == "trial":
        trial_sub = (
            select(Subscription.user_id).join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.status == SubscriptionStatus.ACTIVE,
                   Subscription.expires_at > now, Plan.is_trial.is_(True))
            .scalar_subquery())
        q = q.where(User.id.in_(trial_sub))
    return list(await db.scalars(q))
