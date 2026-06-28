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
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.promo_code import (
    DISCOUNT_FIXED,
    DISCOUNT_PERCENT,
    PromoCode,
    PromoRedemption,
)
from app.services.audit import record_audit

_CENTS = Decimal("0.01")

# Sentinel for update(): "leave this field unchanged" (vs. None = clear it).
_KEEP = object()


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


# ─── Forgiving admin discount parsing ─────────────────────────────────────────
# So admins can write 20% · $10 · pct 20 · fixed 10 · 20 % · 10$ — instead of a
# rigid "<pct|fixed> <value>".
_PCT_WORDS = {"pct", "percent", "percentage", "%", "p"}
_FIXED_WORDS = {"fixed", "flat", "amount", "usd", "$", "f"}


def _num(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _amount_token(tok: str) -> tuple[str | None, Decimal] | None:
    """Parse a single token like '20%', '$10', '10$', 'pct20', '10' into
    (discount_type | None, value), or None if it isn't a number."""
    s = tok.strip().replace(",", ".")
    sl = s.lower()
    dtype: str | None = None
    if s.endswith("%"):
        dtype, s = DISCOUNT_PERCENT, s[:-1]
    elif sl.startswith("pct"):
        dtype, s = DISCOUNT_PERCENT, s[3:]
    elif sl.endswith("pct"):
        dtype, s = DISCOUNT_PERCENT, s[:-3]
    elif s.startswith("$"):
        dtype, s = DISCOUNT_FIXED, s[1:]
    elif s.endswith("$"):
        dtype, s = DISCOUNT_FIXED, s[:-1]
    elif sl.endswith("usd"):
        dtype, s = DISCOUNT_FIXED, s[:-3]
    val = _num(s)
    if val is None:
        return None
    return dtype, val


def parse_discount(tokens: list[str]) -> tuple[str, Decimal, int] | None:
    """Read the leading 1–2 tokens as a discount amount.

    Returns (discount_type, value, tokens_consumed) or None if the leading
    tokens don't describe a valid amount (e.g. a bare number with no % or $)."""
    if not tokens:
        return None
    first = tokens[0].lower()
    # Type word first: "pct 20" / "fixed 10".
    if first in _PCT_WORDS or first in _FIXED_WORDS:
        if len(tokens) < 2:
            return None
        val = _num(tokens[1])
        if val is None:
            return None
        return (DISCOUNT_PERCENT if first in _PCT_WORDS else DISCOUNT_FIXED), val, 2
    parsed = _amount_token(tokens[0])
    if parsed is None:
        return None
    dtype, val = parsed
    if dtype is not None:  # symbol carried the type ("20%", "$10")
        return dtype, val, 1
    # Bare number — the type may be in the next token ("20 %", "10 fixed").
    if len(tokens) >= 2:
        nxt = tokens[1].lower()
        if nxt in _PCT_WORDS:
            return DISCOUNT_PERCENT, val, 2
        if nxt in _FIXED_WORDS:
            return DISCOUNT_FIXED, val, 2
    return None  # ambiguous: a bare number needs a % or $


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


async def update(
    db: AsyncSession,
    *,
    code: str,
    discount_type: str = _KEEP,           # type: ignore[assignment]
    discount_value: Decimal = _KEEP,      # type: ignore[assignment]
    plan_id: int | None = _KEEP,          # type: ignore[assignment]
    max_redemptions: int | None = _KEEP,  # type: ignore[assignment]
    expires_at: datetime | None = _KEEP,  # type: ignore[assignment]
    is_active: bool = _KEEP,              # type: ignore[assignment]
    actor: str = "admin",
) -> PromoCode | None:
    """Edit an existing code in place. Each field defaults to _KEEP (unchanged);
    pass a concrete value to set it, or None to clear it (plan/cap/expiry)."""
    promo = await get(db, code)
    if promo is None:
        return None
    changed: dict[str, object] = {}
    if discount_type is not _KEEP:
        promo.discount_type = discount_type
        changed["type"] = discount_type
    if discount_value is not _KEEP:
        promo.discount_value = discount_value
        changed["value"] = str(discount_value)
    if plan_id is not _KEEP:
        promo.plan_id = plan_id
        changed["plan_id"] = plan_id
    if max_redemptions is not _KEEP:
        promo.max_redemptions = max_redemptions
        changed["max"] = max_redemptions
    if expires_at is not _KEEP:
        promo.expires_at = expires_at
        changed["expires"] = expires_at.isoformat() if expires_at else None
    if is_active is not _KEEP:
        promo.is_active = is_active
        changed["active"] = is_active
    await record_audit(db, actor=actor, action="promo_updated", target=promo.code, meta=changed)
    await db.flush()
    return promo


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
