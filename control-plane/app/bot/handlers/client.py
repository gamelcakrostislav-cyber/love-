"""Client-facing commerce & control commands (aiogram 3.x), localized.

Free-text routing order in the catch-all: menu buttons → human relay → AI agent.
All entitlement/abuse state lives server-side; the bot only displays it and
triggers server-side actions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from sqlalchemy import func, select

from app.bot import i18n
from app.bot.keyboards import (
    devices_keyboard,
    language_keyboard,
    main_menu_keyboard,
    plans_keyboard,
    reissue_confirm_keyboard,
)
from app.core.config import settings
from app.core.db import SessionFactory
from app.models.enums import ReferralStatus
from app.models.plan import Plan
from app.models.referral import Commission, Referral
from app.services import devices as devices_svc
from app.services import (
    handoff,
    keys,
    payments,
    referrals,
    subscriptions,
    support,
    users,
)

router = Router(name="client")


# ─── Small helpers ───────────────────────────────────────────────────────────
def _seed_lang(message: Message) -> str:
    """Best-effort initial language from the user's Telegram client setting."""
    code = (message.from_user.language_code or "en")[:2]
    return i18n.normalize(code)


async def _user_lang(telegram_id: int) -> str:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, telegram_id)
        return i18n.normalize(user.language if user else None)


async def _active_plans(db) -> list[Plan]:
    result = await db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price))
    return list(result)


async def _escalate(message: Message, user, last_text: str, lang: str) -> None:
    """Put a user into human-handoff mode and ping the admins (admins read EN)."""
    await handoff.enter(user.telegram_id)
    uname = f"@{message.from_user.username}" if message.from_user.username else "(no username)"
    await handoff.notify_admins(
        "🆘 <b>Support request</b>\n"
        f"From: {uname} (id <code>{user.telegram_id}</code>)\n"
        f"Message: {last_text}\n\n"
        f"Reply with <code>/reply {user.telegram_id} your message</code>, "
        f"or <code>/close {user.telegram_id}</code> to end."
    )
    await message.answer(i18n.t(lang, "human_connecting"))


# ─── Reusable action views (called by slash commands AND menu buttons) ───────
async def show_plans(message: Message, lang: str) -> None:
    async with SessionFactory() as db:
        plans = await _active_plans(db)
    lines = [i18n.t(lang, "plans_header")]
    for p in plans:
        tier = i18n.t(lang, "tier_trial") if p.is_trial else i18n.t(lang, "tier_all")
        price = i18n.t(lang, "price_free") if p.price == 0 else f"{p.price} {p.currency}"
        lines.append(i18n.t(
            lang, "plan_line", name=p.name, price=price, days=p.duration_days, tier=tier,
            devices=p.max_devices, sessions=p.max_concurrent_sessions, rate=p.rate_limit_per_min,
        ))
    await message.answer("\n".join(lines), parse_mode="HTML",
                         reply_markup=plans_keyboard(plans, lang))


async def show_status(message: Message, lang: str) -> None:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, message.from_user.id)
        if user is None:
            await message.answer(i18n.t(lang, "no_account"))
            return
        active = await subscriptions.get_active_with_plan(db, user.id)
        key = await keys.get_active_key(db, user.id)
    if active is None:
        await message.answer(i18n.t(lang, "status_none"))
        return
    sub, plan = active
    key_line = (
        i18n.t(lang, "status_key_line", prefix=key.prefix) if key
        else i18n.t(lang, "status_no_key")
    )
    days = max(0, (sub.expires_at - datetime.now(UTC)).days)
    await message.answer(
        i18n.t(lang, "status_block", plan=plan.name, status=sub.status,
               expires=f"{sub.expires_at:%Y-%m-%d %H:%M UTC}",
               days_left=i18n.t(lang, "days_left", n=days), key_line=key_line),
        parse_mode="HTML",
    )


async def show_key(message: Message, lang: str) -> None:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, message.from_user.id)
        key = await keys.get_active_key(db, user.id) if user else None
    if key is None:
        await message.answer(i18n.t(lang, "key_none"))
        return
    await message.answer(i18n.t(lang, "key_show", prefix=key.prefix), parse_mode="HTML",
                         reply_markup=reissue_confirm_keyboard(lang))


async def show_devices(message: Message, lang: str) -> None:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, message.from_user.id)
        key = await keys.get_active_key(db, user.id) if user else None
        device_list = await devices_svc.list_for_key(db, key.id) if key else []
    if not key:
        await message.answer(i18n.t(lang, "devices_none_key"))
        return
    if not device_list:
        await message.answer(i18n.t(lang, "devices_empty"))
        return
    lines = [i18n.t(lang, "devices_header")]
    for d in device_list:
        lines.append(f"• <code>{d.fingerprint[:16]}…</code> — {d.status}")
    lines.append(i18n.t(lang, "devices_remove_hint"))
    await message.answer("\n".join(lines), parse_mode="HTML",
                         reply_markup=devices_keyboard(device_list, lang))


async def show_help(message: Message, lang: str) -> None:
    await message.answer(i18n.t(lang, "help"), parse_mode="HTML")


async def show_referrals(message: Message, lang: str) -> None:
    me = await message.bot.me()  # cached after first call
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, message.from_user.id)
        if user is None:
            await message.answer(i18n.t(lang, "no_account"))
            return
        invited = await db.scalar(
            select(func.count()).select_from(Referral)
            .where(Referral.referrer_user_id == user.id)) or 0
        qualified = await db.scalar(
            select(func.count()).select_from(Referral)
            .where(Referral.referrer_user_id == user.id,
                   Referral.status == ReferralStatus.QUALIFIED)) or 0
        earned = await db.scalar(
            select(func.coalesce(func.sum(Commission.amount), 0))
            .where(Commission.referrer_user_id == user.id)) or 0
        is_blogger = user.is_blogger
    rate = settings.referral_rate_blogger if is_blogger else settings.referral_rate_standard
    link = f"https://t.me/{me.username}?start={message.from_user.id}"
    await message.answer(
        i18n.t(lang, "referrals_block", rate=int(round(rate * 100)), link=link,
               invited=invited, qualified=qualified, earned=f"{earned} USD"),
        parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def open_language(message: Message) -> None:
    lang = await _user_lang(message.from_user.id)
    await message.answer(i18n.t(lang, "choose_language"), reply_markup=language_keyboard())


async def _has_active_sub(db, user_id: int) -> bool:
    return await subscriptions.get_active_with_plan(db, user_id) is not None


async def _human_flow(message: Message) -> None:
    async with SessionFactory() as db:
        user, _ = await users.get_or_create(
            db, telegram_id=message.from_user.id, username=message.from_user.username
        )
        lang = i18n.normalize(user.language)
        await db.commit()
    await _escalate(message, user, "(used 🆘 Human)", lang)


# ─── /start + language ───────────────────────────────────────────────────────
async def _do_start(message: Message, ref_payload: str | None) -> None:
    async with SessionFactory() as db:
        user, created = await users.get_or_create(
            db, telegram_id=message.from_user.id, username=message.from_user.username
        )
        if created:
            ref_note = ""
            user.language = _seed_lang(message)
            if ref_payload and ref_payload.isdigit():
                referral = await referrals.attach(
                    db, referred_user=user, referrer_telegram_id=int(ref_payload)
                )
                if referral is not None:
                    ref_note = "\n🎁"
            lang = i18n.normalize(user.language)
            await db.commit()
            # First impression for a brand-new user: just pick a language.
            # The welcome + menu + quick-start follow once they choose (set_language).
            await message.answer(i18n.t(lang, "choose_language") + ref_note,
                                 reply_markup=language_keyboard())
            return

        lang = i18n.normalize(user.language)
        has_sub = await _has_active_sub(db, user.id)

    # Returning user: warm welcome-back + the persistent menu.
    await message.answer(i18n.t(lang, "welcome_back"),
                         parse_mode="HTML", reply_markup=main_menu_keyboard(lang))
    if not has_sub:
        await message.answer(i18n.t(lang, "getting_started"), parse_mode="HTML")


@router.message(CommandStart(deep_link=True))
async def start_with_ref(message: Message, command: CommandObject) -> None:
    await _do_start(message, (command.args or "").strip())


@router.message(CommandStart())
async def start(message: Message) -> None:
    await _do_start(message, None)


@router.callback_query(F.data.startswith("lang:set:"))
async def set_language(cb: CallbackQuery) -> None:
    code = i18n.normalize(cb.data.split(":")[2])
    async with SessionFactory() as db:
        user, _ = await users.get_or_create(
            db, telegram_id=cb.from_user.id, username=cb.from_user.username
        )
        user.language = code
        has_sub = await _has_active_sub(db, user.id)
        await db.commit()
    await cb.message.answer(i18n.t(code, "language_set", lang=i18n.LANGUAGES[code]))
    await cb.message.answer(i18n.t(code, "welcome"), parse_mode="HTML",
                            reply_markup=main_menu_keyboard(code))
    # New / unsubscribed users get the quick-start guide right after choosing.
    if not has_sub:
        await cb.message.answer(i18n.t(code, "getting_started"), parse_mode="HTML")
    await cb.answer()


@router.message(Command("language"))
async def language_cmd(message: Message) -> None:
    await open_language(message)


# ─── Slash commands (thin wrappers over the views) ───────────────────────────
@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await show_help(message, await _user_lang(message.from_user.id))


@router.message(Command("plans"))
async def plans_cmd(message: Message) -> None:
    await show_plans(message, await _user_lang(message.from_user.id))


@router.message(Command("status"))
async def status_cmd(message: Message) -> None:
    await show_status(message, await _user_lang(message.from_user.id))


@router.message(Command("key"))
async def key_cmd(message: Message) -> None:
    await show_key(message, await _user_lang(message.from_user.id))


@router.message(Command("devices"))
async def devices_cmd(message: Message) -> None:
    await show_devices(message, await _user_lang(message.from_user.id))


@router.message(Command("referrals"))
async def referrals_cmd(message: Message) -> None:
    await show_referrals(message, await _user_lang(message.from_user.id))


@router.message(Command("human"))
async def human_cmd(message: Message) -> None:
    await _human_flow(message)


# ─── Buy ─────────────────────────────────────────────────────────────────────
async def _do_buy(db, telegram_id: int, username: str | None, plan_name: str, lang: str) -> str:
    user, _ = await users.get_or_create(db, telegram_id=telegram_id, username=username)
    plan = await db.scalar(
        select(Plan).where(Plan.name == plan_name, Plan.is_active.is_(True))
    )
    if plan is None:
        return i18n.t(lang, "buy_unknown")
    _payment, pay_url = await payments.start_checkout(db, user=user, plan=plan)
    return i18n.t(lang, "buy_invoice", name=plan.name, price=plan.price,
                  currency=plan.currency, url=pay_url)


@router.message(Command("buy"))
async def buy_cmd(message: Message, command: CommandObject) -> None:
    plan_name = (command.args or "").strip().lower()
    lang = await _user_lang(message.from_user.id)
    if not plan_name:
        await show_plans(message, lang)
        return
    async with SessionFactory() as db:
        text = await _do_buy(db, message.from_user.id, message.from_user.username, plan_name, lang)
        await db.commit()
    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("buy:"))
async def buy_callback(cb: CallbackQuery) -> None:
    plan_name = cb.data.split(":", 1)[1]
    lang = await _user_lang(cb.from_user.id)
    async with SessionFactory() as db:
        text = await _do_buy(db, cb.from_user.id, cb.from_user.username, plan_name, lang)
        await db.commit()
    await cb.message.answer(text, parse_mode="HTML")
    await cb.answer()


# ─── Key reissue callbacks ───────────────────────────────────────────────────
@router.callback_query(F.data == "key:reissue:cancel")
async def reissue_cancel(cb: CallbackQuery) -> None:
    lang = await _user_lang(cb.from_user.id)
    await cb.message.edit_text(i18n.t(lang, "key_reissue_cancelled"))
    await cb.answer()


@router.callback_query(F.data == "key:reissue:confirm")
async def reissue_confirm(cb: CallbackQuery) -> None:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, cb.from_user.id)
        if user is None:
            await cb.answer("No account.", show_alert=True)
            return
        lang = i18n.normalize(user.language)
        _key, raw = await keys.reissue(db, user.id)
        await db.commit()
    await cb.message.edit_text(i18n.t(lang, "key_reissued"))
    await cb.message.answer(i18n.t(lang, "key_new", raw=raw), parse_mode="HTML")
    await cb.answer()


# ─── Device removal callbacks ────────────────────────────────────────────────
@router.callback_query(F.data.startswith("dev:remove:"))
async def device_remove(cb: CallbackQuery) -> None:
    device_id = int(cb.data.split(":")[2])
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, cb.from_user.id)
        lang = i18n.normalize(user.language if user else None)
        key = await keys.get_active_key(db, user.id) if user else None
        ok = await devices_svc.remove(db, key_id=key.id, device_id=device_id) if key else False
        await db.commit()
    await cb.answer(i18n.t(lang, "device_remove_ok") if ok else i18n.t(lang, "device_remove_fail"),
                    show_alert=not ok)
    if ok:
        await cb.message.edit_text(i18n.t(lang, "device_removed"))


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery) -> None:
    await cb.answer()


# ─── Catch-all: menu buttons → human relay → AI agent ────────────────────────
@router.message(F.text & ~F.text.startswith("/"))
async def support_or_relay(message: Message) -> None:
    text = message.text or ""

    async with SessionFactory() as db:
        user, _ = await users.get_or_create(
            db, telegram_id=message.from_user.id, username=message.from_user.username
        )
        await db.commit()
        lang = i18n.normalize(user.language)
        relaying = await handoff.is_active(user.telegram_id)

    # 1. Menu button taps route to their action (works in any language / state).
    action = i18n.button_action(text)
    if action == "human":
        await _human_flow(message)
        return
    if action == "plans":
        await show_plans(message, lang); return
    if action == "status":
        await show_status(message, lang); return
    if action == "key":
        await show_key(message, lang); return
    if action == "devices":
        await show_devices(message, lang); return
    if action == "referrals":
        await show_referrals(message, lang); return
    if action == "help":
        await show_help(message, lang); return
    if action == "language":
        await open_language(message); return

    # 2. Human handoff: relay to admins.
    if relaying:
        uname = f"@{message.from_user.username}" if message.from_user.username else "(no username)"
        await handoff.notify_admins(
            f"💬 <b>{uname}</b> (id <code>{message.from_user.id}</code>): {text}"
        )
        await message.answer(i18n.t(lang, "sent_to_team"))
        return

    # 3. AI assistant (replies in the user's chosen language).
    await message.bot.send_chat_action(message.chat.id, "typing")
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, message.from_user.id)
        result = await support.answer(db, user, text)
    await message.answer(result.reply)
    if result.needs_human:
        await _escalate(message, user, text, lang)
