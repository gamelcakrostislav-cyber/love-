"""Native Telegram payment helpers (Telegram Stars + card via provider token).

Pure functions that turn a Plan (+ optional discount ratio) into the invoice
amounts Telegram expects:
  - Stars (XTR): the `amount` is a whole number of Stars.
  - Card (fiat): the `amount` is in the currency's smallest unit (cents).
The bot builds and sends the actual invoice; settlement lives in
`app.services.telegram_pay`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from aiogram.types import LabeledPrice

from app.models.plan import Plan

STARS_CURRENCY = "XTR"


def stars_amount(plan: Plan, *, usd_to_stars: int, ratio: Decimal = Decimal(1)) -> int:
    """Stars to charge for `plan`, scaled by `ratio` (e.g. a promo discount).

    Uses the plan's explicit price_stars when set, else derives it from the USD
    price. Always at least 1 (Telegram rejects a 0-Star invoice)."""
    base = plan.price_stars if plan.price_stars else round(float(plan.price) * usd_to_stars)
    scaled = int((Decimal(base) * ratio).to_integral_value(rounding=ROUND_HALF_UP))
    return max(1, scaled)


def stars_prices(label: str, amount: int) -> list[LabeledPrice]:
    return [LabeledPrice(label=label[:32], amount=amount)]


def card_prices(label: str, usd_amount: Decimal) -> list[LabeledPrice]:
    """Fiat invoice line — `amount` is in cents (smallest currency unit)."""
    cents = int((usd_amount * 100).to_integral_value(rounding=ROUND_HALF_UP))
    return [LabeledPrice(label=label[:32], amount=max(1, cents))]
