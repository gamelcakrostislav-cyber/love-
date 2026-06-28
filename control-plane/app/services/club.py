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

import asyncio
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

# Process at most this many users per sweep so a large backlog (e.g. on first
# enable) drains gradually instead of bursting into Telegram's rate limits, and
# pace the Telegram calls within a sweep.
_SWEEP_LIMIT = 25
_PACE_SECONDS = 0.2


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


async def to_invite(
    db: AsyncSession, now: datetime | None = None, *, limit: int = _SWEEP_LIMIT
) -> list[User]:
    """Active subscribers who haven't been invited to the group yet."""
    now = now or datetime.now(UTC)
    return list(await db.scalars(
        select(User).where(User.club_member.is_(False), _active_sub(now)).limit(limit)))


async def to_remove(
    db: AsyncSession, now: datetime | None = None, *, limit: int = _SWEEP_LIMIT
) -> list[User]:
    """Members whose subscription has lapsed."""
    now = now or datetime.now(UTC)
    return list(await db.scalars(
        select(User).where(User.club_member.is_(True), ~_active_sub(now)).limit(limit)))


async def _has_active_sub(db: AsyncSession, user_id: int, now: datetime) -> bool:
    """Per-user re-check, used right before an irreversible invite/kick to avoid
    acting on a stale snapshot (a user who renewed/lapsed mid-sweep)."""
    return await db.scalar(
        select(Subscription.id).where(
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at > now,
        ).limit(1)
    ) is not None


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


async def _ban(bot: Bot, telegram_id: int) -> bool:
    try:
        await bot.ban_chat_member(settings.client_group_id, telegram_id)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ban %s from club failed: %s", telegram_id, exc)
        return False


async def _unban(bot: Bot, telegram_id: int) -> None:
    # Idempotent (only_if_banned=True is a no-op when not banned), so it's always
    # safe to run — both to let a removed user rejoin and to clear a stale ban
    # before a re-invite. Best-effort.
    try:
        await bot.unban_chat_member(settings.client_group_id, telegram_id, only_if_banned=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("unban %s from club failed: %s", telegram_id, exc)


async def _revoke_link(bot: Bot, link: str) -> None:
    try:
        await bot.revoke_chat_invite_link(settings.client_group_id, link)
    except Exception:  # noqa: BLE001 - tidy-up only
        pass


async def sweep(db: AsyncSession) -> tuple[int, int]:
    """Invite new active subscribers, remove lapsed ones. Returns (invited, removed).

    Each membership change is committed per-user right after its irreversible
    Telegram action, so a later failure can never roll a flag back while the group
    change persists (no re-invite spam). Removal flips the flag the moment the ban
    lands — independent of the follow-up unban — so a partial failure can't lock a
    renewing customer out."""
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
            if not await _has_active_sub(db, user.id, now):
                continue  # renewed-then-lapsed in the snapshot window — skip
            await _unban(bot, user.telegram_id)  # clear any stale ban so the link works
            link = await _one_time_link(bot)
            if not link:
                continue  # couldn't mint a link → retry next sweep (nothing committed)
            lang = i18n.normalize(user.language)
            try:
                await bot.send_message(user.telegram_id, i18n.t(lang, "club_invite", link=link))
            except Exception as exc:  # noqa: BLE001 - e.g. the user blocked the bot
                log.warning("club invite DM to %s failed: %s", user.telegram_id, exc)
                await _revoke_link(bot, link)  # don't leave an orphan one-time link
            # Mark invited regardless of DM delivery so we never re-mint a link.
            user.club_member = True
            await record_audit(db, actor="system", action="club_invited", target=str(user.id))
            await db.commit()
            invited += 1
            await asyncio.sleep(_PACE_SECONDS)

        for user in remove_users:
            if await _has_active_sub(db, user.id, now):
                continue  # renewed mid-sweep — don't kick a paying customer
            if not await _ban(bot, user.telegram_id):
                continue  # ban failed → retry next sweep (flag still set)
            # Ban landed → they're out. Flip the flag now, independent of the unban.
            user.club_member = False
            await record_audit(db, actor="system", action="club_removed", target=str(user.id))
            await db.commit()
            removed += 1
            await _unban(bot, user.telegram_id)  # idempotent → lets a renewal rejoin later
            try:
                await bot.send_message(
                    user.telegram_id, i18n.t(i18n.normalize(user.language), "club_removed"))
            except Exception:  # noqa: BLE001 - the removal already happened; DM is a courtesy
                pass
            await asyncio.sleep(_PACE_SECONDS)

    return (invited, removed)
