"""Client-notification segmentation + opt-out (integration: real DB)."""

from __future__ import annotations

from app.services import notifications
from tests.factories import make_plan, make_subscription, make_user


async def test_segment_excludes_opted_out_and_filters_by_subscription(db):
    monthly = await make_plan(db, name="monthly")
    trial = await make_plan(db, name="trial", price="0.00", is_trial=True, max_profitability="0.02")

    # active paid subscriber, opted in
    paid = await make_user(db, telegram_id=2001)
    await make_subscription(db, user=paid, plan=monthly, days_left=10)
    # active trial subscriber, opted in
    triallist = await make_user(db, telegram_id=2002)
    await make_subscription(db, user=triallist, plan=trial, days_left=5)
    # no subscription, opted in
    await make_user(db, telegram_id=2003)
    # active subscriber but OPTED OUT — must never appear
    muted = await make_user(db, telegram_id=2004)
    muted.notifications_opt_out = True
    await make_subscription(db, user=muted, plan=monthly, days_left=10)
    await db.commit()

    assert set(await notifications.segment_telegram_ids(db, "all")) == {2001, 2002, 2003}
    assert set(await notifications.segment_telegram_ids(db, "active")) == {2001, 2002}
    assert set(await notifications.segment_telegram_ids(db, "trial")) == {2002}
    assert set(await notifications.segment_telegram_ids(db, "inactive")) == {2003}


async def test_segments_constant_matches_handler_choices():
    assert notifications.SEGMENTS == ("all", "active", "trial", "inactive")
