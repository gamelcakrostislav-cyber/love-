"""Client-facing commerce & control commands (aiogram 3.x).

Commands: /start, /plans, /buy <plan>, /status, /key, /devices, /help.
All entitlement/abuse state lives server-side; the bot only displays it and
triggers server-side actions.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards import (
    devices_keyboard,
    plans_keyboard,
    reissue_confirm_keyboard,
)
from app.core.db import SessionFactory
from app.models.plan import Plan
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

HELP_TEXT = (
    "<b>Commands</b>\n"
    "/plans — list subscription plans\n"
    "/buy &lt;plan&gt; — purchase a plan\n"
    "/status — your subscription & expiry\n"
    "/key — show your API key prefix / reissue\n"
    "/devices — manage registered devices\n"
    "/human — talk to a real person\n"
    "/help — this message\n\n"
    "💬 You can also just <b>ask me a question</b> in plain text — the AI assistant "
    "will help."
)


async def _escalate(message: Message, user, last_text: str) -> None:
    """Put a user into human-handoff mode and ping the admins."""
    await handoff.enter(user.telegram_id)
    uname = f"@{message.from_user.username}" if message.from_user.username else "(no username)"
    await handoff.notify_admins(
        "🆘 <b>Support request</b>\n"
        f"From: {uname} (id <code>{user.telegram_id}</code>)\n"
        f"Message: {last_text}\n\n"
        f"Reply with <code>/reply {user.telegram_id} your message</code>, "
        f"or <code>/close {user.telegram_id}</code> to end."
    )
    await message.answer(
        "🧑‍💼 Connecting you to a person — someone will reply here shortly. "
        "Anything you send now goes straight to our team."
    )


async def _active_plans(db) -> list[Plan]:
    result = await db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price))
    return list(result)


@router.message(CommandStart(deep_link=True))
async def start_with_ref(message: Message, command: CommandObject) -> None:
    """/start <referrer_telegram_id> — provision user and capture referral."""
    async with SessionFactory() as db:
        user, created = await users.get_or_create(
            db, telegram_id=message.from_user.id, username=message.from_user.username
        )
        ref_note = ""
        payload = (command.args or "").strip()
        if created and payload.isdigit():
            referral = await referrals.attach(
                db, referred_user=user, referrer_telegram_id=int(payload)
            )
            if referral is not None:
                ref_note = "\n\n🎁 Referral applied — your inviter earns a reward once you subscribe."
        await db.commit()
    await message.answer(
        f"👋 Welcome to the arbitrage control plane.{ref_note}\n\n{HELP_TEXT}",
        parse_mode="HTML",
    )


@router.message(CommandStart())
async def start(message: Message) -> None:
    async with SessionFactory() as db:
        await users.get_or_create(
            db, telegram_id=message.from_user.id, username=message.from_user.username
        )
        await db.commit()
    await message.answer(f"👋 Welcome to the arbitrage control plane.\n\n{HELP_TEXT}",
                         parse_mode="HTML")


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("plans"))
async def plans_cmd(message: Message) -> None:
    async with SessionFactory() as db:
        plans = await _active_plans(db)
    lines = ["<b>Plans</b>"]
    for p in plans:
        tier = "trial (≤2% opportunities)" if p.is_trial else "all opportunities"
        price = "free" if p.price == 0 else f"{p.price} {p.currency}"
        lines.append(
            f"\n• <b>{p.name}</b> — {price} / {p.duration_days}d\n"
            f"  {tier}; {p.max_devices} device(s), "
            f"{p.max_concurrent_sessions} session(s), {p.rate_limit_per_min}/min"
        )
    await message.answer("\n".join(lines), parse_mode="HTML",
                         reply_markup=plans_keyboard(plans))


async def _do_buy(db, telegram_id: int, username: str | None, plan_name: str) -> str:
    user, _ = await users.get_or_create(db, telegram_id=telegram_id, username=username)
    plan = await db.scalar(
        select(Plan).where(Plan.name == plan_name, Plan.is_active.is_(True))
    )
    if plan is None:
        return f"Unknown plan '{plan_name}'. See /plans."
    _payment, pay_url = await payments.start_checkout(db, user=user, plan=plan)
    return (
        f"🧾 Invoice for <b>{plan.name}</b> ({plan.price} {plan.currency}).\n"
        f"Pay here: {pay_url}\n\n"
        f"Your subscription activates automatically once payment is confirmed."
    )


@router.message(Command("buy"))
async def buy_cmd(message: Message, command: CommandObject) -> None:
    plan_name = (command.args or "").strip().lower()
    if not plan_name:
        await message.answer("Usage: /buy &lt;plan&gt; (e.g. /buy monthly). See /plans.",
                             parse_mode="HTML")
        return
    async with SessionFactory() as db:
        text = await _do_buy(db, message.from_user.id, message.from_user.username, plan_name)
        await db.commit()
    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("buy:"))
async def buy_callback(cb: CallbackQuery) -> None:
    plan_name = cb.data.split(":", 1)[1]
    async with SessionFactory() as db:
        text = await _do_buy(db, cb.from_user.id, cb.from_user.username, plan_name)
        await db.commit()
    await cb.message.answer(text, parse_mode="HTML")
    await cb.answer()


@router.message(Command("status"))
async def status_cmd(message: Message) -> None:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, message.from_user.id)
        if user is None:
            await message.answer("No account yet. Send /start.")
            return
        active = await subscriptions.get_active_with_plan(db, user.id)
        key = await keys.get_active_key(db, user.id)
    if active is None:
        await message.answer("No active subscription. See /plans to subscribe.")
        return
    sub, plan = active
    key_line = f"\nAPI key: <code>{key.prefix}…</code>" if key else "\nNo API key yet."
    await message.answer(
        f"<b>Subscription</b>\n"
        f"Plan: {plan.name}\n"
        f"Status: {sub.status}\n"
        f"Expires: {sub.expires_at:%Y-%m-%d %H:%M UTC}"
        f"{key_line}",
        parse_mode="HTML",
    )


@router.message(Command("key"))
async def key_cmd(message: Message) -> None:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, message.from_user.id)
        key = await keys.get_active_key(db, user.id) if user else None
    if key is None:
        await message.answer("You have no active API key. Subscribe via /plans first.")
        return
    await message.answer(
        f"🔑 API key prefix: <code>{key.prefix}…</code>\n"
        f"The full key is shown only once at issue time.\n\n"
        f"Reissuing <b>disables the current key</b> immediately.",
        parse_mode="HTML",
        reply_markup=reissue_confirm_keyboard(),
    )


@router.callback_query(F.data == "key:reissue:cancel")
async def reissue_cancel(cb: CallbackQuery) -> None:
    await cb.message.edit_text("Reissue cancelled. Your current key is unchanged.")
    await cb.answer()


@router.callback_query(F.data == "key:reissue:confirm")
async def reissue_confirm(cb: CallbackQuery) -> None:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, cb.from_user.id)
        if user is None:
            await cb.answer("No account.", show_alert=True)
            return
        _key, raw = await keys.reissue(db, user.id)
        await db.commit()
    await cb.message.edit_text("✅ Key reissued. The old key is now disabled.")
    await cb.message.answer(
        f"🔑 <b>Your new API key (shown once):</b>\n<code>{raw}</code>\n\n"
        f"Store it securely — it will not be shown again.",
        parse_mode="HTML",
    )
    await cb.answer()


@router.message(Command("devices"))
async def devices_cmd(message: Message) -> None:
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, message.from_user.id)
        key = await keys.get_active_key(db, user.id) if user else None
        device_list = await devices_svc.list_for_key(db, key.id) if key else []
    if not key:
        await message.answer("No API key yet. Subscribe via /plans first.")
        return
    if not device_list:
        await message.answer("No registered devices. They appear after your first session.")
        return
    lines = ["<b>Registered devices</b>"]
    for d in device_list:
        lines.append(f"• <code>{d.fingerprint[:16]}…</code> — {d.status}")
    lines.append("\nRemove one to free a device slot:")
    await message.answer("\n".join(lines), parse_mode="HTML",
                         reply_markup=devices_keyboard(device_list))


@router.callback_query(F.data.startswith("dev:remove:"))
async def device_remove(cb: CallbackQuery) -> None:
    device_id = int(cb.data.split(":")[2])
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, cb.from_user.id)
        key = await keys.get_active_key(db, user.id) if user else None
        ok = await devices_svc.remove(db, key_id=key.id, device_id=device_id) if key else False
        await db.commit()
    await cb.answer("Removed — slot freed." if ok else "Could not remove.", show_alert=not ok)
    if ok:
        await cb.message.edit_text("Device removed. A slot is now free for a new device.")


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.message(Command("human"))
async def human_cmd(message: Message) -> None:
    """Explicitly request a human; relays subsequent messages to admins."""
    async with SessionFactory() as db:
        user, _ = await users.get_or_create(
            db, telegram_id=message.from_user.id, username=message.from_user.username
        )
        await db.commit()
    await _escalate(message, user, "(used /human)")


# Catch-all: plain text that isn't a command. Registered LAST so commands win.
@router.message(F.text & ~F.text.startswith("/"))
async def support_or_relay(message: Message) -> None:
    text = message.text or ""
    async with SessionFactory() as db:
        user, _ = await users.get_or_create(
            db, telegram_id=message.from_user.id, username=message.from_user.username
        )
        await db.commit()

        # In a human handoff: relay the message to admins instead of the AI.
        if await handoff.is_active(user.telegram_id):
            uname = f"@{message.from_user.username}" if message.from_user.username else "(no username)"
            await handoff.notify_admins(
                f"💬 <b>{uname}</b> (id <code>{user.telegram_id}</code>): {text}"
            )
            await message.answer("✅ Sent to our team.")
            return

        # Otherwise let the AI assistant answer.
        await message.bot.send_chat_action(message.chat.id, "typing")
        result = await support.answer(db, user, text)

    await message.answer(result.reply)
    if result.needs_human:
        await _escalate(message, user, text)
