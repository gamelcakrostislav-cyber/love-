"""User provisioning shared by the bot and the payment webhook."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_by_telegram_id(db: AsyncSession, telegram_id: int) -> User | None:
    return await db.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_or_create(
    db: AsyncSession, *, telegram_id: int, username: str | None
) -> tuple[User, bool]:
    """Return (user, created). Keeps username fresh on subsequent calls."""
    user = await get_by_telegram_id(db, telegram_id)
    if user is not None:
        if username and user.username != username:
            user.username = username
        return user, False
    user = User(telegram_id=telegram_id, username=username)
    db.add(user)
    await db.flush()
    return user, True
