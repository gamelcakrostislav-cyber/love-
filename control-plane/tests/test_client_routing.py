"""The client router is private-chat only — it must never answer group chatter."""

from __future__ import annotations

import types

from app.bot.handlers import client


def _msg(chat_type: str):
    return types.SimpleNamespace(chat=types.SimpleNamespace(type=chat_type))


def test_is_private_only_true_for_dm():
    assert client._is_private(_msg("private")) is True
    assert client._is_private(_msg("group")) is False
    assert client._is_private(_msg("supergroup")) is False
    assert client._is_private(_msg("channel")) is False


def _registered_filter_callbacks():
    """The callables aiogram will run as root filters for client messages.

    Router-level filters live on the observer's root handler in current aiogram
    (`_handler.filters`); fall back to a plain `.filters` for older layouts so
    this stays robust across 3.7+ patch releases."""
    obs = client.router.message
    holders = []
    handler = getattr(obs, "_handler", None)
    if handler is not None and getattr(handler, "filters", None):
        holders.extend(handler.filters)
    if getattr(obs, "filters", None):
        holders.extend(obs.filters)
    return [getattr(h, "callback", h) for h in holders]


def test_router_registers_the_private_guard():
    # If this filter is ever dropped, the bot starts replying to every group
    # message again (and leaking private status) — keep it wired on the router.
    assert client._is_private in _registered_filter_callbacks()
