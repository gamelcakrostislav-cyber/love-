"""Native Telegram payments — Telegram Stars (XTR) and card (provider token).

Flow (all over the bot's normal update stream, no webhook/hosting needed):
  pay:choose:<plan>  → show the payment-method picker
  pay:stars:<plan>   → send a Stars (XTR) invoice
  pay:card:<plan>    → send a fiat invoice via the BotFather provider token
  pay:crypto:<plan>  → reuse the existing Crypto Pay (URL) checkout
  pre_checkout_query → approve
  successful_payment → settle server-side (grant + referral + promo), DM the user
"""

from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from app.bot import i18n
from app.bot.handlers.client import _armed_promo, _disarm_promo, _do_buy
from app.bot.keyboards import card_payments_enabled, payment_methods_keyboard
from app.core.config import settings
from app.core.db import SessionFactory
from app.core.logging import get_logger
from app.payments import telegram as tg
from app.services import notion_sync, payments, telegram_pay, users

router = Router(name="payments")
log = get_logger("payments")


async def _user_lang(telegram_id: int) -> str:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, telegram_id)
        return i18n.normalize(user.language if user else None)


@router.callback_query(F.data.startswith("pay:choose:"))
async def choose_method(cb: CallbackQuery) -> None:
    plan_name = cb.data.split(":", 2)[2]
    lang = await _user_lang(cb.from_user.id)
    await cb.message.answer(
        i18n.t(lang, "pay_method_prompt", plan=plan_name),
        parse_mode="HTML", reply_markup=payment_methods_keyboard(plan_name, lang),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pay:crypto:"))
async def pay_crypto(cb: CallbackQuery) -> None:
    plan_name = cb.data.split(":", 2)[2]
    lang = await _user_lang(cb.from_user.id)
    async with SessionFactory() as db:
        text = await _do_buy(db, cb.from_user.id, cb.from_user.username, plan_name, lang)
        await db.commit()
    await cb.message.answer(text, parse_mode="HTML")
    await cb.answer()


async def _confirm(target: Message, lang: str, result) -> None:
    """DM the buyer that access is live (key shown once, or a renewal note)."""
    date = f"{result.expires_at:%Y-%m-%d}"
    if result.new_key_raw:
        await target.answer(
            i18n.t(lang, "pay_confirmed_key", plan=result.plan_name, date=date,
                   apikey=result.new_key_raw), parse_mode="HTML")
    else:
        await target.answer(
            i18n.t(lang, "pay_confirmed_renew", plan=result.plan_name, date=date),
            parse_mode="HTML")


async def _send_native_invoice(cb: CallbackQuery, plan_name: str, method: str) -> None:
    lang = await _user_lang(cb.from_user.id)
    async with SessionFactory() as db:
        user, _ = await users.get_or_create(
            db, telegram_id=cb.from_user.id, username=cb.from_user.username)
        armed = await _armed_promo(cb.from_user.id)
        resolved = await payments.resolve_checkout(
            db, user=user, plan_name=plan_name, armed_code=armed)
        if resolved is None or resolved.plan.is_trial or resolved.plan.price <= 0:
            await db.commit()
            await cb.answer(i18n.t(lang, "buy_unknown"), show_alert=True)
            return
        plan = resolved.plan
        promo_id = resolved.promo.id if resolved.promo else None

        # A 100%-off promo makes it free — grant directly, no invoice.
        if resolved.final <= 0:
            result = await telegram_pay.grant_free(
                db, telegram_id=cb.from_user.id, username=cb.from_user.username,
                plan_id=plan.id, promo_code_id=promo_id)
            await db.commit()
            if result is not None and not result.already_processed:
                await notion_sync.push_user(db, result.user_id)
                await _disarm_promo(cb.from_user.id)
                await _confirm(cb.message, lang, result)
            await cb.answer()
            return

        ratio = (resolved.final / resolved.original) if resolved.original else Decimal(1)
        payload = telegram_pay.build_payload(
            plan_id=plan.id, method=method, promo_code_id=promo_id)
        title = f"{plan.name} subscription"
        desc = i18n.t(lang, "pay_invoice_desc", plan=plan.name, days=plan.duration_days)
        # Charge amount: Stars use the plan's star price (× any discount ratio);
        # card uses the discounted USD. settle() derives the booked USD from
        # whatever Telegram actually charges, so the two never drift.
        if method == "telegram_stars":
            prices = tg.stars_prices(
                title, tg.stars_amount(plan, usd_to_stars=settings.usd_to_stars, ratio=ratio))
            currency, provider_token = tg.STARS_CURRENCY, ""
        else:  # telegram_card
            prices = tg.card_prices(title, resolved.final)
            currency, provider_token = "USD", settings.telegram_provider_token
        await db.commit()

    await cb.message.answer_invoice(
        title=title, description=desc, payload=payload,
        currency=currency, prices=prices, provider_token=provider_token)
    await cb.answer()


@router.callback_query(F.data.startswith("pay:stars:"))
async def pay_stars(cb: CallbackQuery) -> None:
    if not settings.telegram_stars_enabled:
        await cb.answer(i18n.t(await _user_lang(cb.from_user.id), "buy_unknown"), show_alert=True)
        return
    await _send_native_invoice(cb, cb.data.split(":", 2)[2], "telegram_stars")


@router.callback_query(F.data.startswith("pay:card:"))
async def pay_card(cb: CallbackQuery) -> None:
    if not card_payments_enabled():
        await cb.answer(i18n.t(await _user_lang(cb.from_user.id), "buy_unknown"), show_alert=True)
        return
    await _send_native_invoice(cb, cb.data.split(":", 2)[2], "telegram_card")


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    """Approve the checkout. Telegram requires an answer within ~10s; we only
    sanity-check that the payload still parses (the plan is validated at settle)."""
    ok = telegram_pay.parse_payload(query.invoice_payload) is not None
    await query.answer(ok=ok, error_message=None if ok else "This invoice is no longer valid.")


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    sp = message.successful_payment
    lang = await _user_lang(message.from_user.id)
    async with SessionFactory() as db:
        result = await telegram_pay.settle(
            db,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            charge_id=sp.telegram_payment_charge_id,
            payload=sp.invoice_payload,
            total_amount=sp.total_amount,
            currency=sp.currency,
        )
        await db.commit()
        if result is not None and not result.already_processed:
            await notion_sync.push_user(db, result.user_id)

    if result is None:
        log.warning("native payment with unrecognized payload from %s", message.from_user.id)
        return
    if result.already_processed:
        return
    await _disarm_promo(message.from_user.id)  # a confirmed sale consumed the code
    await _confirm(message, lang, result)
