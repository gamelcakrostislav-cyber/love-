"""Keyboards for the client bot (localized)."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot import i18n
from app.models.device import Device
from app.models.plan import Plan


def language_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons, one per supported language."""
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"lang:set:{code}")]
        for code, name in i18n.LANGUAGES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Persistent bottom menu with localized command buttons."""
    labels = [i18n.menu_label(a, lang) for a in i18n.MENU_ORDER]
    # 2 buttons per row.
    rows = [
        [KeyboardButton(text=labels[i]), *([KeyboardButton(text=labels[i + 1])] if i + 1 < len(labels) else [])]
        for i in range(0, len(labels), 2)
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def help_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Support hub: FAQ topics, then talk-to-a-person, then 'Other' (last)."""
    rows = [
        [InlineKeyboardButton(text=i18n.t(lang, "faq_pay"), callback_data="faq:pay")],
        [InlineKeyboardButton(text=i18n.t(lang, "faq_key"), callback_data="faq:key")],
        [InlineKeyboardButton(text=i18n.t(lang, "faq_device"), callback_data="faq:device")],
        [InlineKeyboardButton(text=i18n.t(lang, "help_human_btn"), callback_data="help:human")],
        [InlineKeyboardButton(text=i18n.t(lang, "help_other_btn"), callback_data="help:other")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_keyboard(plans: list[Plan], lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=i18n.t(lang, "buy_label", name=p.name, price=p.price, currency=p.currency),
            callback_data=f"buy:{p.name}",
        )]
        for p in plans
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reissue_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=i18n.t(lang, "key_reissue_yes"), callback_data="key:reissue:confirm"),
        InlineKeyboardButton(text=i18n.t(lang, "key_reissue_cancel"), callback_data="key:reissue:cancel"),
    ]])


def devices_keyboard(devices: list[Device], lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=i18n.t(lang, "device_remove_label", fp=d.fingerprint[:12], status=d.status),
            callback_data=f"dev:remove:{d.id}",
        )]
        for d in devices
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows or [[
        InlineKeyboardButton(text="—", callback_data="noop")
    ]])
