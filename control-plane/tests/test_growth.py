"""Growth engine — referral leaderboard + rank (integration: real DB)."""

from __future__ import annotations

from decimal import Decimal

from app.models.enums import CommissionStatus
from app.models.referral import Commission
from app.services import growth
from tests.factories import make_payment, make_plan, make_user


async def _commission(db, *, referrer, referred, plan, ext, amount):
    p = await make_payment(db, user=referred, plan=plan, external_id=ext)
    db.add(Commission(
        referrer_user_id=referrer.id, referred_user_id=referred.id, payment_id=p.id,
        rate=Decimal("0.20"), amount=Decimal(amount), currency="USD",
        status=CommissionStatus.PAYABLE))
    await db.flush()


async def test_leaderboard_orders_by_earnings_and_ranks_users(db):
    plan = await make_plan(db)
    alice = await make_user(db, telegram_id=3001, username="alice")
    bob = await make_user(db, telegram_id=3002, username="bob")
    r1 = await make_user(db, telegram_id=3101)
    r2 = await make_user(db, telegram_id=3102)
    r3 = await make_user(db, telegram_id=3103)
    # alice: 9.80 + 9.80 = 19.60 (2 paid) ; bob: 95.80 (1 paid)
    await _commission(db, referrer=alice, referred=r1, plan=plan, ext="a1", amount="9.80")
    await _commission(db, referrer=alice, referred=r2, plan=plan, ext="a2", amount="9.80")
    await _commission(db, referrer=bob, referred=r3, plan=plan, ext="b1", amount="95.80")
    await db.commit()

    board = await growth.leaderboard(db, limit=10)
    assert [h for _, h, _, _ in board] == ["@bob…", "@ali…"]  # bob ranks first (more earned)
    assert board[0][2] == Decimal("95.80") and board[0][3] == 1
    assert board[1][2] == Decimal("19.60") and board[1][3] == 2

    assert await growth.user_rank(db, bob.id) == (1, Decimal("95.80"), 1)
    assert await growth.user_rank(db, alice.id) == (2, Decimal("19.60"), 2)
    assert await growth.user_rank(db, r1.id) is None  # earned nothing → unranked


async def test_pending_count(db):
    from app.models.enums import ReferralStatus
    from app.models.referral import Referral
    u = await make_user(db, telegram_id=3201)
    referred = await make_user(db, telegram_id=3202)
    db.add(Referral(referrer_user_id=u.id, referred_user_id=referred.id,
                    referrer_type="standard", rate=Decimal("0.20"),
                    status=ReferralStatus.PENDING))
    await db.commit()
    assert await growth.pending_count(db, u.id) == 1


def test_milestones_are_ascending():
    assert list(growth.MILESTONES) == sorted(growth.MILESTONES)
    assert growth.MILESTONES[0] == 1
