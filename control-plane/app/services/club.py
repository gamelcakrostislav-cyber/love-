"""Exclusive subscriber group — gate a private Telegram group on a live sub.

Membership truth is the actual group roster, kept in lockstep with subscriptions
by two cooperating parts:

  - the worker SWEEP (this module's `sweep`) DMs every active subscriber who
    isn't in the group a *join-request* invite link, and removes (bans) members
    whose subscription has lapsed;
  - the bot's join/membership HANDLERS (app/bot/handlers/club_join.py) approve a
    join request only when the requester has an active subscription, and flip
    `user.club_member` on the real `chat_member` join/leave event.

Why join-request links and not `member_limit=1` one-time links: Telegram's
`member_limit` caps how MANY people use a link, not WHO — a forwarded/leaked link
would let the first stranger into the paid group. `creates_join_request=True`
makes the bot vet every joiner, so a leaked link is useless to a non-subscriber.

`user.club_member` therefore means "currently in the group" (set by the join/leave
event), NOT "we sent a link". The sweep never sets it; a Redis cooldown marker
(`redis_keys.club_invited`) tracks "invite sent, awaiting join" so we don't re-DM
the link every minute, and its expiry gives a bounded retry if the link never
landed. Decoupling all this from the payment path means it self-corrects after a
missed grant and uniformly enforces expiry.
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
from app.core import redis_keys
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.models.enums import SubscriptionStatus
from app.models.subscription import Subscription
from app.models.user import User
from app.services import users
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


async def preflight() -> str:
    """One-shot operator config check: is the bot an admin in a supergroup at
    CLIENT_GROUP_ID? Returns a short human verdict for the worker boot log and
    the /clubstatus command, so a misconfigured group fails loudly instead of
    silently doing nothing."""
    if not is_enabled():
        return "disabled (set CLIENT_GROUP_ID + a real BOT_TOKEN to enable)"
    async with _bot() as bot:
        return await _check_config(bot)


async def _check_config(bot: Bot) -> str:
    gid = settings.client_group_id
    try:
        chat = await bot.get_chat(gid)
    except Exception as exc:  # noqa: BLE001
        return (f"MISCONFIGURED: can't read chat {gid} ({exc}). Check the id (it must be the "
                "supergroup's -100… id) and that the bot is a member of the group.")
    if chat.type not in ("supergroup", "channel"):
        return (f"MISCONFIGURED: chat {gid} is a '{chat.type}', not a supergroup. Join requests "
                "need a supergroup — make the group public once to convert it, then use the new "
                "-100… id.")
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(gid, me.id)
    except Exception as exc:  # noqa: BLE001
        return f"MISCONFIGURED: can't read the bot's own membership in {gid} ({exc})."
    if member.status not in ("administrator", "creator"):
        return (f"MISCONFIGURED: the bot is '{member.status}', not an admin in {gid}. Promote it "
                "to admin with Invite-via-link + Ban-users rights.")
    missing = []
    if getattr(member, "can_invite_users", None) is False:
        missing.append("Invite via link")
    if getattr(member, "can_restrict_members", None) is False:
        missing.append("Ban users")
    if missing:
        return f"WARNING: bot is admin but missing rights: {', '.join(missing)}."
    return f"OK: admin in supergroup '{getattr(chat, 'title', '?')}' ({gid})"


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
    """Active subscribers not currently in the group."""
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


async def admit_join_request(db: AsyncSession, telegram_id: int, now: datetime | None = None) -> bool:
    """Whether this Telegram user should be let into the group: they must map to a
    known user with an active subscription. This is the gate that makes a leaked
    join-request link worthless to a non-subscriber."""
    now = now or datetime.now(UTC)
    user = await users.get_by_telegram_id(db, telegram_id)
    if user is None:
        return False
    return await _has_active_sub(db, user.id, now)


async def set_membership(db: AsyncSession, telegram_id: int, *, joined: bool) -> None:
    """Record the real group-membership state from a join/leave event. Idempotent:
    only writes (and audits) on an actual change, so duplicate events and the
    sweep's own removal write don't double-log. Clears the invite cooldown on join
    so a user who later re-lapses and renews is re-invited promptly."""
    user = await users.get_by_telegram_id(db, telegram_id)
    if user is None:
        return
    if joined:
        await redis_client.delete(redis_keys.club_invited(user.id))
    if user.club_member == joined:
        return  # already in the desired state — nothing to write/audit
    user.club_member = joined
    await record_audit(
        db, actor="system", action="club_joined" if joined else "club_left", target=str(user.id))
    await db.commit()


async def _recently_invited(user_id: int) -> bool:
    return bool(await redis_client.exists(redis_keys.club_invited(user_id)))


async def _mark_invited(user_id: int) -> None:
    await redis_client.set(
        redis_keys.club_invited(user_id), "1", ex=max(60, settings.client_group_invite_cooldown))


@asynccontextmanager
async def _bot():
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        yield bot
    finally:
        await bot.session.close()


async def _join_request_link(bot: Bot) -> str | None:
    # creates_join_request=True (mutually exclusive with member_limit): anyone can
    # tap the link, but the bot's chat_join_request handler vets each joiner.
    try:
        kwargs: dict = {
            "chat_id": settings.client_group_id,
            "creates_join_request": True,
            "name": "subscriber",
        }
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

    Invite path sets a Redis cooldown (not club_member) so a sent-but-not-yet-joined
    or undelivered link isn't re-DM'd every minute; club_member flips to True only on
    the real join event. Removal flips club_member=False the moment the ban lands —
    independent of the follow-up unban — so a partial failure can't lock a renewing
    customer out."""
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
            if await _recently_invited(user.id):
                continue  # link sent recently — wait for them to join or for cooldown
            if not await _has_active_sub(db, user.id, now):
                continue  # renewed-then-lapsed in the snapshot window — skip
            await _unban(bot, user.telegram_id)  # clear any stale ban so they can request to join
            link = await _join_request_link(bot)
            if not link:
                continue  # couldn't mint a link → retry next sweep (no cooldown set)
            lang = i18n.normalize(user.language)
            try:
                await bot.send_message(user.telegram_id, i18n.t(lang, "club_invite", link=link))
            except Exception as exc:  # noqa: BLE001 - e.g. the user blocked the bot
                log.warning("club invite DM to %s failed: %s", user.telegram_id, exc)
                await _revoke_link(bot, link)  # don't leave an orphan link
            # Cooldown regardless of delivery: a blocked user is retried once per
            # cooldown, not every sweep. club_member stays False until they join.
            await _mark_invited(user.id)
            await record_audit(db, actor="system", action="club_invited", target=str(user.id))
            await db.commit()  # persist the audit row (symmetric with the remove path)
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
