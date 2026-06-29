"""Subscriber-group gatekeeper (aiogram handlers).

Two Telegram events keep `user.club_member` honest for the exclusive group:

  - chat_join_request: someone tapped a join-request invite link. Approve only if
    they have an active subscription, so a forwarded/leaked link is useless to a
    non-subscriber; otherwise decline and (best-effort) tell them why.
  - chat_member: the group roster changed. Mirror the real status into
    user.club_member so the worker sweep acts on truth — a voluntary leave gets
    the user re-invited, a lapse gets them removed, and a user who only ever
    received a link (never joined) is never falsely "removed".
"""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatJoinRequest, ChatMemberUpdated

from app.bot import i18n
from app.core.config import settings
from app.core.db import SessionFactory
from app.core.logging import get_logger
from app.services import club, users

log = get_logger("club-bot")

router = Router(name="club")


def _for_club(chat_id: int) -> bool:
    return club.is_enabled() and chat_id == settings.client_group_id


def _is_in_chat(member) -> bool:
    """Whether a chat_member status means the user is currently in the group."""
    status = member.status
    if status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    ):
        return True
    if status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(member, "is_member", True))  # restricted but still in the chat
    return False  # LEFT / KICKED


@router.chat_join_request()
async def on_join_request(event: ChatJoinRequest, bot: Bot) -> None:
    if not _for_club(event.chat.id):
        return
    tg_id = event.from_user.id
    async with SessionFactory() as db:
        if await club.admit_join_request(db, tg_id):
            try:
                await event.approve()
            except Exception as exc:  # noqa: BLE001 - already gone / approved elsewhere
                log.warning("approve club join for %s failed: %s", tg_id, exc)
                return
            await club.set_membership(db, tg_id, joined=True)
            return
        # Not an active subscriber. Use their chosen language if we know them,
        # else default to English — never guess from the raw device locale.
        known = await users.get_by_telegram_id(db, tg_id)
        lang = i18n.normalize(known.language) if known else i18n.DEFAULT_LANG
    # Decline, then explain (best-effort DM).
    try:
        await event.decline()
    except Exception as exc:  # noqa: BLE001
        log.warning("decline club join for %s failed: %s", tg_id, exc)
    try:
        await bot.send_message(tg_id, i18n.t(lang, "club_declined"))
    except Exception:  # noqa: BLE001 - they may not have started the bot
        pass


@router.chat_member()
async def on_chat_member(event: ChatMemberUpdated) -> None:
    if not _for_club(event.chat.id):
        return
    member = event.new_chat_member
    if member.user.is_bot:
        return  # the bot's own status arrives via my_chat_member, not here
    async with SessionFactory() as db:
        await club.set_membership(db, member.user.id, joined=_is_in_chat(member))
