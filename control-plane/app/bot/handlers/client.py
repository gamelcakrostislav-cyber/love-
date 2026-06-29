"""Client-facing commerce & control commands (aiogram 3.x), localized.

Free-text routing order in the catch-all: menu buttons → human relay → AI agent.
All entitlement/abuse state lives server-side; the bot only displays it and
triggers server-side actions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape as html_escape

from urllib.parse import quote

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)
from sqlalchemy import func, select

from app.bot import i18n
from app.bot.keyboards import (
    devices_keyboard,
    help_keyboard,
    human_offer_keyboard,
    language_keyboard,
    main_menu_keyboard,
    plans_keyboard,
    reissue_confirm_keyboard,
)
from app.core import redis_keys
from app.core.config import settings
from app.core.db import SessionFactory
from app.core.redis import redis_client
from app.models.enums import ReferralStatus
from app.models.feedback import Feedback
from app.models.plan import Plan
from app.models.referral import Commission, Referral
from app.services import devices as devices_svc
from app.services import (
    bot_content,
    feedback_inbox,
    growth,
    handoff,
    keys,
    payments,
    promos,
    referrals,
    subscriptions,
    support,
    users,
)

router = Router(name="client")


def _is_private(message: Message) -> bool:
    """True only for 1:1 DMs with the bot."""
    return message.chat.type == ChatType.PRIVATE


# Every handler here is a personal commerce/support conversation: it shows the
# user's own subscription, key, devices, or routes their free text to the AI.
# Scoping the whole router to private chats keeps the bot from (a) answering
# every message when it's added to a group — the AI fired on ordinary group
# chatter — and (b) leaking a user's private status into a public group. Group
# events the bot DOES care about (join requests, members joining/leaving the
# subscriber group) live in club_join.router, which uses separate update types.
router.message.filter(_is_private)


# Keyword triggers for the operator hand-off. The 'Talk to a person' button is
# NOT shown by default — it only surfaces once a user's free text contains one
# of these words (any supported language). Kept lowercase; matched on substrings
# so "operator", "оператор", "humano", etc. all hit.
_HUMAN_KEYWORDS = (
    # en
    "human", "operator", "agent", "real person", "talk to a person",
    "live person", "support team", "someone",
    # ru
    "оператор", "человек", "живой", "поддержк", "менеджер",
    # uk
    "людин", "жива людина",
    # es
    "humano", "persona real", "operador", "agente", "hablar con alguien",
    # fr
    "humain", "opérateur", "operateur", "conseiller", "vraie personne",
)


def _wants_human(text: str) -> bool:
    """True when the free text explicitly asks to reach a real person."""
    low = text.lower()
    return any(kw in low for kw in _HUMAN_KEYWORDS)


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


async def _escalate(reply_to: Message, user, last_text: str, lang: str) -> None:
    """Put a user into human-handoff mode and ping the admins (admins read EN).

    `reply_to` is the Message to answer on (a user message, or a callback's
    message), and `user` carries the real telegram_id/username — so this works
    from both the menu and the in-Help 'Talk to a person' button."""
    await handoff.enter(user.telegram_id)
    uname = f"@{user.username}" if user.username else "(no username)"
    await handoff.notify_admins(
        "🆘 <b>Support request</b>\n"
        f"From: {uname} (id <code>{user.telegram_id}</code>)\n"
        f"Message: {last_text}\n\n"
        f"Reply with <code>/reply {user.telegram_id} your message</code>, "
        f"or <code>/close {user.telegram_id}</code> to end."
    )
    await reply_to.answer(i18n.t(lang, "human_connecting"))


async def _return_to_ai(telegram_id: int) -> None:
    """Leave operator-relay mode if active.

    Engaging the self-service Help section is an explicit 'I want the assistant'
    signal, so it always pulls the user out of any operator hand-off — otherwise
    a stuck relay would forward Help questions to a human instead of the AI."""
    if await handoff.is_active(telegram_id):
        await handoff.exit(telegram_id)


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
    """Support hub: FAQ topic buttons + ✍️ ask-your-own. Opening Help returns the
    user to the AI (drops any operator relay) — no operator is pinged here."""
    await _return_to_ai(message.from_user.id)
    await message.answer(i18n.t(lang, "help_intro"), parse_mode="HTML",
                         reply_markup=help_keyboard(lang))


async def show_feedback(message: Message, lang: str) -> None:
    """Arm 'feedback mode' so the user's next message is captured as a suggestion.

    Short TTL + cancel-on-navigation (see the catch-all) keep this from later
    swallowing an ordinary question."""
    await redis_client.delete(redis_keys.promo_entry(message.from_user.id))
    await redis_client.set(redis_keys.feedback_mode(message.from_user.id), "1", ex=300)
    await message.answer(i18n.t(lang, "feedback_prompt"), parse_mode="HTML")


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
        pending = await growth.pending_count(db, user.id)
        rank_info = await growth.user_rank(db, user.id)
    rate = settings.referral_rate_blogger if is_blogger else settings.referral_rate_standard
    link = f"https://t.me/{me.username}?start={message.from_user.id}"
    body = i18n.t(lang, "referrals_block", rate=int(round(rate * 100)), link=link,
                  invited=invited, qualified=qualified, earned=f"{earned} USD")
    body += "\n" + i18n.t(lang, "referrals_more",
                          pending=pending, rank=rank_info[0] if rank_info else "—")
    share_url = (f"https://t.me/share/url?url={quote(link)}"
                 f"&text={quote(i18n.t(lang, 'referrals_share_text'))}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=i18n.t(lang, "referrals_share"), url=share_url),
        InlineKeyboardButton(text=i18n.t(lang, "leaderboard_btn"), callback_data="act:leaderboard"),
    ]])
    await message.answer(body, parse_mode="HTML", reply_markup=kb,
                         link_preview_options=LinkPreviewOptions(is_disabled=True))


async def show_leaderboard(message: Message, lang: str, telegram_id: int) -> None:
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    async with SessionFactory() as db:
        board = await growth.leaderboard(db, limit=10)
        user = await users.get_by_telegram_id(db, telegram_id)
        rank_info = await growth.user_rank(db, user.id) if user else None
    if not board:
        await message.answer(i18n.t(lang, "leaderboard_empty"), parse_mode="HTML")
        return
    lines = [i18n.t(lang, "leaderboard_header")]
    for rank, handle, earned, count in board:
        lines.append(f"{medals.get(rank, f'{rank}.')} {handle} — {earned} USD · {count}")
    text = "\n".join(lines)
    if rank_info:
        text += i18n.t(lang, "leaderboard_you", rank=rank_info[0],
                       earned=f"{rank_info[1]} USD", count=rank_info[2])
    await message.answer(text, parse_mode="HTML")


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
async def _send_welcome(target: Message, lang: str, *, returning: bool) -> None:
    """Branded welcome: the admin-set banner photo + welcome text when present,
    else the default localized greeting. Always attaches the persistent menu."""
    async with SessionFactory() as db:
        banner = await bot_content.get(db, "banner")
        custom = await bot_content.get(db, "welcome")
    text = custom or i18n.t(lang, "welcome_back" if returning else "welcome")
    kb = main_menu_keyboard(lang)
    if banner:
        await target.answer_photo(banner, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


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

    # Returning user: warm welcome-back (branded if configured) + the menu.
    await _send_welcome(message, lang, returning=True)
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
    await _send_welcome(cb.message, code, returning=False)
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


async def _set_opt_out(message: Message, value: bool, key: str) -> None:
    async with SessionFactory() as db:
        user, _ = await users.get_or_create(
            db, telegram_id=message.from_user.id, username=message.from_user.username)
        user.notifications_opt_out = value
        lang = i18n.normalize(user.language)
        await db.commit()
    await message.answer(i18n.t(lang, key), parse_mode="HTML")


@router.message(Command("leaderboard"))
async def leaderboard_cmd(message: Message) -> None:
    lang = await _user_lang(message.from_user.id)
    await show_leaderboard(message, lang, message.from_user.id)


@router.callback_query(F.data == "act:leaderboard")
async def leaderboard_callback(cb: CallbackQuery) -> None:
    lang = await _user_lang(cb.from_user.id)
    await show_leaderboard(cb.message, lang, cb.from_user.id)
    await cb.answer()


# Canned copy is only a fallback for when the AI isn't configured.
_FAQ_ANSWERS = {"pay": "faq_pay_a", "key": "faq_key_a", "device": "faq_device_a"}
# Canonical questions fed to Groq; it replies in the user's chosen language.
_FAQ_QUESTIONS = {
    "pay": "How do I pay and subscribe?",
    "key": "Where do I find my API key and how do I use it?",
    "device": "Why is my device blocked, and how do device limits work?",
}


@router.callback_query(F.data.startswith("faq:"))
async def faq_callback(cb: CallbackQuery) -> None:
    """A Help topic tap: the first answer is generated by the AI (Groq). No
    operator is ever pinged here — reaching a human needs an explicit request."""
    topic = cb.data.split(":", 1)[1]
    lang = await _user_lang(cb.from_user.id)
    question = _FAQ_QUESTIONS.get(topic)
    if question is None:
        await cb.answer()
        return
    await _return_to_ai(cb.from_user.id)
    if not support.is_enabled():
        # Graceful fallback so a topic tap still answers when the AI is off.
        await cb.message.answer(i18n.t(lang, _FAQ_ANSWERS[topic]), parse_mode="HTML")
        await cb.answer()
        return
    await cb.message.bot.send_chat_action(cb.message.chat.id, "typing")
    async with SessionFactory() as db:
        user, _ = await users.get_or_create(
            db, telegram_id=cb.from_user.id, username=cb.from_user.username)
        await db.commit()
        result = await support.answer(db, user, question)
    await cb.message.answer(result.reply)
    await cb.answer()


@router.callback_query(F.data == "help:other")
async def help_other_callback(cb: CallbackQuery) -> None:
    # Choosing to ask your own question is self-service → back to the AI.
    await _return_to_ai(cb.from_user.id)
    await cb.message.answer(
        i18n.t(await _user_lang(cb.from_user.id), "help_other_prompt"), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "help:human")
async def help_human_callback(cb: CallbackQuery) -> None:
    """The only explicit path to an operator — chosen by the user inside Help."""
    async with SessionFactory() as db:
        user, _ = await users.get_or_create(
            db, telegram_id=cb.from_user.id, username=cb.from_user.username)
        lang = i18n.normalize(user.language)
        await db.commit()
    await _escalate(cb.message, user, "(used 🗣 Talk to a person)", lang)
    await cb.answer()


@router.message(Command("feedback"))
async def feedback_cmd(message: Message) -> None:
    await show_feedback(message, await _user_lang(message.from_user.id))


@router.message(Command("mute"))
async def mute_cmd(message: Message) -> None:
    await _set_opt_out(message, True, "muted")


@router.message(Command("unmute"))
async def unmute_cmd(message: Message) -> None:
    await _set_opt_out(message, False, "unmuted")


@router.message(Command("human"))
async def human_cmd(message: Message) -> None:
    await _human_flow(message)


# ─── Promo / discount codes ──────────────────────────────────────────────────
# Terminal errors clear the armed code; a plan mismatch keeps it (it may apply to
# another plan the user buys instead).
_PROMO_ERROR_STRING = {
    promos.PromoError.INVALID: "promo_invalid",
    promos.PromoError.MAXED: "promo_maxed",
    promos.PromoError.ALREADY_USED: "promo_used",
    promos.PromoError.PLAN_MISMATCH: "promo_plan_mismatch",
}
_PROMO_TERMINAL = {
    promos.PromoError.INVALID, promos.PromoError.MAXED, promos.PromoError.ALREADY_USED,
}


async def _armed_promo(telegram_id: int) -> str | None:
    return await redis_client.get(redis_keys.promo_armed(telegram_id))


async def _disarm_promo(telegram_id: int) -> None:
    await redis_client.delete(redis_keys.promo_armed(telegram_id))


def _fmt_code(code: str) -> str:
    """A code is user-controlled and echoed into HTML-parsed replies — escape it
    and cap the length so stray markup can't break (or inject into) the message."""
    return html_escape(code[:32])


async def _apply_promo(message: Message, lang: str, raw_code: str) -> None:
    """Validate a typed discount code: arm it for the next purchase, or explain
    why it can't be used — a code that doesn't exist (or is inactive / expired /
    fully redeemed) gets a clear 'invalid code' message."""
    code = promos.normalize(raw_code)
    if not code:
        await message.answer(i18n.t(lang, "promo_enter"), parse_mode="HTML")
        return
    async with SessionFactory() as db:
        promo = await promos.get(db, code)
        ok = (
            promo is not None and promo.is_active
            and (promo.expires_at is None or promo.expires_at > datetime.now(UTC))
            and (promo.max_redemptions is None or promo.times_redeemed < promo.max_redemptions)
        )
        desc = promos.describe(promo) if promo else ""
    if not ok:
        await message.answer(i18n.t(lang, "promo_invalid", code=_fmt_code(code)), parse_mode="HTML")
        return
    await redis_client.set(redis_keys.promo_armed(message.from_user.id), code, ex=1800)
    await message.answer(i18n.t(lang, "promo_applied", code=_fmt_code(code), desc=desc),
                         parse_mode="HTML")


@router.message(Command("promo"))
async def promo_cmd(message: Message, command: CommandObject) -> None:
    """/promo [code] — apply a discount code. With a code given, validate it now;
    with none (e.g. tapped from the '/' menu), read the next message as the code."""
    lang = await _user_lang(message.from_user.id)
    code = (command.args or "").strip()
    if not code:
        # Guided entry: the next free-text message is validated as the code.
        await redis_client.delete(redis_keys.feedback_mode(message.from_user.id))
        await redis_client.set(redis_keys.promo_entry(message.from_user.id), "1", ex=300)
        await message.answer(i18n.t(lang, "promo_enter"), parse_mode="HTML")
        return
    await _apply_promo(message, lang, code)


# ─── Buy ─────────────────────────────────────────────────────────────────────
async def _do_buy(
    db, telegram_id: int, username: str | None, plan_name: str, lang: str,
    code: str | None = None,
) -> str:
    user, _ = await users.get_or_create(db, telegram_id=telegram_id, username=username)
    plan = await db.scalar(
        select(Plan).where(Plan.name == plan_name, Plan.is_active.is_(True))
    )
    if plan is None:
        return i18n.t(lang, "buy_unknown")

    # A code passed inline (/buy plan code) wins; otherwise use one armed via /promo.
    code = promos.normalize(code) if code else await _armed_promo(telegram_id)
    if code:
        result = await promos.quote(db, code=code, user_id=user.id, plan=plan)
        if isinstance(result, str):  # validation failed — `result` is the reason
            if result in _PROMO_TERMINAL:
                await _disarm_promo(telegram_id)
            return i18n.t(lang, _PROMO_ERROR_STRING[result], code=_fmt_code(code), plan=plan.name)
        _payment, pay_url = await payments.start_checkout(
            db, user=user, plan=plan, amount=result.final, promo=result.promo)
        return i18n.t(lang, "buy_invoice_promo", name=plan.name, code=_fmt_code(result.promo.code),
                      desc=result.description, original=result.original,
                      price=result.final, currency=plan.currency, url=pay_url)

    _payment, pay_url = await payments.start_checkout(db, user=user, plan=plan)
    return i18n.t(lang, "buy_invoice", name=plan.name, price=plan.price,
                  currency=plan.currency, url=pay_url)


@router.message(Command("buy"))
async def buy_cmd(message: Message, command: CommandObject) -> None:
    parts = (command.args or "").split()
    lang = await _user_lang(message.from_user.id)
    if not parts:
        await show_plans(message, lang)
        return
    plan_name = parts[0].lower()
    code = parts[1] if len(parts) > 1 else None
    async with SessionFactory() as db:
        text = await _do_buy(
            db, message.from_user.id, message.from_user.username, plan_name, lang, code)
        await db.commit()
    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "act:plans")
async def plans_callback(cb: CallbackQuery) -> None:
    """Inline '📋 Plans' button (used by win-back DMs) → show the plans list."""
    await show_plans(cb.message, await _user_lang(cb.from_user.id))
    await cb.answer()


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
    # Tapping any menu button cancels a pending feedback / promo-code capture, so
    # a message typed after browsing the menu is never mistaken for one.
    if action:
        if action != "feedback":
            await redis_client.delete(redis_keys.feedback_mode(message.from_user.id))
        await redis_client.delete(redis_keys.promo_entry(message.from_user.id))
    if action == "human":
        await _human_flow(message)
        return
    if action == "plans":
        await show_plans(message, lang)
        return
    if action == "status":
        await show_status(message, lang)
        return
    if action == "key":
        await show_key(message, lang)
        return
    if action == "devices":
        await show_devices(message, lang)
        return
    if action == "referrals":
        await show_referrals(message, lang)
        return
    if action == "help":
        await show_help(message, lang)
        return
    if action == "feedback":
        await show_feedback(message, lang)
        return
    if action == "language":
        await open_language(message)
        return

    # An active operator conversation always wins over a stale capture flag, so
    # the feedback / promo-entry captures below are skipped while relaying.
    # 1b. Feedback capture: the 💬 Feedback button armed this — store the next
    # message as a suggestion and forward it to the team.
    if not relaying and await redis_client.get(redis_keys.feedback_mode(message.from_user.id)):
        await redis_client.delete(redis_keys.feedback_mode(message.from_user.id))
        async with SessionFactory() as db:
            u = await users.get_by_telegram_id(db, message.from_user.id)
            if u is not None:
                db.add(Feedback(user_id=u.id, text=text[:4000]))
                await db.commit()
        await feedback_inbox.route(
            text, telegram_id=message.from_user.id, username=message.from_user.username)
        await message.answer(i18n.t(lang, "feedback_thanks"), parse_mode="HTML")
        return

    # 1c. Promo-code entry: /promo (no code) armed this. A real code is a single
    # short token → validate it (a non-existent code gets a clear 'invalid' reply
    # instead of hitting the AI). Empty input re-prompts and stays armed; a
    # sentence-like message means the user moved on, so cancel entry and let it
    # flow on to the AI.
    if not relaying and await redis_client.get(redis_keys.promo_entry(message.from_user.id)):
        candidate = text.strip()
        if not candidate:
            await message.answer(i18n.t(lang, "promo_enter"), parse_mode="HTML")
            return
        if " " not in candidate and len(candidate) <= 40:
            await redis_client.delete(redis_keys.promo_entry(message.from_user.id))
            await _apply_promo(message, lang, candidate)
            return
        # Doesn't look like a code — drop entry mode and fall through to the AI.
        await redis_client.delete(redis_keys.promo_entry(message.from_user.id))

    # 2. Human handoff: relay to admins.
    if relaying:
        uname = f"@{message.from_user.username}" if message.from_user.username else "(no username)"
        await handoff.notify_admins(
            f"💬 <b>{uname}</b> (id <code>{message.from_user.id}</code>): {text}"
        )
        await message.answer(i18n.t(lang, "sent_to_team"))
        return

    # 2b. Explicit operator request: only when the user's words ask for a human
    # do we surface the 'Talk to a person' button (it's never shown in Help by
    # default). One tap then escalates via the help:human callback.
    if _wants_human(text):
        await message.answer(i18n.t(lang, "human_offer"),
                             reply_markup=human_offer_keyboard(lang))
        return

    # 3. AI assistant (replies in the user's chosen language). It NEVER pings an
    # operator: reaching a human requires an explicit request (the keyword check
    # above). When the model judges a person is warranted we only tell the user
    # how to ask for one — nobody is notified until they do.
    await message.bot.send_chat_action(message.chat.id, "typing")
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, message.from_user.id)
        result = await support.answer(db, user, text)
    reply = result.reply
    if result.needs_human:
        reply += "\n\n" + i18n.t(lang, "human_hint")
    await message.answer(reply)
