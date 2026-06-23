"""AI support agent backed by Claude (Anthropic).

A single Messages API call answers product/support questions, grounded in a
system prompt + the user's own subscription status, with short Redis-backed
conversation memory. The agent only *answers* — it never grants access. When the
user needs a human (asks for one, or the model can't help) the reply carries an
`<ESCALATE>` sentinel, which the bot turns into a human handoff.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.models.user import User
from app.services import keys, subscriptions

log = get_logger("support")

ESCALATE = "<ESCALATE>"
_RATE_PER_MIN = 15
_HISTORY_TTL = 3600  # keep a conversation for an hour of inactivity

SUPPORT_SYSTEM_PROMPT = """You are the friendly support assistant for an \
arbitrage tool sold through this Telegram bot. Help customers use the product \
and resolve billing/access issues.

What you can help with (and ONLY this — politely decline anything off-topic):
- Plans & pricing: trial (free, 7 days, only opportunities up to 2% \
profitability), monthly ($49 / 30 days, all opportunities), yearly ($479 / 365 \
days, all opportunities).
- Bot commands: /plans, /buy <plan>, /status, /key (show/reissue API key), \
/devices (manage devices), /help, /human (talk to a person).
- How access works: after paying, the user gets an API key (shown once). The key \
is exchanged at /auth/session for a short-lived token; the product is then called \
with that token. Each plan allows a limited number of devices and simultaneous \
sessions; a new device beyond the limit waits a 24h cooldown. Rate limits and \
anti-abuse (device binding, impossible-travel, etc.) protect accounts.
- Payments: crypto via @CryptoBot; subscription activates automatically once paid.
- Referrals: inviting people earns commission once the invited person pays.

Rules:
- Be concise, warm, and clear. Reply in the same language the user writes in.
- Answer the user directly. Do not include analysis, planning, or meta-commentary.
- Never reveal full API keys, secrets, or internal implementation details, and \
never claim you have granted access or changed a subscription — you cannot.
- If the user explicitly asks to talk to a human/agent/operator/support person, \
OR you genuinely cannot resolve their issue and they need a person, append the \
exact token <ESCALATE> as the very last characters of your reply. Otherwise never \
write that token."""


def parse_escalation(text: str) -> tuple[str, bool]:
    """Split the model reply into (clean_text, needs_human) on the sentinel."""
    if ESCALATE in text:
        return text.replace(ESCALATE, "").strip(), True
    return text.strip(), False


@dataclass
class SupportResult:
    reply: str
    needs_human: bool
    rate_limited: bool = False


def is_enabled() -> bool:
    return bool(
        settings.support_ai_enabled
        and settings.anthropic_api_key
        and settings.anthropic_api_key != "CHANGE_ME"
    )


_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic  # imported lazily; declared dep

        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def _allow_rate(telegram_id: int) -> bool:
    key = redis_keys.support_ratelimit(telegram_id)
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 60)
    return count <= _RATE_PER_MIN


async def _load_history(telegram_id: int) -> list[dict]:
    raw = await redis_client.get(redis_keys.support_history(telegram_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


async def _save_history(telegram_id: int, history: list[dict]) -> None:
    trimmed = history[-(settings.support_history_turns * 2):]
    await redis_client.set(
        redis_keys.support_history(telegram_id),
        json.dumps(trimmed),
        ex=_HISTORY_TTL,
    )


async def clear_history(telegram_id: int) -> None:
    await redis_client.delete(redis_keys.support_history(telegram_id))


async def _user_context(db: AsyncSession, user: User) -> str:
    """A short, factual status line the model can use for personal answers."""
    active = await subscriptions.get_active_with_plan(db, user.id)
    key = await keys.get_active_key(db, user.id)
    if active is None:
        sub_line = "Subscription: none active (suggest /plans)."
    else:
        sub, plan = active
        sub_line = f"Subscription: {plan.name}, expires {sub.expires_at:%Y-%m-%d}."
    key_line = f"API key prefix: {key.prefix}…" if key else "API key: not issued yet."
    return f"[Account — {sub_line} {key_line}]"


async def answer(db: AsyncSession, user: User, text: str) -> SupportResult:
    """Answer a support message. Returns reply text + whether to escalate."""
    if not is_enabled():
        return SupportResult(
            reply=(
                "🤖 The AI assistant isn't configured yet. Use /help for commands, "
                "or /human to reach a person."
            ),
            needs_human=False,
        )

    if not await _allow_rate(user.telegram_id):
        return SupportResult(
            reply="You're sending messages a bit fast — please wait a minute and try again.",
            needs_human=False,
            rate_limited=True,
        )

    history = await _load_history(user.telegram_id)
    context = await _user_context(db, user)
    messages = [
        *history,
        {"role": "user", "content": f"{context}\n\n{text}"},
    ]

    try:
        resp = await _get_client().messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=SUPPORT_SYSTEM_PROMPT,
            messages=messages,
        )
    except Exception as exc:  # noqa: BLE001 - never crash the bot on an API error
        log.warning("claude support call failed: %s", exc)
        return SupportResult(
            reply="Sorry, I'm having trouble right now. Try again shortly, or /human for a person.",
            needs_human=False,
        )

    raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
    reply, needs_human = parse_escalation(raw)
    if not reply:
        reply = "I'm not sure how to help with that — connecting you to a person."
        needs_human = True

    # Persist the turn (store the original user text, not the context-wrapped one).
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    await _save_history(user.telegram_id, history)

    log.info("support answer for %s (escalate=%s) at %s",
             user.telegram_id, needs_human, datetime.now(UTC).isoformat())
    return SupportResult(reply=reply, needs_human=needs_human)
