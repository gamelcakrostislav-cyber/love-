"""Inline keyboards for the client bot."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.device import Device
from app.models.plan import Plan


def plans_keyboard(plans: list[Plan]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"Buy {p.name} — {p.price} {p.currency}",
            callback_data=f"buy:{p.name}",
        )]
        for p in plans
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reissue_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚠️ Yes, reissue", callback_data="key:reissue:confirm"),
        InlineKeyboardButton(text="Cancel", callback_data="key:reissue:cancel"),
    ]])


def devices_keyboard(devices: list[Device]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"🗑 Remove {d.fingerprint[:12]}… ({d.status})",
            callback_data=f"dev:remove:{d.id}",
        )]
        for d in devices
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows or [[
        InlineKeyboardButton(text="No devices yet", callback_data="noop")
    ]])
