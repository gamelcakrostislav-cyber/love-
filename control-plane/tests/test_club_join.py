"""Subscriber-group gatekeeper: join-request admission, membership truth, handlers."""

from __future__ import annotations

import types
from contextlib import asynccontextmanager

from aiogram.enums import ChatMemberStatus
from sqlalchemy import select

from app.bot.handlers import club_join
from app.core.config import settings
from app.models.user import User
from app.services import club
from tests.factories import make_plan, make_subscription, make_user

_GROUP = -1001234567890


def _enable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "bot_token", "123:real")
    monkeypatch.setattr(settings, "client_group_id", _GROUP)


def _use_test_db(monkeypatch, db) -> None:
    """Make the handlers' `async with SessionFactory()` use the test session, so
    their writes land in the same DB/session the test reads from (and we avoid the
    app's pooled engine in the test loop)."""
    @asynccontextmanager
    async def factory():
        yield db

    monkeypatch.setattr(club_join, "SessionFactory", factory)


async def _club_member(db, telegram_id: int) -> bool:
    return await db.scalar(select(User.club_member).where(User.telegram_id == telegram_id))


# --- service: admission gate -------------------------------------------------

async def test_admit_requires_active_sub(db):
    plan = await make_plan(db)
    sub_user = await make_user(db, telegram_id=7001)
    await make_subscription(db, user=sub_user, plan=plan, days_left=5)
    await make_user(db, telegram_id=7002)                      # known user, no sub
    await db.commit()

    assert await club.admit_join_request(db, 7001) is True
    assert await club.admit_join_request(db, 7002) is False
    assert await club.admit_join_request(db, 999999) is False  # unknown telegram id


# --- service: membership truth ----------------------------------------------

async def test_set_membership_join_sets_flag_and_clears_cooldown(db):
    user = await make_user(db, telegram_id=7101)
    await db.commit()
    await club._mark_invited(user.id)                          # pretend a link was DM'd
    assert await club._recently_invited(user.id) is True

    await club.set_membership(db, 7101, joined=True)

    assert await _club_member(db, 7101) is True
    assert await club._recently_invited(user.id) is False      # cooldown cleared on real join


async def test_set_membership_leave_clears_flag(db):
    user = await make_user(db, telegram_id=7102)
    user.club_member = True
    await db.commit()

    await club.set_membership(db, 7102, joined=False)

    assert await _club_member(db, 7102) is False


async def test_set_membership_idempotent_and_unknown_user(db):
    user = await make_user(db, telegram_id=7103)
    user.club_member = True
    await db.commit()
    await club.set_membership(db, 7103, joined=True)           # no-op, must not raise
    assert await _club_member(db, 7103) is True
    await club.set_membership(db, 424242, joined=True)         # unknown user, must not raise


# --- handler fakes -----------------------------------------------------------

class _FakeJoinRequest:
    def __init__(self, chat_id: int, user_id: int, lang: str = "en") -> None:
        self.chat = types.SimpleNamespace(id=chat_id)
        self.from_user = types.SimpleNamespace(id=user_id, language_code=lang)
        self.approved = False
        self.declined = False

    async def approve(self) -> None:
        self.approved = True

    async def decline(self) -> None:
        self.declined = True


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_message(self, chat_id, text) -> None:
        self.sent.append((chat_id, text))


def _member(user_id: int, status, *, is_bot: bool = False, is_member: bool = True):
    user = types.SimpleNamespace(id=user_id, is_bot=is_bot)
    return types.SimpleNamespace(user=user, status=status, is_member=is_member)


class _FakeChatMemberUpdated:
    def __init__(self, chat_id: int, member) -> None:
        self.chat = types.SimpleNamespace(id=chat_id)
        self.new_chat_member = member


# --- handler: join request ---------------------------------------------------

async def test_handler_approves_subscriber(db, monkeypatch):
    _enable(monkeypatch)
    _use_test_db(monkeypatch, db)
    plan = await make_plan(db)
    user = await make_user(db, telegram_id=7201)
    await make_subscription(db, user=user, plan=plan, days_left=5)
    await db.commit()

    event, bot = _FakeJoinRequest(_GROUP, 7201), _FakeBot()
    await club_join.on_join_request(event, bot)

    assert event.approved is True and event.declined is False
    assert await _club_member(db, 7201) is True
    assert bot.sent == []                                      # approval is silent


async def test_handler_declines_non_subscriber(db, monkeypatch):
    _enable(monkeypatch)
    _use_test_db(monkeypatch, db)
    await make_user(db, telegram_id=7202)                      # no sub
    await db.commit()

    event, bot = _FakeJoinRequest(_GROUP, 7202), _FakeBot()
    await club_join.on_join_request(event, bot)

    assert event.declined is True and event.approved is False
    assert await _club_member(db, 7202) is False
    assert len(bot.sent) == 1                                  # told them why


async def test_handler_declines_unknown_user_in_english(db, monkeypatch):
    _enable(monkeypatch)
    _use_test_db(monkeypatch, db)
    # a total stranger (no user row) with a French device — must NOT get French.
    event, bot = _FakeJoinRequest(_GROUP, 778899, lang="fr"), _FakeBot()
    await club_join.on_join_request(event, bot)

    assert event.declined is True
    assert len(bot.sent) == 1
    assert "members chat" in bot.sent[0][1]                    # English default, not device locale


async def test_handler_ignores_other_chats(db, monkeypatch):
    _enable(monkeypatch)
    _use_test_db(monkeypatch, db)
    plan = await make_plan(db)
    user = await make_user(db, telegram_id=7203)
    await make_subscription(db, user=user, plan=plan, days_left=5)
    await db.commit()

    event, bot = _FakeJoinRequest(-100999999, 7203), _FakeBot()  # not the club chat
    await club_join.on_join_request(event, bot)

    assert event.approved is False and event.declined is False


# --- handler: chat_member roster sync ---------------------------------------

async def test_chat_member_join_marks_member(db, monkeypatch):
    _enable(monkeypatch)
    _use_test_db(monkeypatch, db)
    await make_user(db, telegram_id=7301)
    await db.commit()

    event = _FakeChatMemberUpdated(_GROUP, _member(7301, ChatMemberStatus.MEMBER))
    await club_join.on_chat_member(event)

    assert await _club_member(db, 7301) is True


async def test_chat_member_leave_unmarks_member(db, monkeypatch):
    _enable(monkeypatch)
    _use_test_db(monkeypatch, db)
    user = await make_user(db, telegram_id=7302)
    user.club_member = True
    await db.commit()

    event = _FakeChatMemberUpdated(_GROUP, _member(7302, ChatMemberStatus.LEFT))
    await club_join.on_chat_member(event)

    assert await _club_member(db, 7302) is False


async def test_chat_member_ignores_bots(db, monkeypatch):
    _enable(monkeypatch)
    _use_test_db(monkeypatch, db)
    await make_user(db, telegram_id=7303)
    await db.commit()

    event = _FakeChatMemberUpdated(_GROUP, _member(7303, ChatMemberStatus.MEMBER, is_bot=True))
    await club_join.on_chat_member(event)

    assert await _club_member(db, 7303) is False               # bot membership not recorded


# --- preflight / operator config self-check ---------------------------------

class _FakeAdminBot:
    def __init__(self, *, chat_type="supergroup", status="administrator",
                 can_invite=True, can_restrict=True) -> None:
        self._chat_type = chat_type
        self._status = status
        self._can_invite = can_invite
        self._can_restrict = can_restrict

    async def get_chat(self, chat_id):
        return types.SimpleNamespace(type=self._chat_type, title="Test")

    async def get_me(self):
        return types.SimpleNamespace(id=999)

    async def get_chat_member(self, chat_id, user_id):
        return types.SimpleNamespace(
            status=self._status,
            can_invite_users=self._can_invite,
            can_restrict_members=self._can_restrict,
        )


async def test_preflight_disabled(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "CHANGE_ME")
    assert "disabled" in await club.preflight()


async def test_check_config_rejects_basic_group():
    assert "not a supergroup" in await club._check_config(_FakeAdminBot(chat_type="group"))


async def test_check_config_rejects_non_admin():
    assert "not an admin" in await club._check_config(_FakeAdminBot(status="member"))


async def test_check_config_warns_missing_rights():
    msg = await club._check_config(_FakeAdminBot(can_restrict=False))
    assert "WARNING" in msg and "Ban users" in msg


async def test_check_config_ok():
    assert (await club._check_config(_FakeAdminBot())).startswith("OK")
