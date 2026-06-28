"""Exclusive subscriber group — gate a private Telegram group on a live sub.

A worker sweep keeps the group's membership in lockstep with subscriptions:
  - every active subscriber who hasn't been invited yet gets a fresh, one-time
    invite link DM'd to them (member_limit=1, so the link can't be shared);
  - every member whose subscription has lapsed is removed (ban → unban, so they
    can rejoin with a new link if they renew).

`user.club_member` tracks who we've granted access to, so renewals don't re-spam
links and a single transient Bot serves the whole sweep. Decoupling this from the
payment path means it's robust to a missed grant and uniformly enforces expiry.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import i18n
from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import SubscriptionStatus
from app.models.subscription import Subscription
from app.models.user import User
from app.services.audit import record_audit

log = get_logger("club")


def is_enabled() -> bool:
    return bool(
        settings.bot_token and settings.bot_token != "CHANGE_ME" and settings.client_group_id
    )


def _active_sub(now: datetime):
    return (
        exists()
        .where(
            Subscription.user_id == User.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at > now,
        )
    )


async def to_invite(db: AsyncSession, now: datetime | None = None) -> list[User]:
    """Active subscribers who haven't been invited to the group yet."""
    now = now or datetime.now(UTC)
    return list(await db.scalars(
        select(User).where(User.club_member.is_(False), _active_sub(now))))


async def to_remove(db: AsyncSession, now: datetime | None = None) -> list[User]:
    """Members whose subscription has lapsed."""
    now = now or datetime.now(UTC)
    return list(await db.scalars(
        select(User).where(User.club_member.is_(True), ~_active_sub(now))))


@asynccontextmanager
async def _bot():
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        yield bot
    finally:
        await bot.session.close()


async def _one_time_link(bot: Bot) -> str | None:
    try:
        kwargs: dict = {"chat_id": settings.client_group_id, "member_limit": 1, "name": "subscriber"}
        if settings.client_group_invite_ttl > 0:
            kwargs["expire_date"] = int(datetime.now(UTC).timestamp()) + settings.client_group_invite_ttl
        link = await bot.create_chat_invite_link(**kwargs)
        return link.invite_link
    except Exception as exc:  # noqa: BLE001 - never let one bad call break the sweep
        log.warning("create_chat_invite_link failed: %s", exc)
        return None


async def _revoke(bot: Bot, telegram_id: int) -> bool:
    # Ban then immediately unban: removes them now, but lets them rejoin (with a
    # new one-time link) if they resubscribe.
    try:
        await bot.ban_chat_member(settings.client_group_id, telegram_id)
        await bot.unban_chat_member(settings.client_group_id, telegram_id, only_if_banned=True)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("revoke club access for %s failed: %s", telegram_id, exc)
        return False


async def sweep(db: AsyncSession) -> tuple[int, int]:
    """Invite new active subscribers, remove lapsed ones. Returns (invited, removed)."""
    if not is_enabled():
        return (0, 0)
    now = datetime.now(UTC)
    invite_users = await to_invite(db, now)
    remove_users = await to_remove(db, now)
    if not invite_users and not remove_users:
        return (0, 0)

    invited = removed = 0
    async with _bot() as bot:
        for user in invite_users:
            link = await _one_time_link(bot)
            if not link:
                continue
            lang = i18n.normalize(user.language)
            try:
                await bot.send_message(user.telegram_id, i18n.t(lang, "club_invite", link=link))
            except Exception as exc:  # noqa: BLE001 - a blocked user must not stop the rest
                log.warning("club invite DM to %s failed: %s", user.telegram_id, exc)
                continue
            user.club_member = True
            invited += 1
            await record_audit(db, actor="system", action="club_invited", target=str(user.id))

        for user in remove_users:
            if not await _revoke(bot, user.telegram_id):
                continue
            user.club_member = False
            removed += 1
            await record_audit(db, actor="system", action="club_removed", target=str(user.id))
            try:
                await bot.send_message(
                    user.telegram_id, i18n.t(i18n.normalize(user.language), "club_removed"))
            except Exception:  # noqa: BLE001 - the removal already happened; DM is a courtesy
                pass

    await db.flush()
    return (invited, removed)
