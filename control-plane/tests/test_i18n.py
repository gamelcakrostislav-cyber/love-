"""i18n translation lookup + menu-button routing (offline, no network)."""

from __future__ import annotations

from app.bot import i18n


def test_t_returns_localized_string():
    assert i18n.t("ru", "price_free") == "бесплатно"
    assert i18n.t("fr", "price_free") == "gratuit"
    assert i18n.t("en", "price_free") == "free"


def test_t_falls_back_to_english_for_unknown_lang():
    assert i18n.t("zz", "price_free") == "free"


def test_t_formats_kwargs():
    out = i18n.t("en", "language_set", lang="Español")
    assert out == "✅ Language set to Español."


def test_button_action_maps_labels_in_every_language():
    # The localized "Plans" label routes to the plans action in each language.
    for lang in i18n.LANGUAGES:
        label = i18n.menu_label("plans", lang)
        assert i18n.button_action(label) == "plans"
    assert i18n.button_action(i18n.menu_label("status", "uk")) == "status"
    assert i18n.button_action(i18n.menu_label("human", "es")) == "human"


def test_button_action_none_for_plain_text():
    assert i18n.button_action("how much is the monthly plan?") is None
    assert i18n.button_action("") is None


def test_command_descriptions_cover_every_language():
    # Each native "/" menu command must have a (short) description in all langs.
    for cmd in i18n.COMMAND_ORDER:
        for lang in i18n.LANGUAGES:
            desc = i18n.command_description(cmd, lang)
            assert desc and len(desc) <= 256


def test_command_description_falls_back_to_english():
    assert i18n.command_description("plans", "zz") == i18n.COMMANDS["plans"]["en"]


def test_status_block_formats_in_every_language():
    # Guards against a missing {placeholder} in any localized status string.
    for lang in i18n.LANGUAGES:
        out = i18n.t(
            lang, "status_block", plan="monthly", status="active",
            expires="2026-07-01", days_left=i18n.t(lang, "days_left", n=5), key_line="",
        )
        assert "{" not in out and "}" not in out


def test_onboarding_strings_present_in_every_language():
    for lang in i18n.LANGUAGES:
        assert i18n.t(lang, "welcome")
        assert i18n.t(lang, "welcome_back")
        assert i18n.t(lang, "getting_started")


def test_referrals_button_and_strings_in_every_language():
    assert "referrals" in i18n.MENU_ORDER and "referrals" in i18n.COMMAND_ORDER
    for lang in i18n.LANGUAGES:
        assert i18n.button_action(i18n.menu_label("referrals", lang)) == "referrals"
        block = i18n.t(lang, "referrals_block", rate=20, link="https://t.me/b?start=1",
                       invited=3, qualified=1, earned="12.50 USD")
        assert "{" not in block and "}" not in block


def test_reminder_string_formats_in_every_language():
    for lang in i18n.LANGUAGES:
        out = i18n.t(lang, "reminder_expiring", plan="monthly", days=2, date="2026-07-01")
        assert "{" not in out and "}" not in out
