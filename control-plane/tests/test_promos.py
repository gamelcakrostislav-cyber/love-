"""Promo / discount codes — discount math (pure) + validation & redemption (DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.enums import PaymentStatus
from app.models.promo_code import (
    DISCOUNT_FIXED,
    DISCOUNT_PERCENT,
    PromoCode,
    PromoRedemption,
)
from app.services import activation, promos
from tests.factories import make_payment, make_plan, make_user


# ─── Pure discount math (no DB) ───────────────────────────────────────────────
def test_normalize_uppercases_and_trims():
    assert promos.normalize("  save20 ") == "SAVE20"
    assert promos.normalize("") == ""


def test_percent_discount_rounds_to_cents():
    promo = PromoCode(discount_type=DISCOUNT_PERCENT, discount_value=Decimal("20"))
    assert promos.discount_for(promo, Decimal("49.00")) == Decimal("39.20")
    # 33% of 9.99 → 6.69 (half-up rounding)
    promo33 = PromoCode(discount_type=DISCOUNT_PERCENT, discount_value=Decimal("33"))
    assert promos.discount_for(promo33, Decimal("9.99")) == Decimal("6.69")


def test_fixed_discount_clamps_at_zero():
    promo = PromoCode(discount_type=DISCOUNT_FIXED, discount_value=Decimal("10"))
    assert promos.discount_for(promo, Decimal("49.00")) == Decimal("39.00")
    # Discount larger than price never goes negative.
    big = PromoCode(discount_type=DISCOUNT_FIXED, discount_value=Decimal("100"))
    assert promos.discount_for(big, Decimal("49.00")) == Decimal("0.00")


def test_percent_over_100_is_capped():
    promo = PromoCode(discount_type=DISCOUNT_PERCENT, discount_value=Decimal("150"))
    assert promos.discount_for(promo, Decimal("49.00")) == Decimal("0.00")


def test_describe():
    assert promos.describe(
        PromoCode(discount_type=DISCOUNT_PERCENT, discount_value=Decimal("20"))) == "20% off"
    assert promos.describe(
        PromoCode(discount_type=DISCOUNT_FIXED, discount_value=Decimal("10"))) == "10 USD off"


def test_parse_discount_accepts_forgiving_forms():
    assert promos.parse_discount(["20%"]) == (DISCOUNT_PERCENT, Decimal("20"), 1)
    assert promos.parse_discount(["$10"]) == (DISCOUNT_FIXED, Decimal("10"), 1)
    assert promos.parse_discount(["10$"]) == (DISCOUNT_FIXED, Decimal("10"), 1)
    assert promos.parse_discount(["pct", "20"]) == (DISCOUNT_PERCENT, Decimal("20"), 2)
    assert promos.parse_discount(["fixed", "10"]) == (DISCOUNT_FIXED, Decimal("10"), 2)
    assert promos.parse_discount(["20", "%"]) == (DISCOUNT_PERCENT, Decimal("20"), 2)
    assert promos.parse_discount(["10", "fixed"]) == (DISCOUNT_FIXED, Decimal("10"), 2)
    # consumed count = 1 so trailing tokens (plan/max/days) stay for the caller
    assert promos.parse_discount(["20%", "monthly", "100"]) == (DISCOUNT_PERCENT, Decimal("20"), 1)
    # ambiguous / unparseable
    assert promos.parse_discount(["20"]) is None       # bare number needs % or $
    assert promos.parse_discount([]) is None
    assert promos.parse_discount(["abc"]) is None
    assert promos.parse_discount(["pct"]) is None       # type word, no number


async def test_update_changes_only_given_fields(db):
    await promos.create(db, code="EDITME", discount_type=DISCOUNT_PERCENT,
                        discount_value=Decimal("20"))
    await db.commit()
    updated = await promos.update(db, code="editme", discount_value=Decimal("30"))
    await db.commit()
    assert updated.discount_value == Decimal("30")
    assert updated.discount_type == DISCOUNT_PERCENT   # untouched
    assert updated.is_active is True                   # untouched
    # toggle active, leave the rest
    await promos.update(db, code="EDITME", is_active=False)
    await db.commit()
    refreshed = await promos.get(db, "EDITME")
    assert refreshed.is_active is False and refreshed.discount_value == Decimal("30")
    # clearing vs setting limits
    await promos.update(db, code="EDITME", max_redemptions=50)
    await db.commit()
    assert (await promos.get(db, "EDITME")).max_redemptions == 50
    await promos.update(db, code="EDITME", max_redemptions=None)
    await db.commit()
    assert (await promos.get(db, "EDITME")).max_redemptions is None
    # unknown code → None
    assert await promos.update(db, code="NOPE", is_active=False) is None


# ─── Validation (DB) ──────────────────────────────────────────────────────────
async def test_quote_valid_returns_discounted_total(db):
    plan = await make_plan(db)  # 49.00
    user = await make_user(db, telegram_id=5001)
    promo = await promos.create(db, code="save20", discount_type=DISCOUNT_PERCENT,
                                discount_value=Decimal("20"))
    await db.commit()
    q = await promos.quote(db, code="SAVE20", user_id=user.id, plan=plan)
    assert not isinstance(q, str)
    assert q.original == Decimal("49.00")
    assert q.final == Decimal("39.20")
    assert q.saved == Decimal("9.80")
    assert q.promo.id == promo.id


async def test_quote_rejects_inactive_expired_and_plan_mismatch(db):
    plan = await make_plan(db)
    other = await make_plan(db, name="yearly", price="479.00", duration_days=365)
    user = await make_user(db, telegram_id=5002)

    await promos.create(db, code="OFF", discount_type=DISCOUNT_PERCENT,
                        discount_value=Decimal("10"))
    await promos.deactivate(db, code="OFF")
    await promos.create(db, code="GONE", discount_type=DISCOUNT_PERCENT,
                        discount_value=Decimal("10"),
                        expires_at=datetime.now(UTC) - timedelta(days=1))
    await promos.create(db, code="YEARONLY", discount_type=DISCOUNT_PERCENT,
                        discount_value=Decimal("10"), plan_id=other.id)
    await db.commit()

    assert await promos.quote(db, code="OFF", user_id=user.id, plan=plan) == \
        promos.PromoError.INVALID
    assert await promos.quote(db, code="GONE", user_id=user.id, plan=plan) == \
        promos.PromoError.INVALID
    assert await promos.quote(db, code="MISSING", user_id=user.id, plan=plan) == \
        promos.PromoError.INVALID
    assert await promos.quote(db, code="YEARONLY", user_id=user.id, plan=plan) == \
        promos.PromoError.PLAN_MISMATCH


async def test_quote_rejects_when_maxed(db):
    plan = await make_plan(db)
    user = await make_user(db, telegram_id=5003)
    promo = await promos.create(db, code="ONE", discount_type=DISCOUNT_FIXED,
                                discount_value=Decimal("5"), max_redemptions=1)
    promo.times_redeemed = 1
    await db.commit()
    assert await promos.quote(db, code="ONE", user_id=user.id, plan=plan) == \
        promos.PromoError.MAXED


async def test_quote_rejects_second_use_by_same_user(db):
    plan = await make_plan(db)
    user = await make_user(db, telegram_id=5004)
    promo = await promos.create(db, code="ONCE", discount_type=DISCOUNT_FIXED,
                                discount_value=Decimal("5"))
    await db.commit()
    await promos.record_redemption(db, promo_id=promo.id, user_id=user.id, payment_id=None)
    await db.commit()
    assert await promos.quote(db, code="ONCE", user_id=user.id, plan=plan) == \
        promos.PromoError.ALREADY_USED


async def test_record_redemption_is_idempotent(db):
    user = await make_user(db, telegram_id=5005)
    promo = await promos.create(db, code="DUP", discount_type=DISCOUNT_FIXED,
                                discount_value=Decimal("5"))
    await db.commit()
    assert await promos.record_redemption(db, promo_id=promo.id, user_id=user.id, payment_id=None)
    assert not await promos.record_redemption(db, promo_id=promo.id, user_id=user.id, payment_id=None)
    await db.commit()
    assert promo.times_redeemed == 1  # not double-counted


# ─── End-to-end: paying a discounted invoice records the redemption ───────────
async def test_paid_promo_payment_records_redemption(db):
    plan = await make_plan(db)
    user = await make_user(db, telegram_id=5006)
    promo = await promos.create(db, code="WELCOME", discount_type=DISCOUNT_PERCENT,
                                discount_value=Decimal("20"))
    await db.flush()
    payment = await make_payment(db, user=user, plan=plan, external_id="promo-1")
    payment.amount = Decimal("39.20")
    payment.promo_code_id = promo.id
    await db.commit()

    result = await activation.activate_paid_payment(
        db, external_id="promo-1", payer_fingerprint=None, amount=Decimal("39.20"))
    await db.commit()
    assert result is not None and not result.already_processed
    assert payment.status == PaymentStatus.PAID

    redemptions = list(await db.scalars(
        select(PromoRedemption).where(PromoRedemption.promo_code_id == promo.id)))
    assert len(redemptions) == 1 and redemptions[0].user_id == user.id
    refreshed = await promos.get(db, "WELCOME")
    assert refreshed.times_redeemed == 1
