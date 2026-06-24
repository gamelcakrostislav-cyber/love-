"""AI support agent backed by a free, OpenAI-compatible LLM (default: Groq).

A single chat-completions call answers product/support questions, grounded in a
system prompt + the user's own subscription status, with short Redis-backed
conversation memory. The agent only *answers* — it never grants access. When the
user needs a human (asks for one, or the model can't help) the reply carries an
`<ESCALATE>` sentinel, which the bot turns into a human handoff.

Works with any OpenAI-compatible endpoint (Groq, OpenAI, OpenRouter, …) via the
`SUPPORT_*` settings — no provider SDK required, just `httpx`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
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

# Display names for the user-chosen reply language (keeps support layer free of
# the bot/i18n layer). Falls back to "the user's language".
LANGUAGE_NAMES = {
    "en": "English", "ru": "Russian", "uk": "Ukrainian", "es": "Spanish", "fr": "French",
}

SUPPORT_SYSTEM_PROMPT = """You are the friendly in-app support assistant for an \
arbitrage tool sold through this Telegram bot. Your job is to help customers use \
the product, choose a plan, and resolve billing/access problems — quickly and \
warmly.

The bot has a button menu at the bottom of the chat. Whenever you tell someone to \
do something, point them at the exact button or command so they can act in one \
tap. The buttons are: 📋 Plans · 📊 Status · 🔑 Key · 📱 Devices · 🆘 Human · \
🌐 Language · ❓ Help. The matching commands are /plans, /buy <plan>, /status, \
/key, /devices, /human, /language, /help.

PRODUCT KNOWLEDGE (use this; do not invent anything beyond it):
- Plans & pricing:
  • trial — free, 7 days, shows only opportunities up to 2% profitability.
  • monthly — $49 / 30 days, all opportunities.
  • yearly — $479 / 365 days, all opportunities (best value, ~2 months free vs monthly).
  To subscribe: tap 📋 Plans (or send /buy monthly). Payment is crypto via \
@CryptoBot and the subscription activates automatically the moment payment confirms.
- Getting started after paying: tap 🔑 Key to reveal your API key (shown ONCE — \
store it safely). Paste that key into the product; it's exchanged behind the \
scenes for a short-lived token, so you never paste the long key again.
- Devices & sessions: each plan allows a limited number of devices and \
simultaneous sessions. Adding a NEW device beyond the limit triggers a 24-hour \
cooldown before it's auto-approved — this is normal anti-fraud, not a ban. Manage \
or free up a slot with 📱 Devices.
- Lost/leaked key: tap 🔑 Key → reissue. The old key stops working immediately and \
you get a fresh one (shown once).
- "Why am I blocked / why cooldown / impossible travel": the system flags unusual \
patterns (same key used from far-apart locations at once, too many devices) to \
stop key-sharing. It flags, it doesn't permanently ban. If they believe it's a \
mistake, offer 🆘 Human.
- Referrals: share your invite link; you earn commission once someone you invited \
makes their first payment.
- Checking their own account: 📊 Status shows their plan, expiry and key prefix.

RULES:
- Be concise, warm and concrete. Prefer 1–4 short sentences. Use the user's \
account context (provided to you) to personalize — e.g. if they have no \
subscription, nudge them to 📋 Plans; if theirs is expiring, mention it.
- Stay strictly on-topic (this product, its plans, access, payments, referrals). \
Politely decline anything unrelated and steer back.
- Answer directly. No analysis, planning, or meta-commentary in your reply.
- Never reveal full API keys, secrets or internal implementation details, and \
never claim you granted access or changed a subscription — you cannot do that; \
only paying (or an admin) changes access.
- If the user explicitly asks for a human/agent/operator/manager, OR you genuinely \
cannot resolve their issue and they need a person (refunds, disputes, a suspected \
wrongful flag, anything account-specific you can't verify), append the exact token \
<ESCALATE> as the very last characters of your reply. Otherwise never write that \
token."""


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
        and settings.support_api_key
        and settings.support_api_key != "CHANGE_ME"
    )


_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.support_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.support_api_key}"},
            timeout=30.0,
        )
    return _client


async def _complete(messages: list[dict]) -> str:
    """Call the OpenAI-compatible chat-completions endpoint; return reply text."""
    resp = await _get_client().post(
        "/chat/completions",
        json={
            "model": settings.support_model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.3,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"] or ""


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
    lang_name = LANGUAGE_NAMES.get(getattr(user, "language", "en") or "en")
    directive = (
        f"\n\nAlways respond in {lang_name}." if lang_name
        else "\n\nReply in the same language the user writes in."
    )
    messages = [
        {"role": "system", "content": SUPPORT_SYSTEM_PROMPT + directive},
        *history,
        {"role": "user", "content": f"{context}\n\n{text}"},
    ]

    try:
        raw = await _complete(messages)
    except Exception as exc:  # noqa: BLE001 - never crash the bot on an API error
        log.warning("support LLM call failed: %s", exc)
        return SupportResult(
            reply="Sorry, I'm having trouble right now. Try again shortly, or /human for a person.",
            needs_human=False,
        )

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
