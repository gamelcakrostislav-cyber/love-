"""Admin-editable bot content — get/set/all + best-effort profile push."""

from __future__ import annotations

from app.services import bot_content


async def test_set_get_and_update(db):
    assert await bot_content.get(db, "welcome") is None
    await bot_content.set_value(db, "welcome", "Hello <b>world</b>")
    await db.commit()
    assert await bot_content.get(db, "welcome") == "Hello <b>world</b>"
    # overwrite
    await bot_content.set_value(db, "welcome", "Updated")
    await db.commit()
    assert await bot_content.get(db, "welcome") == "Updated"


async def test_all_content(db):
    await bot_content.set_value(db, "welcome", "hi")
    await bot_content.set_value(db, "about", "short bio")
    await db.commit()
    content = await bot_content.all_content(db)
    assert content == {"welcome": "hi", "about": "short bio"}


class _FakeBot:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: dict[str, str] = {}

    async def set_my_description(self, *, description: str) -> None:
        if self.fail:
            raise RuntimeError("telegram down")
        self.calls["description"] = description

    async def set_my_short_description(self, *, short_description: str) -> None:
        if self.fail:
            raise RuntimeError("telegram down")
        self.calls["about"] = short_description


async def test_apply_profile_pushes_description_and_about(db):
    await bot_content.set_value(db, "description", "What this bot does")
    await bot_content.set_value(db, "about", "Fast support")
    await db.commit()
    bot = _FakeBot()
    await bot_content.apply_profile(bot, db)
    assert bot.calls == {"description": "What this bot does", "about": "Fast support"}


async def test_apply_profile_is_best_effort(db):
    # Nothing set → no calls, no error.
    await bot_content.apply_profile(_FakeBot(), db)
    # Telegram failure is swallowed, never raised.
    await bot_content.set_value(db, "description", "x")
    await db.commit()
    await bot_content.apply_profile(_FakeBot(fail=True), db)
