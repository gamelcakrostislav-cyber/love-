"""Promo / discount code engine.

Pure discount math + server-side validation. A code is *quoted* at checkout
(does it exist, is it live, does it apply to this plan/user, what does it cost
after the discount) and *redeemed* only when the resulting payment is paid — so
the redemption cap and the one-per-user rule reflect real sales, never abandoned
invoices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.promo_code import DISCOUNT_PERCENT, PromoCode, PromoRedemption
from app.services.audit import record_audit

_CENTS = Decimal("0.01")


# ─── Error reasons (returned to the bot for a localized message) ──────────────
class PromoError:
    INVALID = "invalid"           # missing / inactive / expired
    PLAN_MISMATCH = "plan"        # code is restricted to another plan
    MAXED = "maxed"               # redemption cap reached
    ALREADY_USED = "already"      # this user already redeemed it


@dataclass(frozen=True)
class PromoQuote:
    promo: PromoCode
    original: Decimal            # plan price before discount
    final: Decimal              # amount actually charged (>= 0)
    saved: Decimal              # original - final
    description: str            # e.g. "20% off" / "10 USD off"


def normalize(code: str) -> str:
    return (code or "").strip().upper()


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_CENTS, rounding=ROUND_HALF_UP)


def discount_for(promo: PromoCode, price: Decimal) -> Decimal:
    """Discounted price for `price` under `promo`, clamped to [0, price]."""
    if promo.discount_type == DISCOUNT_PERCENT:
        pct = max(Decimal(0), min(Decimal(100), promo.discount_value))
        final = price * (Decimal(100) - pct) / Decimal(100)
    else:  # fixed amount off
        final = price - promo.discount_value
    final = _quantize(final)
    if final < 0:
        final = Decimal("0.00")
    return final


def _trim(value: Decimal) -> str:
    """Render a Decimal without trailing zeros ('20.00' -> '20', '12.50' -> '12.5')."""
    return f"{value.normalize():f}"


def describe(promo: PromoCode, currency: str = "USD") -> str:
    if promo.discount_type == DISCOUNT_PERCENT:
        return f"{_trim(promo.discount_value)}% off"
    return f"{_trim(promo.discount_value)} {currency} off"


async def get(db: AsyncSession, code: str) -> PromoCode | None:
    return await db.scalar(select(PromoCode).where(PromoCode.code == normalize(code)))


async def _already_redeemed(db: AsyncSession, *, promo_id: int, user_id: int) -> bool:
    return bool(await db.scalar(
        select(PromoRedemption.id).where(
            PromoRedemption.promo_code_id == promo_id,
            PromoRedemption.user_id == user_id,
        ).limit(1)
    ))


async def quote(
    db: AsyncSession, *, code: str, user_id: int, plan: Plan
) -> PromoQuote | str:
    """Validate `code` for (user, plan). Returns a PromoQuote or a PromoError reason."""
    promo = await get(db, code)
    if promo is None or not promo.is_active:
        return PromoError.INVALID
    if promo.expires_at is not None and promo.expires_at <= datetime.now(UTC):
        return PromoError.INVALID
    if promo.plan_id is not None and promo.plan_id != plan.id:
        return PromoError.PLAN_MISMATCH
    if promo.max_redemptions is not None and promo.times_redeemed >= promo.max_redemptions:
        return PromoError.MAXED
    if await _already_redeemed(db, promo_id=promo.id, user_id=user_id):
        return PromoError.ALREADY_USED
    final = discount_for(promo, plan.price)
    return PromoQuote(
        promo=promo, original=plan.price, final=final,
        saved=_quantize(plan.price - final), description=describe(promo, plan.currency),
    )


async def record_redemption(
    db: AsyncSession, *, promo_id: int, user_id: int, payment_id: int | None
) -> bool:
    """Idempotently record a redemption + bump the counter. Returns True if new.

    Guarded by the (promo_code_id, user_id) unique constraint: a replayed webhook
    finds the row already present and is a no-op (counter not double-incremented).
    """
    if await _already_redeemed(db, promo_id=promo_id, user_id=user_id):
        return False
    db.add(PromoRedemption(promo_code_id=promo_id, user_id=user_id, payment_id=payment_id))
    promo = await db.get(PromoCode, promo_id)
    if promo is not None:
        promo.times_redeemed = (promo.times_redeemed or 0) + 1
    await db.flush()
    return True


# ─── Admin operations ─────────────────────────────────────────────────────────
async def create(
    db: AsyncSession,
    *,
    code: str,
    discount_type: str,
    discount_value: Decimal,
    plan_id: int | None = None,
    max_redemptions: int | None = None,
    expires_at: datetime | None = None,
    actor: str = "admin",
) -> PromoCode:
    promo = PromoCode(
        code=normalize(code),
        discount_type=discount_type,
        discount_value=discount_value,
        plan_id=plan_id,
        max_redemptions=max_redemptions,
        expires_at=expires_at,
    )
    db.add(promo)
    await db.flush()
    await record_audit(
        db, actor=actor, action="promo_created", target=promo.code,
        meta={"type": discount_type, "value": str(discount_value),
              "plan_id": plan_id, "max": max_redemptions},
    )
    return promo


async def deactivate(db: AsyncSession, *, code: str, actor: str = "admin") -> bool:
    promo = await get(db, code)
    if promo is None:
        return False
    promo.is_active = False
    await record_audit(db, actor=actor, action="promo_deactivated", target=promo.code)
    await db.flush()
    return True


async def list_all(db: AsyncSession, limit: int = 50) -> list[tuple[PromoCode, str | None]]:
    """Return [(promo, plan_name_or_None)] newest first."""
    rows = await db.execute(
        select(PromoCode, Plan.name)
        .outerjoin(Plan, Plan.id == PromoCode.plan_id)
        .order_by(PromoCode.id.desc()).limit(limit)
    )
    return [(promo, plan_name) for promo, plan_name in rows.all()]


async def redemption_count(db: AsyncSession, promo_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(PromoRedemption)
        .where(PromoRedemption.promo_code_id == promo_id)
    ) or 0
