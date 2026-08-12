"""Growth / affiliate engine — referral leaderboard, ranks, milestone rewards.

Read-only against the domain plus best-effort milestone DMs from the worker.
Used by the customer-facing /referrals and /leaderboard, and a worker sweep that
congratulates referrers as they cross paid-referral milestones.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import i18n, notify
from app.core import redis_keys
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.models.enums import ReferralStatus
from app.models.referral import Commission, Referral
from app.models.user import User

log = get_logger("growth")

MILESTONES = (1, 5, 10, 25, 50, 100)
_MILESTONE_TTL = 400 * 86400


def _mask(username: str | None) -> str:
    """Privacy-preserving handle for the public leaderboard."""
    return f"@{username[:3]}…" if username else "anonymous"


async def leaderboard(db: AsyncSession, limit: int = 10) -> list[tuple[int, str, Decimal, int]]:
    """Top referrers by total commission earned: (rank, masked_handle, earned, count)."""
    rows = (await db.execute(
        select(User.username, func.sum(Commission.amount), func.count())
        .join(Commission, Commission.referrer_user_id == User.id)
        .group_by(User.id, User.username)
        .order_by(func.sum(Commission.amount).desc())
        .limit(limit))).all()
    return [(i + 1, _mask(uname), total, cnt) for i, (uname, total, cnt) in enumerate(rows)]


async def user_rank(db: AsyncSession, user_id: int) -> tuple[int, Decimal, int] | None:
    """The user's (rank, earned, paid_count), or None if they've earned nothing."""
    total, cnt = (await db.execute(
        select(func.coalesce(func.sum(Commission.amount), 0), func.count())
        .where(Commission.referrer_user_id == user_id))).first()
    if not cnt:
        return None
    higher = await db.scalar(
        select(func.count()).select_from(
            select(Commission.referrer_user_id)
            .group_by(Commission.referrer_user_id)
            .having(func.sum(Commission.amount) > total).subquery()))
    return (higher + 1, total, cnt)


async def pending_count(db: AsyncSession, user_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(Referral)
        .where(Referral.referrer_user_id == user_id,
               Referral.status == ReferralStatus.PENDING)) or 0


async def milestone_sweep(db: AsyncSession) -> int:
    """Congratulate referrers who crossed a new paid-referral milestone. Returns count."""
    rows = (await db.execute(
        select(Referral.referrer_user_id, func.count())
        .where(Referral.status == ReferralStatus.QUALIFIED)
        .group_by(Referral.referrer_user_id))).all()
    sent = 0
    for referrer_id, count in rows:
        reached = max((m for m in MILESTONES if count >= m), default=0)
        if not reached:
            continue
        key = redis_keys.milestone(referrer_id)
        last = await redis_client.get(key)
        if reached <= (int(last) if last else 0):
            continue
        await redis_client.set(key, str(reached), ex=_MILESTONE_TTL)
        user = await db.get(User, referrer_id)
        if user is None or user.notifications_opt_out:
            continue
        lang = i18n.normalize(user.language)
        try:
            await notify.send_message(user.telegram_id, i18n.t(lang, "milestone", count=reached))
            sent += 1
        except Exception as exc:  # noqa: BLE001 - never crash the worker on one DM
            log.warning("milestone DM to %s failed: %s", user.telegram_id, exc)
    return sent
