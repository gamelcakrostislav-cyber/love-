"""Admin-editable bot copy / branding (key → value).

Backs the runtime-editable welcome message, /start banner, and the
'What can this bot do?' description / about text, so admins can rebrand the bot
with commands instead of code. `apply_profile` pushes the description/about to
Telegram (best-effort) on startup and whenever an admin edits them.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bot_content import BotContent
from app.services.audit import record_audit

log = get_logger("bot-content")

# Editable keys → (human label, max length enforced by the admin command).
# Telegram caps: description ≤ 512, short description (about) ≤ 120.
FIELDS: dict[str, tuple[str, int]] = {
    "welcome": ("the /start welcome message (HTML allowed)", 1024),
    "banner": ("the /start banner photo (a Telegram file id)", 256),
    "description": ("the 'What can this bot do?' text (pre-start screen)", 512),
    "about": ("the short bio on the bot's profile", 120),
}


async def get(db: AsyncSession, key: str) -> str | None:
    row = await db.get(BotContent, key)
    return row.value if row else None


async def all_content(db: AsyncSession) -> dict[str, str]:
    rows = await db.scalars(select(BotContent))
    return {r.key: r.value for r in rows}


async def set_value(db: AsyncSession, key: str, value: str, *, actor: str = "admin") -> None:
    row = await db.get(BotContent, key)
    if row is None:
        db.add(BotContent(key=key, value=value))
    else:
        row.value = value
    await record_audit(db, actor=actor, action="bot_content_set", target=key,
                       meta={"len": len(value)})
    await db.flush()


async def apply_profile(bot, db: AsyncSession) -> None:
    """Push the editable description/about to Telegram. Best-effort: a Telegram
    error (or unset values) never breaks startup or the admin command."""
    description = await get(db, "description")
    about = await get(db, "about")
    try:
        if description:
            await bot.set_my_description(description=description[:512])
        if about:
            await bot.set_my_short_description(short_description=about[:120])
    except Exception as exc:  # noqa: BLE001 - profile copy is cosmetic
        log.warning("could not apply bot profile: %s", exc)
