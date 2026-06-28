"""Feedback routing — message formatting escapes user-supplied text, and
route() prefers the channel, falling back to admin DMs."""

from __future__ import annotations

from app.core.config import settings
from app.services import feedback_inbox


def test_format_body_escapes_user_text():
    body = feedback_inbox.format_body("<b>x</b> & y", telegram_id=42, username="ev<il")
    # markup in the feedback text and username is neutralized
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in body
    assert "@ev&lt;il" in body
    # the bot's own formatting stays intact
    assert "id <code>42</code>" in body


def test_format_body_handles_missing_username():
    body = feedback_inbox.format_body("hi", telegram_id=1, username=None)
    assert "(no username)" in body


async def test_route_posts_to_channel_when_send_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "feedback_channel_id", -100999)
    sent: list[tuple] = []
    admins: list[str] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))
        return True

    async def fake_notify_admins(text):
        admins.append(text)

    monkeypatch.setattr(feedback_inbox.notify, "send_message", fake_send)
    monkeypatch.setattr(feedback_inbox.handoff, "notify_admins", fake_notify_admins)

    await feedback_inbox.route("hello", telegram_id=7, username="me")

    body = feedback_inbox.format_body("hello", telegram_id=7, username="me")
    assert sent == [(-100999, body)]
    assert admins == []


async def test_route_falls_back_to_admins_when_send_fails(monkeypatch):
    monkeypatch.setattr(settings, "feedback_channel_id", -100999)
    sent: list[tuple] = []
    admins: list[str] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))
        return False

    async def fake_notify_admins(text):
        admins.append(text)

    monkeypatch.setattr(feedback_inbox.notify, "send_message", fake_send)
    monkeypatch.setattr(feedback_inbox.handoff, "notify_admins", fake_notify_admins)

    await feedback_inbox.route("hello", telegram_id=7, username="me")

    body = feedback_inbox.format_body("hello", telegram_id=7, username="me")
    assert len(sent) == 1
    assert admins == [body]


async def test_route_without_channel_uses_admins(monkeypatch):
    monkeypatch.setattr(settings, "feedback_channel_id", 0)
    sent: list[tuple] = []
    admins: list[str] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))
        return True

    async def fake_notify_admins(text):
        admins.append(text)

    monkeypatch.setattr(feedback_inbox.notify, "send_message", fake_send)
    monkeypatch.setattr(feedback_inbox.handoff, "notify_admins", fake_notify_admins)

    await feedback_inbox.route("hello", telegram_id=7, username="me")

    body = feedback_inbox.format_body("hello", telegram_id=7, username="me")
    assert sent == []
    assert admins == [body]


async def test_route_rejects_positive_channel_id(monkeypatch):
    # A positive id is a misconfig (channel ids are negative) — never post there.
    monkeypatch.setattr(settings, "feedback_channel_id", 123456)
    sent: list[tuple] = []
    admins: list[str] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))
        return True

    async def fake_notify_admins(text):
        admins.append(text)

    monkeypatch.setattr(feedback_inbox.notify, "send_message", fake_send)
    monkeypatch.setattr(feedback_inbox.handoff, "notify_admins", fake_notify_admins)

    await feedback_inbox.route("hello", telegram_id=7, username="me")

    body = feedback_inbox.format_body("hello", telegram_id=7, username="me")
    assert sent == []              # never posted to the bad id
    assert admins == [body]        # routed to admins instead
