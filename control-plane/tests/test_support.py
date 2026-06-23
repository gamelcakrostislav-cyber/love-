"""Escalation-sentinel parsing for the AI support agent (offline, no network)."""

from __future__ import annotations

from app.services.support import ESCALATE, parse_escalation


def test_no_sentinel_means_no_escalation():
    reply, needs_human = parse_escalation("Here's how to buy: use /buy monthly.")
    assert needs_human is False
    assert reply == "Here's how to buy: use /buy monthly."


def test_sentinel_triggers_escalation_and_is_stripped():
    reply, needs_human = parse_escalation(f"Let me get someone for you. {ESCALATE}")
    assert needs_human is True
    assert ESCALATE not in reply
    assert reply == "Let me get someone for you."


def test_sentinel_with_trailing_whitespace():
    reply, needs_human = parse_escalation(f"One moment.{ESCALATE}\n  ")
    assert needs_human is True
    assert reply == "One moment."
