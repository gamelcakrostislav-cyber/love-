"""Feedback routing — message formatting escapes user-supplied text."""

from __future__ import annotations

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
