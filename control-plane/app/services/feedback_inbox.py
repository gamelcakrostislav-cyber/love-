"""Route user feedback to a dedicated inbox.

When FEEDBACK_CHANNEL_ID is set, every submitted suggestion is posted to that
private group/channel so admins can review and track ideas in one place;
otherwise it falls back to DMing each admin (the original behaviour). The
feedback row is still stored in the DB either way (the caller does that).
"""

from __future__ import annotations

from html import escape

from app.bot import notify
from app.core.config import settings
from app.services import handoff


def format_body(text: str, *, telegram_id: int, username: str | None) -> str:
    """Build the HTML message — user-supplied text is escaped to prevent markup
    injection / broken rendering."""
    uname = f"@{escape(username)}" if username else "(no username)"
    return (
        f"💡 <b>Feedback</b> from {uname} (id <code>{telegram_id}</code>):\n"
        f"{escape(text)}"
    )


async def route(text: str, *, telegram_id: int, username: str | None) -> None:
    body = format_body(text, telegram_id=telegram_id, username=username)
    if settings.feedback_channel_id:
        await notify.send_message(settings.feedback_channel_id, body)
    else:
        await handoff.notify_admins(body)
