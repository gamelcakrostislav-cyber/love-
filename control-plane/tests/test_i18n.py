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


def test_renew_and_winback_strings_in_every_language():
    for lang in i18n.LANGUAGES:
        assert "{" not in i18n.t(lang, "renew_button", plan="monthly")
        out = i18n.t(lang, "winback", plan="monthly", days=3)
        assert "{" not in out and "}" not in out


def test_drip_digest_mute_strings_in_every_language():
    for lang in i18n.LANGUAGES:
        assert i18n.t(lang, "drip_nudge") and i18n.t(lang, "muted") and i18n.t(lang, "unmuted")
        digest = i18n.t(lang, "digest", plan="monthly", days=30, earned="9.80 USD")
        assert "{" not in digest and "}" not in digest


def test_support_hub_and_feedback_strings_in_every_language():
    # Operator is no longer a top-level menu button; Help is the support hub.
    assert "human" not in i18n.MENU_ORDER and "feedback" in i18n.MENU_ORDER
    for lang in i18n.LANGUAGES:
        assert i18n.button_action(i18n.menu_label("feedback", lang)) == "feedback"
        for k in ("help_intro", "faq_pay", "faq_pay_a", "faq_key", "faq_key_a",
                  "faq_device", "faq_device_a", "help_human_btn", "help_other_btn",
                  "help_other_prompt", "feedback_prompt", "feedback_thanks",
                  "human_offer", "human_hint"):
            assert i18n.t(lang, k)
        # human_hint is appended to a plain-text AI reply — must carry no HTML.
        assert "<" not in i18n.t(lang, "human_hint")


def test_human_keyword_surfaces_operator_offer():
    # The 'Talk to a person' button is keyword-gated: plain questions never
    # trigger it, but an explicit ask for a human (in any language) does.
    from app.bot.handlers.client import _wants_human
    assert not _wants_human("how much is the monthly plan?")
    assert not _wants_human("")
    for phrase in ("can I talk to a human?", "I need an operator",
                   "соедините с оператором", "quiero hablar con un humano",
                   "je veux parler à un humain", "хочу живу людину"):
        assert _wants_human(phrase)


def test_promo_strings_in_every_language():
    assert "promo" in i18n.COMMAND_ORDER
    for lang in i18n.LANGUAGES:
        assert i18n.t(lang, "promo_usage")
        assert "{" not in i18n.t(lang, "promo_applied", code="SAVE20", desc="20% off")
        assert "{" not in i18n.t(lang, "promo_invalid", code="SAVE20")
        assert "{" not in i18n.t(lang, "promo_used", code="SAVE20")
        assert "{" not in i18n.t(lang, "promo_plan_mismatch", code="SAVE20", plan="monthly")
        assert "{" not in i18n.t(lang, "promo_maxed", code="SAVE20")
        out = i18n.t(lang, "buy_invoice_promo", name="monthly", code="SAVE20",
                     desc="20% off", original="49.00", price="39.20",
                     currency="USD", url="https://t.me/x")
        assert "{" not in out and "}" not in out


def test_growth_strings_in_every_language():
    for lang in i18n.LANGUAGES:
        for k in ("referrals_share", "referrals_share_text", "leaderboard_btn",
                  "leaderboard_header", "leaderboard_empty"):
            assert i18n.t(lang, k)
        assert "{" not in i18n.t(lang, "referrals_more", pending=2, rank=3)
        assert "{" not in i18n.t(lang, "leaderboard_you", rank=1, earned="9.80 USD", count=2)
        assert "{" not in i18n.t(lang, "milestone", count=5)
