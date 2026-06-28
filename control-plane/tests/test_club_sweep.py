"""Drive club.sweep() through every branch with a fake transient Bot.

New model: the sweep DMs a join-request link and sets a Redis cooldown marker; it
never sets club_member (that flips only on the real join/leave event, covered in
test_club_join.py). So the invite-path assertions check the cooldown + the
join-request link, and that club_member stays False.
"""

from __future__ import annotations

import types
from contextlib import asynccontextmanager

from sqlalchemy import select

from app.core import redis_keys
from app.core.config import settings
from app.core.redis import redis_client
from app.models.user import User
from app.services import club
from tests.factories import make_plan, make_subscription, make_user


class FakeBot:
    """Records every Telegram call; per-method ``fail`` flags raise to exercise
    the sweep's failure branches."""

    def __init__(self) -> None:
        self.invite_calls: list[dict] = []
        self.send_calls: list[tuple] = []
        self.ban_calls: list[tuple] = []
        self.unban_calls: list[tuple] = []
        self.revoke_calls: list[tuple] = []
        self.fail_create = False
        self.fail_send = False
        self.fail_ban = False

    async def create_chat_invite_link(self, *, chat_id, creates_join_request=False, name=None, **kw):
        self.invite_calls.append(
            {"chat_id": chat_id, "creates_join_request": creates_join_request, "name": name})
        if self.fail_create:
            raise RuntimeError("mint boom")
        return types.SimpleNamespace(invite_link="https://t.me/+abc")

    async def send_message(self, telegram_id, text):
        self.send_calls.append((telegram_id, text))
        if self.fail_send:
            raise RuntimeError("dm boom")

    async def ban_chat_member(self, chat_id, telegram_id):
        self.ban_calls.append((chat_id, telegram_id))
        if self.fail_ban:
            raise RuntimeError("ban boom")

    async def unban_chat_member(self, chat_id, telegram_id, only_if_banned=False):
        self.unban_calls.append((chat_id, telegram_id, only_if_banned))

    async def revoke_chat_invite_link(self, chat_id, link):
        self.revoke_calls.append((chat_id, link))


def _enable(monkeypatch, bot: FakeBot) -> FakeBot:
    """Turn the club on and swap the transient Bot for ``bot``, no sleeps."""
    monkeypatch.setattr(settings, "bot_token", "123:real")
    monkeypatch.setattr(settings, "client_group_id", -1001234567890)
    monkeypatch.setattr(club, "_PACE_SECONDS", 0)

    @asynccontextmanager
    async def fake_bot_factory():
        yield bot

    monkeypatch.setattr(club, "_bot", fake_bot_factory)
    return bot


async def _club_member(db, telegram_id: int) -> bool:
    return await db.scalar(select(User.club_member).where(User.telegram_id == telegram_id))


async def _invited(user_id: int) -> bool:
    return bool(await redis_client.exists(redis_keys.club_invited(user_id)))


async def test_sweep_disabled_does_nothing(db, monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "CHANGE_ME")
    constructed = False

    @asynccontextmanager
    async def boom_bot():
        nonlocal constructed
        constructed = True
        yield FakeBot()

    monkeypatch.setattr(club, "_bot", boom_bot)
    assert await club.sweep(db) == (0, 0)
    assert constructed is False


async def test_sweep_happy_invite(db, monkeypatch):
    bot = _enable(monkeypatch, FakeBot())
    plan = await make_plan(db)
    user = await make_user(db, telegram_id=9001)
    await make_subscription(db, user=user, plan=plan, days_left=10)
    await db.commit()

    invited, removed = await club.sweep(db)

    assert (invited, removed) == (1, 0)
    # sweep does NOT mark them a member — that waits for the real join event.
    assert await _club_member(db, 9001) is False
    assert await _invited(user.id) is True              # cooldown set so we don't re-DM
    assert len(bot.invite_calls) == 1
    assert bot.invite_calls[0]["creates_join_request"] is True
    assert len(bot.send_calls) == 1
    assert bot.revoke_calls == []


async def test_sweep_invite_dm_fails_still_sets_cooldown(db, monkeypatch):
    bot = FakeBot()
    bot.fail_send = True
    _enable(monkeypatch, bot)
    plan = await make_plan(db)
    user = await make_user(db, telegram_id=9101)
    await make_subscription(db, user=user, plan=plan, days_left=10)
    await db.commit()

    invited, removed = await club.sweep(db)

    assert (invited, removed) == (1, 0)
    assert await _club_member(db, 9101) is False
    assert await _invited(user.id) is True              # cooldown so a blocked user isn't re-DM'd every sweep
    assert len(bot.send_calls) == 1
    assert len(bot.revoke_calls) == 1                   # orphan link revoked


async def test_sweep_link_mint_fails_skips_user(db, monkeypatch):
    bot = FakeBot()
    bot.fail_create = True
    _enable(monkeypatch, bot)
    plan = await make_plan(db)
    user = await make_user(db, telegram_id=9201)
    await make_subscription(db, user=user, plan=plan, days_left=10)
    await db.commit()

    invited, removed = await club.sweep(db)

    assert (invited, removed) == (0, 0)
    assert await _club_member(db, 9201) is False
    assert await _invited(user.id) is False             # nothing committed → retry next sweep
    # _unban runs before the mint attempt, so the stale-ban clear still happened.
    assert len(bot.unban_calls) == 1
    assert bot.send_calls == []


async def test_sweep_skips_recently_invited(db, monkeypatch):
    bot = _enable(monkeypatch, FakeBot())
    plan = await make_plan(db)
    user = await make_user(db, telegram_id=9251)
    await make_subscription(db, user=user, plan=plan, days_left=10)
    await db.commit()
    await club._mark_invited(user.id)                   # pretend we DM'd them last sweep

    invited, removed = await club.sweep(db)

    assert (invited, removed) == (0, 0)
    assert bot.invite_calls == []                       # no second link minted
    assert bot.send_calls == []


async def test_sweep_happy_remove(db, monkeypatch):
    bot = _enable(monkeypatch, FakeBot())
    user = await make_user(db, telegram_id=9301)
    user.club_member = True
    await db.commit()

    invited, removed = await club.sweep(db)

    assert (invited, removed) == (0, 1)
    assert await _club_member(db, 9301) is False
    assert len(bot.ban_calls) == 1
    assert len(bot.unban_calls) == 1


async def test_sweep_ban_fails_keeps_member(db, monkeypatch):
    bot = FakeBot()
    bot.fail_ban = True
    _enable(monkeypatch, bot)
    user = await make_user(db, telegram_id=9401)
    user.club_member = True
    await db.commit()

    invited, removed = await club.sweep(db)

    assert (invited, removed) == (0, 0)
    assert await _club_member(db, 9401) is True


async def test_sweep_remove_toctou_renewal_skips(db, monkeypatch):
    bot = _enable(monkeypatch, FakeBot())
    user = await make_user(db, telegram_id=9501)
    user.club_member = True
    await db.commit()

    async def force_active(_db, _user_id, _now):
        return True

    monkeypatch.setattr(club, "_has_active_sub", force_active)

    invited, removed = await club.sweep(db)

    assert (invited, removed) == (0, 0)
    assert await _club_member(db, 9501) is True
    assert bot.ban_calls == []


async def test_sweep_throttles_to_limit(db, monkeypatch):
    bot = _enable(monkeypatch, FakeBot())

    # to_invite()/to_remove() bind `limit=_SWEEP_LIMIT` as a default at definition
    # time, so patching club._SWEEP_LIMIT is a no-op. Instead wrap the real query
    # helper to inject limit=1 — sweep() calls it via the module reference, so this
    # shim is what actually runs.
    real_to_invite = club.to_invite

    async def capped_to_invite(db_, now=None):
        return await real_to_invite(db_, now, limit=1)

    monkeypatch.setattr(club, "to_invite", capped_to_invite)

    plan = await make_plan(db)
    one = await make_user(db, telegram_id=9601)
    two = await make_user(db, telegram_id=9602)
    await make_subscription(db, user=one, plan=plan, days_left=10)
    await make_subscription(db, user=two, plan=plan, days_left=10)
    await db.commit()

    invited, removed = await club.sweep(db)

    assert (invited, removed) == (1, 0)
    assert len(bot.invite_calls) == 1
    # exactly one of the two got a cooldown marker this sweep
    flags = [await _invited(one.id), await _invited(two.id)]
    assert flags.count(True) == 1
