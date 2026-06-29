"""Keyboards for the client bot (localized)."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot import i18n
from app.core.config import settings
from app.models.device import Device
from app.models.plan import Plan


def card_payments_enabled() -> bool:
    """Card payments need the feature flag AND a real BotFather provider token."""
    return settings.telegram_card_enabled and settings.telegram_provider_token not in ("", "CHANGE_ME")


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
    """Support hub: FAQ topics, then 'Other' (last). The operator option is NOT
    shown here — it only surfaces after the user explicitly asks for a human."""
    rows = [
        [InlineKeyboardButton(text=i18n.t(lang, "faq_pay"), callback_data="faq:pay")],
        [InlineKeyboardButton(text=i18n.t(lang, "faq_key"), callback_data="faq:key")],
        [InlineKeyboardButton(text=i18n.t(lang, "faq_device"), callback_data="faq:device")],
        [InlineKeyboardButton(text=i18n.t(lang, "help_other_btn"), callback_data="help:other")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def human_offer_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Surfaced only when a user explicitly asks for a person (keyword match)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=i18n.t(lang, "help_human_btn"), callback_data="help:human")]])


def plans_keyboard(plans: list[Plan], lang: str) -> InlineKeyboardMarkup:
    # Paid plans open the payment-method picker; the free trial keeps its
    # direct activation path.
    rows = [
        [InlineKeyboardButton(
            text=i18n.t(lang, "buy_label", name=p.name, price=p.price, currency=p.currency),
            callback_data=f"buy:{p.name}" if p.is_trial else f"pay:choose:{p.name}",
        )]
        for p in plans
    ]
    # Discount-code entry, right under the plans so it's easy to find (otherwise
    # it's only reachable by typing /promo).
    rows.append([InlineKeyboardButton(
        text=i18n.t(lang, "plans_promo_btn"), callback_data="act:promo")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_methods_keyboard(plan_name: str, lang: str) -> InlineKeyboardMarkup:
    """Offer the enabled payment methods for a plan. Crypto Pay is always on;
    Stars / card depend on their settings."""
    rows: list[list[InlineKeyboardButton]] = []
    if settings.telegram_stars_enabled:
        rows.append([InlineKeyboardButton(
            text=i18n.t(lang, "pay_stars_btn"), callback_data=f"pay:stars:{plan_name}")])
    if card_payments_enabled():
        rows.append([InlineKeyboardButton(
            text=i18n.t(lang, "pay_card_btn"), callback_data=f"pay:card:{plan_name}")])
    rows.append([InlineKeyboardButton(
        text=i18n.t(lang, "pay_crypto_btn"), callback_data=f"pay:crypto:{plan_name}")])
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
