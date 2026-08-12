"""Monetization nudges: upgrade-to-best-plan + win-back discount code."""

from __future__ import annotations

from decimal import Decimal

from app.bot import notify
from app.core import redis_keys
from app.core.config import settings
from app.core.redis import redis_client
from app.models.promo_code import DISCOUNT_PERCENT
from app.services import notifications, promos, reminders
from tests.factories import make_plan, make_subscription, make_user


def _capture_sends(monkeypatch) -> list[tuple]:
    """Stub notify.send_message (shared module) and record every DM."""
    sends: list[tuple] = []

    async def fake_send(telegram_id, text, **kw):
        sends.append((telegram_id, text, kw.get("reply_markup")))
        return True

    monkeypatch.setattr(notify, "send_message", fake_send)
    return sends


# ─── Upgrade nudge ───────────────────────────────────────────────────────────

async def test_upgrade_nudges_monthly_user_toward_cheaper_yearly(db, monkeypatch):
    sends = _capture_sends(monkeypatch)
    monthly = await make_plan(db, name="monthly", price="49.00", duration_days=30)
    yearly = await make_plan(db, name="yearly", price="479.00", duration_days=365)

    u = await make_user(db, telegram_id=3101)
    await make_subscription(db, user=u, plan=monthly, days_left=10)
    # User already on the best plan must NOT be nudged.
    onbest = await make_user(db, telegram_id=3102)
    await make_subscription(db, user=onbest, plan=yearly, days_left=300)
    await db.commit()

    sent = await notifications.upgrade_sweep(db)

    assert sent == 1
    assert len(sends) == 1
    tid, text, kb = sends[0]
    assert tid == 3101
    assert "20" in text          # ~20% cheaper per day (49/30 vs 479/365)
    assert kb is not None        # one-tap upgrade button
    _ = yearly


async def test_upgrade_nudge_is_deduped(db, monkeypatch):
    sends = _capture_sends(monkeypatch)
    monthly = await make_plan(db, name="monthly", price="49.00", duration_days=30)
    await make_plan(db, name="yearly", price="479.00", duration_days=365)
    u = await make_user(db, telegram_id=3201)
    await make_subscription(db, user=u, plan=monthly, days_left=10)
    await db.commit()

    assert await notifications.upgrade_sweep(db) == 1
    assert await notifications.upgrade_sweep(db) == 0   # marker blocks a second DM
    assert len(sends) == 1


async def test_upgrade_skips_when_not_cheaper_per_day(db, monkeypatch):
    sends = _capture_sends(monkeypatch)
    # Longest plan exists but is NOT cheaper per day → no honest savings, no nudge.
    monthly = await make_plan(db, name="monthly", price="10.00", duration_days=30)   # 0.33/day
    await make_plan(db, name="yearly", price="200.00", duration_days=365)            # 0.55/day
    u = await make_user(db, telegram_id=3301)
    await make_subscription(db, user=u, plan=monthly, days_left=10)
    await db.commit()

    assert await notifications.upgrade_sweep(db) == 0
    assert sends == []


async def test_upgrade_respects_opt_out(db, monkeypatch):
    sends = _capture_sends(monkeypatch)
    monthly = await make_plan(db, name="monthly", price="49.00", duration_days=30)
    await make_plan(db, name="yearly", price="479.00", duration_days=365)
    u = await make_user(db, telegram_id=3401)
    u.notifications_opt_out = True
    await make_subscription(db, user=u, plan=monthly, days_left=10)
    await db.commit()

    assert await notifications.upgrade_sweep(db) == 0
    assert sends == []


async def test_upgrade_disabled_flag(db, monkeypatch):
    _capture_sends(monkeypatch)
    monkeypatch.setattr(settings, "upgrade_nudge_enabled", False)
    assert await notifications.upgrade_sweep(db) == 0


# ─── Win-back discount code ──────────────────────────────────────────────────

async def _lapsed_user(db, telegram_id: int):
    plan = await make_plan(db, name="monthly", price="49.00", duration_days=30)
    u = await make_user(db, telegram_id=telegram_id)
    # Expired ~winback_days (3) ago → lands in the [d+1, d) win-back window.
    await make_subscription(db, user=u, plan=plan, days_left=-3)
    return u


async def test_winback_includes_and_arms_valid_promo(db, monkeypatch):
    sends = _capture_sends(monkeypatch)
    await promos.create(db, code="COMEBACK", discount_type=DISCOUNT_PERCENT,
                        discount_value=Decimal("20"), actor="test")
    u = await _lapsed_user(db, 3501)
    await db.commit()
    monkeypatch.setattr(settings, "winback_promo_code", "COMEBACK")

    sent = await reminders.winback_sweep(db)

    assert sent == 1
    assert "COMEBACK" in sends[0][1]                       # code shown in the DM
    # …and armed so the next purchase applies it automatically.
    assert await redis_client.get(redis_keys.promo_armed(u.telegram_id)) == "COMEBACK"


async def test_winback_falls_back_when_code_unusable(db, monkeypatch):
    sends = _capture_sends(monkeypatch)
    u = await _lapsed_user(db, 3601)
    await db.commit()
    monkeypatch.setattr(settings, "winback_promo_code", "NOSUCHCODE")  # doesn't exist

    sent = await reminders.winback_sweep(db)

    assert sent == 1
    assert "NOSUCHCODE" not in sends[0][1]                 # plain win-back, no dead code
    assert await redis_client.get(redis_keys.promo_armed(u.telegram_id)) is None
