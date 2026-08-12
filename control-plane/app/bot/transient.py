"""Shared transient Bot construction for out-of-band Telegram calls.

The gateway DM helper (app/bot/notify.py) and the worker's subscriber-group sweep
(app/services/club.py) both need a short-lived Bot to message users without running
the dispatcher. Keep the token + default parse-mode in one place so they can't drift.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import settings


def make_bot() -> Bot:
    return Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


@asynccontextmanager
async def bot_session() -> AsyncIterator[Bot]:
    """A transient Bot whose aiohttp session is always closed."""
    bot = make_bot()
    try:
        yield bot
    finally:
        await bot.session.close()
