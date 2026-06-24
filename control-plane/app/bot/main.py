"""Telegram bot entrypoint (aiogram 3.x).

Long-polls Telegram and dispatches to the client command router. Admin commands
are added in Phase 7.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from app.bot import i18n
from app.bot.handlers import admin, client
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

log = get_logger("bot")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    # Admin router first: its IsAdmin filter scopes /stats, /grant, etc.
    dp.include_router(admin.router)
    dp.include_router(client.router)
    return dp


def _commands_for(lang: str) -> list[BotCommand]:
    return [
        BotCommand(command=cmd, description=i18n.command_description(cmd, lang))
        for cmd in i18n.COMMAND_ORDER
    ]


# Admin-only commands, shown in the "/" menu for admin chats (English).
_ADMIN_COMMANDS: list[tuple[str, str]] = [
    ("stats", "Overview stats"),
    ("user", "Look up a user"),
    ("grant", "Grant / extend access"),
    ("revoke", "Revoke access"),
    ("flags", "Flagged keys & abuse"),
    ("unflag", "Clear a flag"),
    ("notion", "Notion CRM status / sync"),
    ("reply", "Reply in a support handoff"),
    ("close", "Close a support handoff"),
    ("admin", "List admin commands"),
]


def _admin_commands() -> list[BotCommand]:
    # Admins keep the client menu (English) plus the admin tools below it.
    base = _commands_for(i18n.DEFAULT_LANG)
    extra = [BotCommand(command=c, description=d) for c, d in _ADMIN_COMMANDS]
    return base + extra


async def _set_commands(bot: Bot) -> None:
    """Register the native "/" command menu, localized per language.

    English is the default scope (shown to everyone); ru/uk/es/fr get a
    localized menu when the user's Telegram client is set to that language.
    Best-effort: a Telegram hiccup here must not stop the bot from polling.
    """
    try:
        await bot.set_my_commands(
            _commands_for(i18n.DEFAULT_LANG), scope=BotCommandScopeDefault()
        )
        for lang in i18n.LANGUAGES:
            if lang == i18n.DEFAULT_LANG:
                continue
            await bot.set_my_commands(
                _commands_for(lang),
                scope=BotCommandScopeDefault(),
                language_code=lang,
            )
        # Per-admin chat scope: admins additionally see the admin tools.
        for admin_id in settings.admin_ids:
            try:
                await bot.set_my_commands(
                    _admin_commands(), scope=BotCommandScopeChat(chat_id=admin_id)
                )
            except Exception as exc:  # noqa: BLE001 - one bad id must not block the rest
                log.warning("could not set admin menu for %s: %s", admin_id, exc)
        log.info(
            "native command menu registered (%d languages, %d admins)",
            len(i18n.LANGUAGES), len(settings.admin_ids),
        )
    except Exception as exc:  # noqa: BLE001 - menu is cosmetic; never block startup
        log.warning("could not set command menu: %s", exc)


async def main() -> None:
    configure_logging()
    if not settings.bot_token or settings.bot_token == "CHANGE_ME":
        log.warning("BOT_TOKEN not set — bot idling (set it in .env to enable)")
        while True:
            await asyncio.sleep(3600)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()
    await _set_commands(bot)
    log.info("bot starting (long polling)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
