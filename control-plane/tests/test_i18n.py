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
