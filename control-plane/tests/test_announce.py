"""Admin /announce → post into the subscriber group (arg parsing + service)."""

from __future__ import annotations

import types
from contextlib import asynccontextmanager

import pytest

from app.bot.handlers.admin import _parse_announce
from app.core.config import settings
from app.services import club

_GROUP = -1001234567890


def _enable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "bot_token", "123:real")
    monkeypatch.setattr(settings, "client_group_id", _GROUP)


class _FakeGroupBot:
    def __init__(self) -> None:
        self.sent: list[tuple] = []
        self.pinned: list[tuple] = []

    async def send_message(self, chat_id, text, message_thread_id=None):
        self.sent.append((chat_id, text, message_thread_id))
        return types.SimpleNamespace(message_id=4242)

    async def pin_chat_message(self, chat_id, message_id, disable_notification=True):
        self.pinned.append((chat_id, message_id))


def _patch_bot(monkeypatch, bot) -> None:
    @asynccontextmanager
    async def session():
        yield bot

    monkeypatch.setattr(club, "_bot", session)


# --- arg parsing (pure) ------------------------------------------------------

def test_parse_plain_message():
    assert _parse_announce("hello world") == (None, False, "hello world")


def test_parse_pin_and_topic_flags_any_order():
    assert _parse_announce("topic=12 pin Big news") == (12, True, "Big news")
    assert _parse_announce("pin topic=-5 hi") == (-5, True, "hi")


def test_parse_preserves_body_newlines_and_stops_at_first_nonflag():
    topic, pin, text = _parse_announce("pin Line one\nLine two")
    assert (topic, pin) == (None, True)
    assert text == "Line one\nLine two"  # internal newline survives


def test_parse_ignores_malformed_topic():
    # topic=abc isn't a number → it's the start of the message, not a flag.
    assert _parse_announce("topic=abc rest") == (None, False, "topic=abc rest")


def test_parse_flags_only_gives_empty_body():
    assert _parse_announce("pin") == (None, True, "")


# --- service -----------------------------------------------------------------

async def test_announce_posts_with_topic_and_pin(monkeypatch):
    _enable(monkeypatch)
    bot = _FakeGroupBot()
    _patch_bot(monkeypatch, bot)

    mid = await club.announce("<b>hi</b>", topic_id=7, pin=True)

    assert mid == 4242
    assert bot.sent == [(_GROUP, "<b>hi</b>", 7)]
    assert bot.pinned == [(_GROUP, 4242)]


async def test_announce_plain_does_not_pin(monkeypatch):
    _enable(monkeypatch)
    bot = _FakeGroupBot()
    _patch_bot(monkeypatch, bot)

    await club.announce("plain")

    assert bot.sent == [(_GROUP, "plain", None)]
    assert bot.pinned == []


async def test_announce_raises_when_group_disabled(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "CHANGE_ME")
    with pytest.raises(RuntimeError):
        await club.announce("hi")
