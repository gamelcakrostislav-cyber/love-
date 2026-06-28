"""Native Telegram payments — payload codec, Stars math, and settlement."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.models.enums import CommissionStatus, PaymentStatus, ReferralStatus
from app.models.payment import Payment
from app.models.promo_code import DISCOUNT_PERCENT, PromoRedemption
from app.models.referral import Commission, Referral
from app.payments import telegram as tg
from app.services import promos, subscriptions, telegram_pay
from tests.factories import make_plan, make_user


# ─── Pure: payload codec + amounts ────────────────────────────────────────────
def test_payload_round_trips():
    raw = telegram_pay.build_payload(plan_id=7, method="telegram_stars", promo_code_id=3)
    p = telegram_pay.parse_payload(raw)
    assert p.plan_id == 7 and p.method == "telegram_stars" and p.promo_code_id == 3
    # no promo encodes as "-"
    p2 = telegram_pay.parse_payload(
        telegram_pay.build_payload(plan_id=1, method="telegram_card", promo_code_id=None))
    assert p2.promo_code_id is None


def test_parse_payload_rejects_garbage():
    assert telegram_pay.parse_payload("") is None
    assert telegram_pay.parse_payload("nope|1|stars|-") is None     # bad prefix
    assert telegram_pay.parse_payload("tg|x|stars|-") is None        # bad int
    assert telegram_pay.parse_payload("tg|1|stars") is None          # too few parts
    assert telegram_pay.parse_payload("tg|1|stars|-|100") is None    # too many parts


def test_charged_usd_derives_from_what_telegram_charged():
    from decimal import Decimal as D
    # card: cents / 100
    assert telegram_pay.charged_usd(total_amount=4900, currency="USD", usd_to_stars=50) == D("49.00")
    # stars: stars / rate
    assert telegram_pay.charged_usd(total_amount=2450, currency="XTR", usd_to_stars=50) == D("49.00")
    assert telegram_pay.charged_usd(total_amount=1960, currency="XTR", usd_to_stars=50) == D("39.20")


async def test_stars_amount_explicit_derived_and_scaled(db):
    explicit = await make_plan(db, name="m", price="49.00")
    explicit.price_stars = 2500
    assert tg.stars_amount(explicit, usd_to_stars=50) == 2500
    # 20% off → 2000
    assert tg.stars_amount(explicit, usd_to_stars=50, ratio=Decimal("0.8")) == 2000
    # no explicit price → derive from usd * rate
    derived = await make_plan(db, name="y", price="10.00")
    assert tg.stars_amount(derived, usd_to_stars=50) == 500
    # never below 1
    assert tg.stars_amount(derived, usd_to_stars=50, ratio=Decimal("0")) == 1


def test_card_prices_are_cents():
    assert tg.card_prices("x", Decimal("49.00"))[0].amount == 4900
    assert tg.card_prices("x", Decimal("9.99"))[0].amount == 999


# ─── Settlement (DB) ──────────────────────────────────────────────────────────
async def test_settle_grants_and_is_idempotent(db):
    plan = await make_plan(db, name="monthly", price="49.00")
    user = await make_user(db, telegram_id=7001, username="buyer")
    await db.commit()
    payload = telegram_pay.build_payload(
        plan_id=plan.id, method="telegram_stars", promo_code_id=None)

    # Stars: Telegram charged 2450 XTR → booked as $49.00 (2450 / 50).
    result = await telegram_pay.settle(
        db, telegram_id=7001, username="buyer", charge_id="charge-1", payload=payload,
        total_amount=2450, currency="XTR")
    await db.commit()
    assert result is not None and not result.already_processed
    assert result.plan_name == "monthly" and result.new_key_raw  # fresh key issued

    pay = await db.scalar(select(Payment).where(Payment.external_id == "charge-1"))
    assert pay.status == PaymentStatus.PAID and pay.amount == Decimal("49.00")
    assert pay.provider == "telegram_stars" and pay.currency == "USD"
    assert await subscriptions.get_active_with_plan(db, user.id) is not None

    # Replayed delivery → no-op, no second payment row.
    again = await telegram_pay.settle(
        db, telegram_id=7001, username="buyer", charge_id="charge-1", payload=payload,
        total_amount=2450, currency="XTR")
    await db.commit()
    assert again.already_processed
    count = await db.scalar(
        select(func.count()).select_from(Payment).where(Payment.external_id == "charge-1"))
    assert count == 1


async def test_settle_rejects_method_currency_mismatch(db):
    plan = await make_plan(db, name="monthly", price="49.00")
    await db.commit()
    # A Stars payload settled with a USD charge (or vice-versa) is rejected.
    stars_payload = telegram_pay.build_payload(
        plan_id=plan.id, method="telegram_stars", promo_code_id=None)
    assert await telegram_pay.settle(
        db, telegram_id=7008, username=None, charge_id="cx", payload=stars_payload,
        total_amount=4900, currency="USD") is None


async def test_settle_records_promo_redemption(db):
    plan = await make_plan(db, name="monthly", price="49.00")
    user = await make_user(db, telegram_id=7002)
    promo = await promos.create(db, code="STAR20", discount_type=DISCOUNT_PERCENT,
                                discount_value=Decimal("20"))
    await db.commit()
    payload = telegram_pay.build_payload(
        plan_id=plan.id, method="telegram_stars", promo_code_id=promo.id)
    # 20% off → Telegram charged 1960 XTR → booked $39.20.
    result = await telegram_pay.settle(
        db, telegram_id=7002, username=None, charge_id="charge-2", payload=payload,
        total_amount=1960, currency="XTR")
    await db.commit()
    assert result is not None
    pay = await db.scalar(select(Payment).where(Payment.external_id == "charge-2"))
    assert pay.amount == Decimal("39.20")
    rows = list(await db.scalars(
        select(PromoRedemption).where(PromoRedemption.promo_code_id == promo.id)))
    assert len(rows) == 1 and rows[0].user_id == user.id
    assert (await promos.get(db, "STAR20")).times_redeemed == 1


async def test_settle_unlocks_referral_commission(db):
    plan = await make_plan(db, name="monthly", price="49.00")
    referrer = await make_user(db, telegram_id=7100, username="ref")
    buyer = await make_user(db, telegram_id=7003)
    db.add(Referral(referrer_user_id=referrer.id, referred_user_id=buyer.id,
                    rate=Decimal("0.20"), status=ReferralStatus.PENDING))
    await db.commit()
    payload = telegram_pay.build_payload(
        plan_id=plan.id, method="telegram_card", promo_code_id=None)
    # Card: Telegram charged 4900 cents → $49.00 → commission $9.80.
    await telegram_pay.settle(
        db, telegram_id=7003, username=None, charge_id="charge-3", payload=payload,
        total_amount=4900, currency="USD")
    await db.commit()
    commission = await db.scalar(select(Commission).where(Commission.referred_user_id == buyer.id))
    assert commission is not None and commission.amount == Decimal("9.80")
    assert commission.status == CommissionStatus.PAYABLE


async def test_grant_free_activates_without_charge(db):
    plan = await make_plan(db, name="monthly", price="49.00")
    user = await make_user(db, telegram_id=7009)
    promo = await promos.create(db, code="FREE100", discount_type=DISCOUNT_PERCENT,
                                discount_value=Decimal("100"))
    await db.commit()
    result = await telegram_pay.grant_free(
        db, telegram_id=7009, username=None, plan_id=plan.id, promo_code_id=promo.id)
    await db.commit()
    assert result is not None and not result.already_processed
    pay = await db.scalar(select(Payment).where(Payment.user_id == user.id))
    assert pay.amount == Decimal("0.00") and pay.provider == "promo_free"
    assert await subscriptions.get_active_with_plan(db, user.id) is not None
    # idempotent — a second free grant is a no-op
    again = await telegram_pay.grant_free(
        db, telegram_id=7009, username=None, plan_id=plan.id, promo_code_id=promo.id)
    await db.commit()
    assert again.already_processed


async def test_settle_rejects_bad_payload(db):
    assert await telegram_pay.settle(
        db, telegram_id=7004, username=None, charge_id="c", payload="garbage",
        total_amount=100, currency="XTR") is None


# ─── Shared checkout resolution (plan + armed promo) ──────────────────────────
async def test_resolve_checkout_applies_promo(db):
    from app.services import payments as pay_svc
    await make_plan(db, name="monthly", price="49.00")
    user = await make_user(db, telegram_id=7005)
    await promos.create(db, code="HALF", discount_type=DISCOUNT_PERCENT,
                        discount_value=Decimal("50"))
    await db.commit()
    # no code → full price
    full = await pay_svc.resolve_checkout(db, user=user, plan_name="monthly", armed_code=None)
    assert full.final == Decimal("49.00") and full.promo is None
    # valid code → discounted
    disc = await pay_svc.resolve_checkout(db, user=user, plan_name="monthly", armed_code="HALF")
    assert disc.final == Decimal("24.50") and disc.promo is not None
    # invalid code → silently ignored (full price)
    bad = await pay_svc.resolve_checkout(db, user=user, plan_name="monthly", armed_code="NOPE")
    assert bad.final == Decimal("49.00") and bad.promo is None
    # unknown plan → None
    assert await pay_svc.resolve_checkout(db, user=user, plan_name="ghost", armed_code=None) is None
