"""Exclusive subscriber group — who gets invited / removed (query logic)."""

from __future__ import annotations

from app.core.config import settings
from app.services import club
from tests.factories import make_plan, make_subscription, make_user


def test_is_enabled(monkeypatch):
    monkeypatch.setattr(settings, "client_group_id", 0)
    assert not club.is_enabled()
    monkeypatch.setattr(settings, "bot_token", "123:real")
    monkeypatch.setattr(settings, "client_group_id", -1001234567890)
    assert club.is_enabled()


async def test_to_invite_finds_active_non_members(db):
    plan = await make_plan(db)
    active = await make_user(db, telegram_id=8001)            # active, not invited → invite
    await make_subscription(db, user=active, plan=plan, days_left=10)
    await make_user(db, telegram_id=8002)                     # no sub → skip
    already = await make_user(db, telegram_id=8003)           # active but already a member → skip
    already.club_member = True
    await make_subscription(db, user=already, plan=plan, days_left=10)
    await db.commit()

    ids = {u.telegram_id for u in await club.to_invite(db)}
    assert ids == {8001}


async def test_to_remove_finds_lapsed_members(db):
    plan = await make_plan(db)
    keep = await make_user(db, telegram_id=8101)              # member with active sub → keep
    keep.club_member = True
    await make_subscription(db, user=keep, plan=plan, days_left=5)
    lapsed = await make_user(db, telegram_id=8102)            # member, no sub → remove
    lapsed.club_member = True
    expired = await make_user(db, telegram_id=8103)           # member, sub already past → remove
    expired.club_member = True
    await make_subscription(db, user=expired, plan=plan, days_left=-1)
    await make_user(db, telegram_id=8104)                     # non-member → never removed
    await db.commit()

    ids = {u.telegram_id for u in await club.to_remove(db)}
    assert ids == {8102, 8103}
