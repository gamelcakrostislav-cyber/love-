"""Admin commands, gated by ADMIN_IDS.

/stats, /grant <telegram_id> <plan>, /revoke <telegram_id>, /flags,
/unflag <key_prefix|key_id>. Grants/revocations reuse the same server-side
activation/revocation services as the payment webhook.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionFactory
from app.models.abuse_event import AbuseEvent
from app.models.api_key import ApiKey
from app.models.enums import PaymentStatus, SubscriptionStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.session import Session
from app.models.subscription import Subscription
from app.models.user import User
from app.services import activation, revocation, users
from app.services.audit import record_audit
from app.bot import notify

router = Router(name="admin")


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in settings.admin_ids)


# Gate every handler in this router behind the admin check.
router.message.filter(IsAdmin())


@router.message(Command("stats"))
async def stats_cmd(message: Message) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as db:
        active_users = await db.scalar(
            select(func.count(func.distinct(Subscription.user_id))).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at > now,
            )
        )
        active_sessions = await db.scalar(
            select(func.count()).select_from(Session).where(
                Session.revoked.is_(False), Session.expires_at > now
            )
        )
        revenue = await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.PAID
            )
        )
        flagged = await db.scalar(
            select(func.count()).select_from(ApiKey).where(ApiKey.flagged.is_(True))
        )
        abuse_total = await db.scalar(select(func.count()).select_from(AbuseEvent))
    await message.answer(
        "<b>📊 Stats</b>\n"
        f"Active users: {active_users or 0}\n"
        f"Active sessions: {active_sessions or 0}\n"
        f"Revenue (paid): {revenue or 0}\n"
        f"Flagged keys: {flagged or 0}\n"
        f"Abuse events (total): {abuse_total or 0}",
        parse_mode="HTML",
    )


@router.message(Command("grant"))
async def grant_cmd(message: Message, command: CommandObject) -> None:
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer("Usage: /grant &lt;telegram_id&gt; &lt;plan&gt;", parse_mode="HTML")
        return
    telegram_id, plan_name = int(parts[0]), parts[1].lower()
    async with SessionFactory() as db:
        plan = await db.scalar(select(Plan).where(Plan.name == plan_name))
        if plan is None:
            await message.answer(f"Unknown plan '{plan_name}'.")
            return
        user, _ = await users.get_or_create(db, telegram_id=telegram_id, username=None)
        result = await activation.grant(
            db, user=user, plan=plan, payment=None, actor=f"admin:{message.from_user.id}"
        )
        await db.commit()

    if result.new_key_raw:
        await notify.send_message(
            telegram_id,
            f"🎁 You've been granted <b>{result.plan_name}</b> until "
            f"{result.expires_at:%Y-%m-%d}.\n\n"
            f"🔑 <b>Your API key (shown once):</b>\n<code>{result.new_key_raw}</code>",
        )
    else:
        await notify.send_message(
            telegram_id,
            f"🎁 Your access was granted/extended — <b>{result.plan_name}</b> until "
            f"{result.expires_at:%Y-%m-%d}.",
        )
    await message.answer(
        f"✅ Granted {result.plan_name} to {telegram_id} until {result.expires_at:%Y-%m-%d}."
    )


@router.message(Command("revoke"))
async def revoke_cmd(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Usage: /revoke &lt;telegram_id&gt;", parse_mode="HTML")
        return
    telegram_id = int(arg)
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, telegram_id)
        if user is None:
            await message.answer("No such user.")
            return
        await revocation.revoke_user(db, user_id=user.id, actor=f"admin:{message.from_user.id}")
        await db.commit()
    await message.answer(f"🚫 Revoked access for {telegram_id} (keys disabled, sessions killed).")
    await notify.send_message(telegram_id, "⚠️ Your access has been revoked. Contact support if unexpected.")


@router.message(Command("flags"))
async def flags_cmd(message: Message) -> None:
    async with SessionFactory() as db:
        flagged_keys = list(await db.scalars(
            select(ApiKey).where(ApiKey.flagged.is_(True)).order_by(ApiKey.id.desc()).limit(15)
        ))
        recent = list(await db.scalars(
            select(AbuseEvent).order_by(AbuseEvent.created_at.desc()).limit(10)
        ))
    if not flagged_keys and not recent:
        await message.answer("No flagged keys or abuse events. 🎉")
        return
    lines = ["<b>🚩 Flagged keys</b>"]
    for k in flagged_keys:
        lines.append(f"• id={k.id} prefix=<code>{k.prefix}</code> user={k.user_id}")
    lines.append("\n<b>Recent abuse events</b>")
    for e in recent:
        lines.append(f"• [{e.type}] key={e.key_id} — {e.detail or ''}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("unflag"))
async def unflag_cmd(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await message.answer("Usage: /unflag &lt;key_prefix|key_id&gt;", parse_mode="HTML")
        return
    async with SessionFactory() as db:
        if arg.isdigit():
            key = await db.scalar(select(ApiKey).where(ApiKey.id == int(arg)))
        else:
            key = await db.scalar(select(ApiKey).where(ApiKey.prefix == arg))
        if key is None:
            await message.answer("Key not found.")
            return
        key.flagged = False
        await record_audit(
            db, actor=f"admin:{message.from_user.id}", action="key_unflagged",
            target=str(key.id), meta={"prefix": key.prefix},
        )
        await db.commit()
    await message.answer(f"✅ Cleared flag on key id={key.id} (prefix {key.prefix}).")
