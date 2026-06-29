"""Lightweight i18n for the client bot (en / ru / uk / es / fr).

`t(lang, key, **kwargs)` returns a translated string (English fallback).
Menu button labels double as routing keys: `button_action(text)` maps any
localized label back to its action so taps work in every language.
"""

from __future__ import annotations

LANGUAGES: dict[str, str] = {
    "en": "English",
    "ru": "Русский",
    "uk": "Українська",
    "es": "Español",
    "fr": "Français",
}
DEFAULT_LANG = "en"


def normalize(lang: str | None) -> str:
    return lang if lang in LANGUAGES else DEFAULT_LANG


# ─── Menu buttons (persistent reply keyboard) ────────────────────────────────
# action -> {lang: label}. Emoji stays constant; only the word is translated.
_MENU: dict[str, dict[str, str]] = {
    "plans":    {"en": "📋 Plans", "ru": "📋 Тарифы", "uk": "📋 Тарифи", "es": "📋 Planes", "fr": "📋 Forfaits"},
    "status":   {"en": "📊 Status", "ru": "📊 Статус", "uk": "📊 Статус", "es": "📊 Estado", "fr": "📊 Statut"},
    "key":      {"en": "🔑 Key", "ru": "🔑 Ключ", "uk": "🔑 Ключ", "es": "🔑 Clave", "fr": "🔑 Clé"},
    "devices":  {"en": "📱 Devices", "ru": "📱 Устройства", "uk": "📱 Пристрої", "es": "📱 Dispositivos", "fr": "📱 Appareils"},
    "referrals": {"en": "🎁 Referrals", "ru": "🎁 Рефералы", "uk": "🎁 Реферали", "es": "🎁 Referidos", "fr": "🎁 Parrainage"},
    "help":     {"en": "❓ Help", "ru": "❓ Помощь", "uk": "❓ Допомога", "es": "❓ Ayuda", "fr": "❓ Aide"},
    "feedback": {"en": "💬 Feedback", "ru": "💬 Отзыв", "uk": "💬 Відгук", "es": "💬 Sugerencias", "fr": "💬 Avis"},
    "language": {"en": "🌐 Language", "ru": "🌐 Язык", "uk": "🌐 Мова", "es": "🌐 Idioma", "fr": "🌐 Langue"},
    # 'human' is no longer a menu button — reaching an operator is an explicit
    # choice inside Help. The label is kept for the in-Help button text.
    "human":    {"en": "🆘 Human", "ru": "🆘 Оператор", "uk": "🆘 Оператор", "es": "🆘 Persona", "fr": "🆘 Humain"},
}
MENU_ORDER = ["plans", "status", "key", "devices", "referrals", "help", "feedback", "language"]

_LABEL_TO_ACTION = {label: action for action, m in _MENU.items() for label in m.values()}


# ─── Native command menu (BotFather "/" menu) ────────────────────────────────
# command -> {lang: short description}. Registered via bot.set_my_commands per
# language so Telegram shows a localized menu when the user taps the "/" button.
COMMANDS: dict[str, dict[str, str]] = {
    "start":    {"en": "Start / choose language", "ru": "Старт / выбрать язык", "uk": "Старт / обрати мову", "es": "Iniciar / elegir idioma", "fr": "Démarrer / choisir la langue"},
    "plans":    {"en": "See subscription plans", "ru": "Посмотреть тарифы", "uk": "Переглянути тарифи", "es": "Ver planes", "fr": "Voir les forfaits"},
    "status":   {"en": "Your subscription & expiry", "ru": "Ваша подписка и срок", "uk": "Ваша підписка та термін", "es": "Tu suscripción y vencimiento", "fr": "Votre abonnement et échéance"},
    "key":      {"en": "Show / reissue API key", "ru": "Показать / перевыпустить ключ", "uk": "Показати / перевипустити ключ", "es": "Ver / reemitir clave API", "fr": "Afficher / réémettre la clé API"},
    "devices":  {"en": "Manage your devices", "ru": "Управление устройствами", "uk": "Керування пристроями", "es": "Gestionar dispositivos", "fr": "Gérer vos appareils"},
    "referrals": {"en": "Your invite link & earnings", "ru": "Ваша ссылка и доход", "uk": "Ваше посилання та дохід", "es": "Tu enlace y ganancias", "fr": "Votre lien et vos gains"},
    "help":     {"en": "Help & support", "ru": "Помощь и поддержка", "uk": "Допомога та підтримка", "es": "Ayuda y soporte", "fr": "Aide et support"},
    "feedback": {"en": "Send feedback / ideas", "ru": "Оставить отзыв / идеи", "uk": "Залишити відгук / ідеї", "es": "Enviar sugerencias / ideas", "fr": "Envoyer un avis / des idées"},
    "promo":    {"en": "Apply a discount code", "ru": "Применить промокод", "uk": "Застосувати промокод", "es": "Aplicar un código de descuento", "fr": "Appliquer un code promo"},
    "language": {"en": "Change language", "ru": "Сменить язык", "uk": "Змінити мову", "es": "Cambiar idioma", "fr": "Changer de langue"},
}
COMMAND_ORDER = ["start", "plans", "status", "key", "devices", "referrals", "help", "feedback", "promo", "language"]


def command_description(command: str, lang: str) -> str:
    m = COMMANDS[command]
    return m.get(normalize(lang), m["en"])


def menu_label(action: str, lang: str) -> str:
    m = _MENU[action]
    return m.get(normalize(lang), m["en"])


def button_action(text: str) -> str | None:
    return _LABEL_TO_ACTION.get((text or "").strip())


# ─── Strings ─────────────────────────────────────────────────────────────────
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "choose_language": "🌐 Please choose your language:",
        "language_set": "✅ Language set to {lang}.",
        "welcome": "👋 <b>Welcome!</b> This bot manages your arbitrage subscription, API key and devices.\n\n🎁 New here? Tap 📋 <b>Plans</b> — the trial is free. Or just type a question and the assistant will help.",
        "welcome_back": "👋 <b>Welcome back!</b> Tap a button below, or ask me anything.",
        "getting_started": (
            "<b>🚀 Quick start</b>\n"
            "1️⃣ Tap 📋 <b>Plans</b> and choose one — start free with the trial.\n"
            "2️⃣ Tap 🔑 <b>Key</b> to get your API key (shown once).\n"
            "3️⃣ Paste the key into the product to go live.\n\n"
            "Stuck on any step? Just type your question here. 💬"
        ),
        "days_left": "{n} days left",
        "expires_soon": "⏳ expires in {n} days",
        "help": (
            "<b>What you can do</b>\n"
            "📋 Plans — see subscription plans\n"
            "📊 Status — your subscription & expiry\n"
            "🔑 Key — show/reissue your API key\n"
            "📱 Devices — manage your devices\n"
            "🆘 Human — talk to a real person\n"
            "🌐 Language — change language\n\n"
            "💬 You can also just <b>ask a question</b> in plain text — the assistant will help."
        ),
        "referrals_block": (
            "🎁 <b>Referrals</b>\n"
            "Share your link and earn <b>{rate}%</b> when someone you invite subscribes.\n\n"
            "🔗 <b>Your invite link:</b>\n{link}\n\n"
            "👥 Invited: <b>{invited}</b>\n✅ Paid: <b>{qualified}</b>\n💰 Earned: <b>{earned}</b>"
        ),
        "reminder_expiring": (
            "⏳ Your <b>{plan}</b> subscription expires in <b>{days}</b> day(s) — on {date}.\n"
            "Tap below to renew in one tap and keep your access."
        ),
        "renew_button": "🔄 Renew {plan}",
        "winback": (
            "👋 We miss you! Your <b>{plan}</b> access ended {days} day(s) ago.\n"
            "Come back any time — tap 📋 Plans to pick up where you left off."
        ),
        "plans_header": "<b>📋 Choose a plan</b>\nTap a button below to subscribe. Payment is in crypto and activates automatically.",
        "tier_trial": "trial (opportunities up to 2%)",
        "tier_all": "all opportunities",
        "price_free": "free",
        "plan_line": "\n• <b>{name}</b> — {price} / {days}d\n  {tier}; {devices} device(s), {sessions} session(s), {rate}/min",
        "buy_label": "Buy {name} — {price} {currency}",
        "buy_unknown": "Unknown plan. Tap 📋 Plans.",
        "buy_invoice": "🧾 Invoice for <b>{name}</b> ({price} {currency}).\nPay here: {url}\n\nYour subscription activates automatically once payment is confirmed.",
        "status_none": "You don't have an active subscription yet.\nTap 📋 <b>Plans</b> to get started — the trial is free.",
        "status_block": "<b>📊 Your subscription</b>\nPlan: <b>{plan}</b>\nStatus: {status}\nExpires: {expires} · {days_left}{key_line}",
        "status_key_line": "\nAPI key: <code>{prefix}…</code>",
        "status_no_key": "\nNo API key yet.",
        "key_none": "You have no active API key. Subscribe via 📋 Plans first.",
        "key_show": "🔑 API key prefix: <code>{prefix}…</code>\nThe full key is shown only once at issue time.\n\nReissuing <b>disables the current key</b> immediately.",
        "key_reissue_yes": "⚠️ Yes, reissue",
        "key_reissue_cancel": "Cancel",
        "key_reissue_cancelled": "Reissue cancelled. Your current key is unchanged.",
        "key_reissued": "✅ Key reissued. The old key is now disabled.",
        "key_new": "🔑 <b>Your new API key (shown once):</b>\n<code>{raw}</code>\n\nStore it securely — it will not be shown again.",
        "devices_none_key": "No API key yet. Subscribe via 📋 Plans first.",
        "devices_empty": "No registered devices. They appear after your first session.",
        "devices_header": "<b>Registered devices</b>",
        "devices_remove_hint": "\nRemove one to free a device slot:",
        "device_remove_label": "🗑 Remove {fp}… ({status})",
        "device_removed": "Device removed. A slot is now free for a new device.",
        "device_remove_ok": "Removed — slot freed.",
        "device_remove_fail": "Could not remove.",
        "human_connecting": "🧑‍💼 Connecting you to a person — someone will reply here shortly. Anything you send now goes straight to our team.",
        "sent_to_team": "✅ Sent to our team.",
        "no_account": "No account yet. Send /start.",
        "drip_nudge": "👋 Still deciding? Start <b>free</b> with the 7-day trial — see real arbitrage opportunities with no risk. Tap 📋 Plans whenever you're ready.",
        "digest": "📊 <b>Your weekly summary</b>\nPlan: <b>{plan}</b> · {days} days left\nReferral earnings: <b>{earned}</b>\n\nKeep it up! Invite friends with 🎁 Referrals to earn more.",
        "muted": "🔕 You'll no longer get promotional messages. Important ones (payments, expiry) still come through. Send /unmute to turn them back on.",
        "unmuted": "🔔 Promotional messages are back on. Send /mute to stop them anytime.",
        "referrals_more": "⏳ Pending: <b>{pending}</b>  ·  🏆 Rank: <b>#{rank}</b>",
        "referrals_share": "📤 Share my link",
        "referrals_share_text": "I'm using this arbitrage tool — start free and find profitable opportunities 🚀",
        "leaderboard_btn": "🏆 Leaderboard",
        "leaderboard_header": "🏆 <b>Top referrers</b> (by earnings)",
        "leaderboard_you": "\n— — —\n🫵 <b>You</b>: #{rank} · {earned} · {count} paid",
        "leaderboard_empty": "No paid referrals yet — be the first! Tap 🎁 Referrals to get your link.",
        "milestone": "🎉 <b>Milestone reached!</b> You've brought in <b>{count}</b> paying customer(s). Keep sharing your link to earn more! 🚀",
        "help_intro": "❓ <b>Help &amp; support</b>\nPick a topic below, or tap ✍️ to ask your own question.",
        "faq_pay": "💳 How do I pay?",
        "faq_pay_a": "Tap 📋 <b>Plans</b>, choose a plan, and pay in crypto via @CryptoBot — your subscription activates automatically once paid. The 7-day trial is free!",
        "faq_key": "🔑 My API key",
        "faq_key_a": "After subscribing, tap 🔑 <b>Key</b> to reveal your API key (shown once) and paste it into the product. Lost it? Tap 🔑 Key → reissue to get a new one.",
        "faq_device": "📱 Device blocked?",
        "faq_device_a": "Adding a new device beyond your plan's limit triggers a 24h cooldown — that's anti-fraud protection, not a ban. Manage your devices with 📱 <b>Devices</b>.",
        "help_human_btn": "🗣 Talk to a person",
        "help_other_btn": "✍️ Ask my own question",
        "help_other_prompt": "💬 Go ahead — type your question and our assistant will help.",
        "feedback_prompt": "💬 <b>We'd love your ideas!</b> Type your suggestion in your <b>next message</b> and it goes straight to our team. (To ask a question instead, tap any menu button or use ❓ Help.)",
        "feedback_thanks": "✅ Thank you! Your feedback was sent to our team. 🙏",
        "human_offer": "🗣 It sounds like you'd like to talk to a real person. Tap below to connect — or just keep typing and the assistant will help.",
        "human_hint": "💬 Prefer a real person? Just type: human support",
        "promo_usage": "🏷 <b>Discount code</b>\nSend <code>/promo YOURCODE</code> to apply a code, then tap 📋 Plans and Buy.",
        "promo_enter": "🏷 <b>Discount code</b>\nSend your code in your <b>next message</b> and I'll check it. (Tap any menu button to cancel.)",
        "promo_applied": "✅ Promo <b>{code}</b> applied — {desc}. Tap 📋 Plans and Buy to use it (valid for 30 min).",
        "promo_invalid": "❌ Code <b>{code}</b> isn't valid or has expired.",
        "promo_used": "❌ You've already used the code <b>{code}</b>.",
        "promo_plan_mismatch": "❌ Code <b>{code}</b> doesn't apply to the {plan} plan.",
        "promo_maxed": "❌ Code <b>{code}</b> has reached its redemption limit.",
        "buy_invoice_promo": "🧾 Invoice for <b>{name}</b>\n💸 <b>{code}</b> ({desc}): <s>{original} {currency}</s> → <b>{price} {currency}</b>\nPay here: {url}\n\nYour subscription activates automatically once payment is confirmed.",
        "pay_method_prompt": "💳 How would you like to pay for <b>{plan}</b>?",
        "pay_stars_btn": "⭐ Telegram Stars",
        "pay_card_btn": "💳 Bank card",
        "pay_crypto_btn": "🪙 Crypto (@CryptoBot)",
        "pay_invoice_desc": "{plan} subscription — {days} days of full access to all arbitrage opportunities.",
        "pay_confirmed_key": "✅ Payment confirmed — <b>{plan}</b> active until {date}.\n\n🔑 <b>Your API key (shown once):</b>\n<code>{apikey}</code>\n\nStore it securely — it won't be shown again.",
        "pay_confirmed_renew": "✅ Payment confirmed — <b>{plan}</b> extended until {date}. Your existing API key stays valid.",
        "club_invite": "👥 <b>Members chat</b>\nYour subscription unlocks our private subscriber group. Tap to join — I'll let you in:\n{link}",
        "club_removed": "👋 Your access to the members chat ended with your subscription. Renew any time — tap 📋 Plans — and you'll get a fresh invite.",
        "club_declined": "🔒 I can't add you to the members chat — your subscription isn't active. Tap 📋 Plans to subscribe and I'll send you your own invite link.",
    },
    "ru": {
        "choose_language": "🌐 Пожалуйста, выберите язык:",
        "language_set": "✅ Язык установлен: {lang}.",
        "welcome": "👋 <b>Добро пожаловать!</b> Этот бот управляет вашей подпиской, API-ключом и устройствами.\n\n🎁 Впервые? Нажмите 📋 <b>Тарифы</b> — пробный период бесплатный. Или просто напишите вопрос, и ассистент поможет.",
        "welcome_back": "👋 <b>С возвращением!</b> Нажмите кнопку ниже или задайте любой вопрос.",
        "getting_started": (
            "<b>🚀 Быстрый старт</b>\n"
            "1️⃣ Нажмите 📋 <b>Тарифы</b> и выберите план — начните бесплатно с пробного.\n"
            "2️⃣ Нажмите 🔑 <b>Ключ</b>, чтобы получить API-ключ (показывается один раз).\n"
            "3️⃣ Вставьте ключ в продукт — и всё готово.\n\n"
            "Застряли на каком-то шаге? Просто напишите вопрос здесь. 💬"
        ),
        "days_left": "осталось дней: {n}",
        "expires_soon": "⏳ истекает через {n} дн.",
        "help": (
            "<b>Что можно сделать</b>\n"
            "📋 Тарифы — посмотреть планы подписки\n"
            "📊 Статус — ваша подписка и срок действия\n"
            "🔑 Ключ — показать/перевыпустить API-ключ\n"
            "📱 Устройства — управление устройствами\n"
            "🆘 Оператор — связаться с человеком\n"
            "🌐 Язык — сменить язык\n\n"
            "💬 Можно просто <b>задать вопрос</b> текстом — ассистент поможет."
        ),
        "referrals_block": (
            "🎁 <b>Рефералы</b>\n"
            "Делитесь ссылкой и получайте <b>{rate}%</b>, когда приглашённый оформляет подписку.\n\n"
            "🔗 <b>Ваша реферальная ссылка:</b>\n{link}\n\n"
            "👥 Приглашено: <b>{invited}</b>\n✅ Оплатили: <b>{qualified}</b>\n💰 Заработано: <b>{earned}</b>"
        ),
        "reminder_expiring": (
            "⏳ Ваша подписка <b>{plan}</b> истекает через <b>{days}</b> дн. — {date}.\n"
            "Нажмите ниже, чтобы продлить в один тап и сохранить доступ."
        ),
        "renew_button": "🔄 Продлить {plan}",
        "winback": (
            "👋 Мы скучаем! Ваш доступ <b>{plan}</b> закончился {days} дн. назад.\n"
            "Возвращайтесь в любой момент — нажмите 📋 Тарифы, чтобы продолжить."
        ),
        "plans_header": "<b>📋 Выберите тариф</b>\nНажмите кнопку ниже, чтобы оформить. Оплата в крипте, активация автоматическая.",
        "tier_trial": "пробный (возможности до 2%)",
        "tier_all": "все возможности",
        "price_free": "бесплатно",
        "plan_line": "\n• <b>{name}</b> — {price} / {days}д\n  {tier}; устройств: {devices}, сессий: {sessions}, {rate}/мин",
        "buy_label": "Купить {name} — {price} {currency}",
        "buy_unknown": "Неизвестный план. Нажмите 📋 Тарифы.",
        "buy_invoice": "🧾 Счёт за <b>{name}</b> ({price} {currency}).\nОплатить: {url}\n\nПодписка активируется автоматически после оплаты.",
        "status_none": "У вас пока нет активной подписки.\nНажмите 📋 <b>Тарифы</b>, чтобы начать — пробный бесплатный.",
        "status_block": "<b>📊 Ваша подписка</b>\nПлан: <b>{plan}</b>\nСтатус: {status}\nДействует до: {expires} · {days_left}{key_line}",
        "status_key_line": "\nAPI-ключ: <code>{prefix}…</code>",
        "status_no_key": "\nAPI-ключа пока нет.",
        "key_none": "У вас нет активного API-ключа. Сначала оформите подписку через 📋 Тарифы.",
        "key_show": "🔑 Префикс ключа: <code>{prefix}…</code>\nПолный ключ показывается только один раз при выпуске.\n\nПеревыпуск <b>немедленно отключает текущий ключ</b>.",
        "key_reissue_yes": "⚠️ Да, перевыпустить",
        "key_reissue_cancel": "Отмена",
        "key_reissue_cancelled": "Перевыпуск отменён. Текущий ключ не изменён.",
        "key_reissued": "✅ Ключ перевыпущен. Старый ключ отключён.",
        "key_new": "🔑 <b>Ваш новый API-ключ (показан один раз):</b>\n<code>{raw}</code>\n\nСохраните его надёжно — он больше не будет показан.",
        "devices_none_key": "API-ключа пока нет. Сначала оформите подписку через 📋 Тарифы.",
        "devices_empty": "Нет зарегистрированных устройств. Они появятся после первой сессии.",
        "devices_header": "<b>Зарегистрированные устройства</b>",
        "devices_remove_hint": "\nУдалите одно, чтобы освободить слот:",
        "device_remove_label": "🗑 Удалить {fp}… ({status})",
        "device_removed": "Устройство удалено. Слот освобождён.",
        "device_remove_ok": "Удалено — слот освобождён.",
        "device_remove_fail": "Не удалось удалить.",
        "human_connecting": "🧑‍💼 Соединяю с человеком — скоро ответят здесь. Всё, что вы напишете сейчас, уйдёт нашей команде.",
        "sent_to_team": "✅ Отправлено нашей команде.",
        "no_account": "Аккаунта пока нет. Отправьте /start.",
        "drip_nudge": "👋 Ещё думаете? Начните <b>бесплатно</b> с 7-дневного пробного периода — посмотрите реальные арбитражные возможности без риска. Нажмите 📋 Тарифы, когда будете готовы.",
        "digest": "📊 <b>Ваша сводка за неделю</b>\nПлан: <b>{plan}</b> · осталось дней: {days}\nДоход с рефералов: <b>{earned}</b>\n\nТак держать! Приглашайте друзей через 🎁 Рефералы, чтобы зарабатывать больше.",
        "muted": "🔕 Вы больше не будете получать рекламные сообщения. Важные (оплата, окончание срока) приходят по-прежнему. Отправьте /unmute, чтобы включить обратно.",
        "unmuted": "🔔 Рекламные сообщения снова включены. Отправьте /mute, чтобы отключить в любой момент.",
        "referrals_more": "⏳ В ожидании: <b>{pending}</b>  ·  🏆 Место: <b>#{rank}</b>",
        "referrals_share": "📤 Поделиться ссылкой",
        "referrals_share_text": "Я пользуюсь этим арбитражным инструментом — начните бесплатно и находите прибыльные возможности 🚀",
        "leaderboard_btn": "🏆 Рейтинг",
        "leaderboard_header": "🏆 <b>Топ рефереров</b> (по доходу)",
        "leaderboard_you": "\n— — —\n🫵 <b>Вы</b>: #{rank} · {earned} · оплатили: {count}",
        "leaderboard_empty": "Пока нет оплаченных рефералов — станьте первым! Нажмите 🎁 Рефералы за ссылкой.",
        "milestone": "🎉 <b>Достижение!</b> Вы привели <b>{count}</b> платящих клиентов. Делитесь ссылкой, чтобы зарабатывать больше! 🚀",
        "help_intro": "❓ <b>Помощь и поддержка</b>\nВыберите тему ниже или нажмите ✍️, чтобы задать свой вопрос.",
        "faq_pay": "💳 Как оплатить?",
        "faq_pay_a": "Нажмите 📋 <b>Тарифы</b>, выберите план и оплатите в крипте через @CryptoBot — подписка активируется автоматически после оплаты. 7-дневный пробный период бесплатный!",
        "faq_key": "🔑 Мой API-ключ",
        "faq_key_a": "После оформления подписки нажмите 🔑 <b>Ключ</b>, чтобы увидеть API-ключ (показывается один раз), и вставьте его в продукт. Потеряли? Нажмите 🔑 Ключ → перевыпустить.",
        "faq_device": "📱 Устройство заблокировано?",
        "faq_device_a": "Добавление нового устройства сверх лимита плана включает 24-часовую задержку — это защита от мошенничества, а не бан. Управляйте устройствами через 📱 <b>Устройства</b>.",
        "help_human_btn": "🗣 Связаться с человеком",
        "help_other_btn": "✍️ Задать свой вопрос",
        "help_other_prompt": "💬 Пишите — задайте вопрос текстом, и ассистент поможет.",
        "feedback_prompt": "💬 <b>Нам важны ваши идеи!</b> Напишите предложение <b>следующим сообщением</b> — оно сразу уйдёт нашей команде. (Чтобы задать вопрос, нажмите любую кнопку меню или ❓ Помощь.)",
        "feedback_thanks": "✅ Спасибо! Ваш отзыв отправлен нашей команде. 🙏",
        "human_offer": "🗣 Похоже, вы хотите связаться с человеком. Нажмите ниже, чтобы соединиться — или продолжайте писать, и ассистент поможет.",
        "human_hint": "💬 Нужен живой человек? Просто напишите: оператор",
        "promo_usage": "🏷 <b>Промокод</b>\nОтправьте <code>/promo ВАШКОД</code>, чтобы применить код, затем нажмите 📋 Тарифы и Купить.",
        "promo_enter": "🏷 <b>Промокод</b>\nОтправьте код <b>следующим сообщением</b> — я его проверю. (Нажмите любую кнопку меню, чтобы отменить.)",
        "promo_applied": "✅ Промокод <b>{code}</b> применён — {desc}. Нажмите 📋 Тарифы и Купить (действует 30 мин).",
        "promo_invalid": "❌ Код <b>{code}</b> недействителен или истёк.",
        "promo_used": "❌ Вы уже использовали код <b>{code}</b>.",
        "promo_plan_mismatch": "❌ Код <b>{code}</b> не подходит для тарифа {plan}.",
        "promo_maxed": "❌ Код <b>{code}</b> исчерпал лимит активаций.",
        "buy_invoice_promo": "🧾 Счёт за <b>{name}</b>\n💸 <b>{code}</b> ({desc}): <s>{original} {currency}</s> → <b>{price} {currency}</b>\nОплатить: {url}\n\nПодписка активируется автоматически после оплаты.",
        "pay_method_prompt": "💳 Как вы хотите оплатить <b>{plan}</b>?",
        "pay_stars_btn": "⭐ Telegram Stars",
        "pay_card_btn": "💳 Банковская карта",
        "pay_crypto_btn": "🪙 Крипта (@CryptoBot)",
        "pay_invoice_desc": "Подписка {plan} — {days} дней полного доступа ко всем возможностям.",
        "pay_confirmed_key": "✅ Оплата подтверждена — <b>{plan}</b> активна до {date}.\n\n🔑 <b>Ваш API-ключ (показывается один раз):</b>\n<code>{apikey}</code>\n\nСохраните его — больше он не появится.",
        "pay_confirmed_renew": "✅ Оплата подтверждена — <b>{plan}</b> продлена до {date}. Ваш API-ключ остаётся действительным.",
        "club_invite": "👥 <b>Чат для подписчиков</b>\nВаша подписка открывает доступ в закрытую группу. Нажмите, чтобы войти — я вас впущу:\n{link}",
        "club_removed": "👋 Доступ к чату для подписчиков завершился вместе с подпиской. Продлите в любой момент — нажмите 📋 Тарифы — и получите новое приглашение.",
        "club_declined": "🔒 Не могу добавить вас в чат для подписчиков — подписка неактивна. Нажмите 📋 Тарифы, оформите подписку — и я пришлю вам персональную ссылку-приглашение.",
    },
    "uk": {
        "choose_language": "🌐 Будь ласка, оберіть мову:",
        "language_set": "✅ Мову встановлено: {lang}.",
        "welcome": "👋 <b>Ласкаво просимо!</b> Цей бот керує вашою підпискою, API-ключем і пристроями.\n\n🎁 Уперше? Натисніть 📋 <b>Тарифи</b> — пробний період безкоштовний. Або просто напишіть запитання, і асистент допоможе.",
        "welcome_back": "👋 <b>З поверненням!</b> Натисніть кнопку нижче або поставте будь-яке запитання.",
        "getting_started": (
            "<b>🚀 Швидкий старт</b>\n"
            "1️⃣ Натисніть 📋 <b>Тарифи</b> й оберіть план — почніть безкоштовно з пробного.\n"
            "2️⃣ Натисніть 🔑 <b>Ключ</b>, щоб отримати API-ключ (показується один раз).\n"
            "3️⃣ Вставте ключ у продукт — і все готово.\n\n"
            "Застрягли на якомусь кроці? Просто напишіть запитання тут. 💬"
        ),
        "days_left": "залишилось днів: {n}",
        "expires_soon": "⏳ спливає через {n} дн.",
        "help": (
            "<b>Що можна зробити</b>\n"
            "📋 Тарифи — переглянути плани підписки\n"
            "📊 Статус — ваша підписка та термін дії\n"
            "🔑 Ключ — показати/перевипустити API-ключ\n"
            "📱 Пристрої — керування пристроями\n"
            "🆘 Оператор — зв'язатися з людиною\n"
            "🌐 Мова — змінити мову\n\n"
            "💬 Можна просто <b>поставити запитання</b> текстом — асистент допоможе."
        ),
        "referrals_block": (
            "🎁 <b>Реферали</b>\n"
            "Діліться посиланням і отримуйте <b>{rate}%</b>, коли запрошений оформлює підписку.\n\n"
            "🔗 <b>Ваше реферальне посилання:</b>\n{link}\n\n"
            "👥 Запрошено: <b>{invited}</b>\n✅ Оплатили: <b>{qualified}</b>\n💰 Зароблено: <b>{earned}</b>"
        ),
        "reminder_expiring": (
            "⏳ Ваша підписка <b>{plan}</b> спливає через <b>{days}</b> дн. — {date}.\n"
            "Натисніть нижче, щоб продовжити в один тап і зберегти доступ."
        ),
        "renew_button": "🔄 Продовжити {plan}",
        "winback": (
            "👋 Ми сумуємо! Ваш доступ <b>{plan}</b> завершився {days} дн. тому.\n"
            "Повертайтеся будь-коли — натисніть 📋 Тарифи, щоб продовжити."
        ),
        "plans_header": "<b>📋 Оберіть тариф</b>\nНатисніть кнопку нижче, щоб оформити. Оплата у крипті, активація автоматична.",
        "tier_trial": "пробний (можливості до 2%)",
        "tier_all": "усі можливості",
        "price_free": "безкоштовно",
        "plan_line": "\n• <b>{name}</b> — {price} / {days}д\n  {tier}; пристроїв: {devices}, сесій: {sessions}, {rate}/хв",
        "buy_label": "Купити {name} — {price} {currency}",
        "buy_unknown": "Невідомий план. Натисніть 📋 Тарифи.",
        "buy_invoice": "🧾 Рахунок за <b>{name}</b> ({price} {currency}).\nОплатити: {url}\n\nПідписка активується автоматично після оплати.",
        "status_none": "У вас поки немає активної підписки.\nНатисніть 📋 <b>Тарифи</b>, щоб почати — пробний безкоштовний.",
        "status_block": "<b>📊 Ваша підписка</b>\nПлан: <b>{plan}</b>\nСтатус: {status}\nДіє до: {expires} · {days_left}{key_line}",
        "status_key_line": "\nAPI-ключ: <code>{prefix}…</code>",
        "status_no_key": "\nAPI-ключа поки немає.",
        "key_none": "У вас немає активного API-ключа. Спочатку оформіть підписку через 📋 Тарифи.",
        "key_show": "🔑 Префікс ключа: <code>{prefix}…</code>\nПовний ключ показується лише раз під час випуску.\n\nПеревипуск <b>негайно вимикає поточний ключ</b>.",
        "key_reissue_yes": "⚠️ Так, перевипустити",
        "key_reissue_cancel": "Скасувати",
        "key_reissue_cancelled": "Перевипуск скасовано. Поточний ключ без змін.",
        "key_reissued": "✅ Ключ перевипущено. Старий ключ вимкнено.",
        "key_new": "🔑 <b>Ваш новий API-ключ (показано один раз):</b>\n<code>{raw}</code>\n\nЗбережіть його надійно — більше він не показуватиметься.",
        "devices_none_key": "API-ключа поки немає. Спочатку оформіть підписку через 📋 Тарифи.",
        "devices_empty": "Немає зареєстрованих пристроїв. Вони з'являться після першої сесії.",
        "devices_header": "<b>Зареєстровані пристрої</b>",
        "devices_remove_hint": "\nВидаліть один, щоб звільнити слот:",
        "device_remove_label": "🗑 Видалити {fp}… ({status})",
        "device_removed": "Пристрій видалено. Слот звільнено.",
        "device_remove_ok": "Видалено — слот звільнено.",
        "device_remove_fail": "Не вдалося видалити.",
        "human_connecting": "🧑‍💼 З'єдную з людиною — скоро дадуть відповідь тут. Усе, що ви напишете зараз, піде нашій команді.",
        "sent_to_team": "✅ Надіслано нашій команді.",
        "no_account": "Облікового запису поки немає. Надішліть /start.",
        "drip_nudge": "👋 Ще вагаєтесь? Почніть <b>безкоштовно</b> з 7-денного пробного періоду — перегляньте реальні арбітражні можливості без ризику. Натисніть 📋 Тарифи, коли будете готові.",
        "digest": "📊 <b>Ваш тижневий підсумок</b>\nПлан: <b>{plan}</b> · залишилось днів: {days}\nДохід з рефералів: <b>{earned}</b>\n\nТак тримати! Запрошуйте друзів через 🎁 Реферали, щоб заробляти більше.",
        "muted": "🔕 Ви більше не отримуватимете рекламні повідомлення. Важливі (оплата, завершення терміну) надходять як завжди. Надішліть /unmute, щоб увімкнути знову.",
        "unmuted": "🔔 Рекламні повідомлення знову увімкнено. Надішліть /mute, щоб вимкнути будь-коли.",
        "referrals_more": "⏳ В очікуванні: <b>{pending}</b>  ·  🏆 Місце: <b>#{rank}</b>",
        "referrals_share": "📤 Поділитися посиланням",
        "referrals_share_text": "Я користуюся цим арбітражним інструментом — почніть безкоштовно і знаходьте прибуткові можливості 🚀",
        "leaderboard_btn": "🏆 Рейтинг",
        "leaderboard_header": "🏆 <b>Топ реферерів</b> (за доходом)",
        "leaderboard_you": "\n— — —\n🫵 <b>Ви</b>: #{rank} · {earned} · оплатили: {count}",
        "leaderboard_empty": "Поки немає оплачених рефералів — станьте першим! Натисніть 🎁 Реферали за посиланням.",
        "milestone": "🎉 <b>Досягнення!</b> Ви привели <b>{count}</b> платних клієнтів. Діліться посиланням, щоб заробляти більше! 🚀",
        "help_intro": "❓ <b>Допомога та підтримка</b>\nОберіть тему нижче або натисніть ✍️, щоб поставити своє запитання.",
        "faq_pay": "💳 Як оплатити?",
        "faq_pay_a": "Натисніть 📋 <b>Тарифи</b>, оберіть план і сплатіть у крипті через @CryptoBot — підписка активується автоматично після оплати. 7-денний пробний період безкоштовний!",
        "faq_key": "🔑 Мій API-ключ",
        "faq_key_a": "Після оформлення підписки натисніть 🔑 <b>Ключ</b>, щоб побачити API-ключ (показується один раз), і вставте його в продукт. Втратили? Натисніть 🔑 Ключ → перевипустити.",
        "faq_device": "📱 Пристрій заблоковано?",
        "faq_device_a": "Додавання нового пристрою понад ліміт плану вмикає 24-годинну затримку — це захист від шахрайства, а не бан. Керуйте пристроями через 📱 <b>Пристрої</b>.",
        "help_human_btn": "🗣 Зв'язатися з людиною",
        "help_other_btn": "✍️ Поставити своє запитання",
        "help_other_prompt": "💬 Пишіть — поставте запитання текстом, і асистент допоможе.",
        "feedback_prompt": "💬 <b>Нам важливі ваші ідеї!</b> Напишіть пропозицію <b>наступним повідомленням</b> — вона одразу піде нашій команді. (Щоб поставити запитання, натисніть будь-яку кнопку меню або ❓ Допомога.)",
        "feedback_thanks": "✅ Дякуємо! Ваш відгук надіслано нашій команді. 🙏",
        "human_offer": "🗣 Схоже, ви хочете зв'язатися з людиною. Натисніть нижче, щоб з'єднатися — або продовжуйте писати, і асистент допоможе.",
        "human_hint": "💬 Потрібна жива людина? Просто напишіть: оператор",
        "promo_usage": "🏷 <b>Промокод</b>\nНадішліть <code>/promo ВАШКОД</code>, щоб застосувати код, потім натисніть 📋 Тарифи і Купити.",
        "promo_enter": "🏷 <b>Промокод</b>\nНадішліть код <b>наступним повідомленням</b> — я його перевірю. (Натисніть будь-яку кнопку меню, щоб скасувати.)",
        "promo_applied": "✅ Промокод <b>{code}</b> застосовано — {desc}. Натисніть 📋 Тарифи і Купити (діє 30 хв).",
        "promo_invalid": "❌ Код <b>{code}</b> недійсний або прострочений.",
        "promo_used": "❌ Ви вже використали код <b>{code}</b>.",
        "promo_plan_mismatch": "❌ Код <b>{code}</b> не підходить для тарифу {plan}.",
        "promo_maxed": "❌ Код <b>{code}</b> вичерпав ліміт активацій.",
        "buy_invoice_promo": "🧾 Рахунок за <b>{name}</b>\n💸 <b>{code}</b> ({desc}): <s>{original} {currency}</s> → <b>{price} {currency}</b>\nОплатити: {url}\n\nПідписка активується автоматично після оплати.",
        "pay_method_prompt": "💳 Як ви хочете оплатити <b>{plan}</b>?",
        "pay_stars_btn": "⭐ Telegram Stars",
        "pay_card_btn": "💳 Банківська картка",
        "pay_crypto_btn": "🪙 Крипта (@CryptoBot)",
        "pay_invoice_desc": "Підписка {plan} — {days} днів повного доступу до всіх можливостей.",
        "pay_confirmed_key": "✅ Оплату підтверджено — <b>{plan}</b> активна до {date}.\n\n🔑 <b>Ваш API-ключ (показується один раз):</b>\n<code>{apikey}</code>\n\nЗбережіть його — більше він не з'явиться.",
        "pay_confirmed_renew": "✅ Оплату підтверджено — <b>{plan}</b> продовжено до {date}. Ваш API-ключ залишається дійсним.",
        "club_invite": "👥 <b>Чат для підписників</b>\nВаша підписка відкриває доступ до закритої групи. Натисніть, щоб увійти — я вас впущу:\n{link}",
        "club_removed": "👋 Доступ до чату для підписників завершився разом із підпискою. Продовжіть будь-коли — натисніть 📋 Тарифи — і отримаєте нове запрошення.",
        "club_declined": "🔒 Не можу додати вас до чату для підписників — підписка неактивна. Натисніть 📋 Тарифи, оформіть підписку — і я надішлю вам персональне посилання-запрошення.",
    },
    "es": {
        "choose_language": "🌐 Por favor, elige tu idioma:",
        "language_set": "✅ Idioma establecido: {lang}.",
        "welcome": "👋 <b>¡Bienvenido!</b> Este bot gestiona tu suscripción, clave API y dispositivos.\n\n🎁 ¿Primera vez? Pulsa 📋 <b>Planes</b> — la prueba es gratis. O simplemente escribe una pregunta y el asistente te ayudará.",
        "welcome_back": "👋 <b>¡Bienvenido de nuevo!</b> Pulsa un botón abajo o pregúntame lo que quieras.",
        "getting_started": (
            "<b>🚀 Inicio rápido</b>\n"
            "1️⃣ Pulsa 📋 <b>Planes</b> y elige uno — empieza gratis con la prueba.\n"
            "2️⃣ Pulsa 🔑 <b>Clave</b> para obtener tu clave API (se muestra una vez).\n"
            "3️⃣ Pega la clave en el producto y listo.\n\n"
            "¿Atascado en algún paso? Solo escribe tu pregunta aquí. 💬"
        ),
        "days_left": "quedan {n} días",
        "expires_soon": "⏳ vence en {n} días",
        "help": (
            "<b>Qué puedes hacer</b>\n"
            "📋 Planes — ver planes de suscripción\n"
            "📊 Estado — tu suscripción y vencimiento\n"
            "🔑 Clave — ver/reemitir tu clave API\n"
            "📱 Dispositivos — gestionar tus dispositivos\n"
            "🆘 Persona — hablar con alguien real\n"
            "🌐 Idioma — cambiar idioma\n\n"
            "💬 También puedes simplemente <b>hacer una pregunta</b> — el asistente te ayudará."
        ),
        "referrals_block": (
            "🎁 <b>Referidos</b>\n"
            "Comparte tu enlace y gana <b>{rate}%</b> cuando alguien que invitas se suscribe.\n\n"
            "🔗 <b>Tu enlace de invitación:</b>\n{link}\n\n"
            "👥 Invitados: <b>{invited}</b>\n✅ Pagaron: <b>{qualified}</b>\n💰 Ganado: <b>{earned}</b>"
        ),
        "reminder_expiring": (
            "⏳ Tu suscripción <b>{plan}</b> vence en <b>{days}</b> día(s) — el {date}.\n"
            "Pulsa abajo para renovar en un toque y mantener tu acceso."
        ),
        "renew_button": "🔄 Renovar {plan}",
        "winback": (
            "👋 ¡Te echamos de menos! Tu acceso <b>{plan}</b> terminó hace {days} día(s).\n"
            "Vuelve cuando quieras — pulsa 📋 Planes para continuar."
        ),
        "plans_header": "<b>📋 Elige un plan</b>\nPulsa un botón abajo para suscribirte. El pago es en cripto y se activa automáticamente.",
        "tier_trial": "prueba (oportunidades hasta 2%)",
        "tier_all": "todas las oportunidades",
        "price_free": "gratis",
        "plan_line": "\n• <b>{name}</b> — {price} / {days}d\n  {tier}; {devices} dispositivo(s), {sessions} sesión(es), {rate}/min",
        "buy_label": "Comprar {name} — {price} {currency}",
        "buy_unknown": "Plan desconocido. Pulsa 📋 Planes.",
        "buy_invoice": "🧾 Factura por <b>{name}</b> ({price} {currency}).\nPaga aquí: {url}\n\nTu suscripción se activa automáticamente tras el pago.",
        "status_none": "Aún no tienes una suscripción activa.\nPulsa 📋 <b>Planes</b> para empezar — la prueba es gratis.",
        "status_block": "<b>📊 Tu suscripción</b>\nPlan: <b>{plan}</b>\nEstado: {status}\nVence: {expires} · {days_left}{key_line}",
        "status_key_line": "\nClave API: <code>{prefix}…</code>",
        "status_no_key": "\nAún no hay clave API.",
        "key_none": "No tienes una clave API activa. Suscríbete primero con 📋 Planes.",
        "key_show": "🔑 Prefijo de la clave: <code>{prefix}…</code>\nLa clave completa solo se muestra una vez al emitirla.\n\nReemitir <b>desactiva la clave actual</b> de inmediato.",
        "key_reissue_yes": "⚠️ Sí, reemitir",
        "key_reissue_cancel": "Cancelar",
        "key_reissue_cancelled": "Reemisión cancelada. Tu clave actual no cambia.",
        "key_reissued": "✅ Clave reemitida. La anterior queda desactivada.",
        "key_new": "🔑 <b>Tu nueva clave API (se muestra una vez):</b>\n<code>{raw}</code>\n\nGuárdala de forma segura — no se mostrará de nuevo.",
        "devices_none_key": "Aún no hay clave API. Suscríbete primero con 📋 Planes.",
        "devices_empty": "No hay dispositivos registrados. Aparecen tras tu primera sesión.",
        "devices_header": "<b>Dispositivos registrados</b>",
        "devices_remove_hint": "\nElimina uno para liberar un espacio:",
        "device_remove_label": "🗑 Eliminar {fp}… ({status})",
        "device_removed": "Dispositivo eliminado. Hay un espacio libre.",
        "device_remove_ok": "Eliminado — espacio liberado.",
        "device_remove_fail": "No se pudo eliminar.",
        "human_connecting": "🧑‍💼 Te conecto con una persona — alguien responderá aquí pronto. Lo que escribas ahora va directo a nuestro equipo.",
        "sent_to_team": "✅ Enviado a nuestro equipo.",
        "no_account": "Aún no hay cuenta. Envía /start.",
        "drip_nudge": "👋 ¿Aún lo piensas? Empieza <b>gratis</b> con la prueba de 7 días — mira oportunidades reales de arbitraje sin riesgo. Pulsa 📋 Planes cuando quieras.",
        "digest": "📊 <b>Tu resumen semanal</b>\nPlan: <b>{plan}</b> · quedan {days} días\nGanancias por referidos: <b>{earned}</b>\n\n¡Sigue así! Invita amigos con 🎁 Referidos para ganar más.",
        "muted": "🔕 Ya no recibirás mensajes promocionales. Los importantes (pagos, vencimiento) siguen llegando. Envía /unmute para reactivarlos.",
        "unmuted": "🔔 Mensajes promocionales reactivados. Envía /mute para detenerlos cuando quieras.",
        "referrals_more": "⏳ Pendientes: <b>{pending}</b>  ·  🏆 Puesto: <b>#{rank}</b>",
        "referrals_share": "📤 Compartir mi enlace",
        "referrals_share_text": "Estoy usando esta herramienta de arbitraje — empieza gratis y encuentra oportunidades rentables 🚀",
        "leaderboard_btn": "🏆 Clasificación",
        "leaderboard_header": "🏆 <b>Mejores referidores</b> (por ganancias)",
        "leaderboard_you": "\n— — —\n🫵 <b>Tú</b>: #{rank} · {earned} · {count} pagados",
        "leaderboard_empty": "Aún no hay referidos pagados — ¡sé el primero! Pulsa 🎁 Referidos para tu enlace.",
        "milestone": "🎉 <b>¡Logro alcanzado!</b> Has traído <b>{count}</b> cliente(s) de pago. ¡Sigue compartiendo tu enlace para ganar más! 🚀",
        "help_intro": "❓ <b>Ayuda y soporte</b>\nElige un tema abajo, o pulsa ✍️ para hacer tu propia pregunta.",
        "faq_pay": "💳 ¿Cómo pago?",
        "faq_pay_a": "Pulsa 📋 <b>Planes</b>, elige un plan y paga en cripto vía @CryptoBot — tu suscripción se activa automáticamente tras el pago. ¡La prueba de 7 días es gratis!",
        "faq_key": "🔑 Mi clave API",
        "faq_key_a": "Tras suscribirte, pulsa 🔑 <b>Clave</b> para ver tu clave API (se muestra una vez) y pégala en el producto. ¿La perdiste? Pulsa 🔑 Clave → reemitir.",
        "faq_device": "📱 ¿Dispositivo bloqueado?",
        "faq_device_a": "Añadir un dispositivo más allá del límite de tu plan activa un periodo de 24h — es protección antifraude, no un bloqueo. Gestiona tus dispositivos con 📱 <b>Dispositivos</b>.",
        "help_human_btn": "🗣 Hablar con una persona",
        "help_other_btn": "✍️ Hacer mi propia pregunta",
        "help_other_prompt": "💬 Adelante — escribe tu pregunta y el asistente te ayudará.",
        "feedback_prompt": "💬 <b>¡Nos encantan tus ideas!</b> Escribe tu sugerencia en tu <b>próximo mensaje</b> y llega directo a nuestro equipo. (Para hacer una pregunta, toca cualquier botón del menú o ❓ Ayuda.)",
        "feedback_thanks": "✅ ¡Gracias! Tu sugerencia se envió a nuestro equipo. 🙏",
        "human_offer": "🗣 Parece que quieres hablar con una persona real. Pulsa abajo para conectar — o sigue escribiendo y el asistente te ayudará.",
        "human_hint": "💬 ¿Prefieres una persona real? Solo escribe: operador",
        "promo_usage": "🏷 <b>Código de descuento</b>\nEnvía <code>/promo TUCODIGO</code> para aplicar un código, luego pulsa 📋 Planes y Comprar.",
        "promo_enter": "🏷 <b>Código de descuento</b>\nEnvía tu código en tu <b>próximo mensaje</b> y lo comprobaré. (Toca cualquier botón del menú para cancelar.)",
        "promo_applied": "✅ Código <b>{code}</b> aplicado — {desc}. Pulsa 📋 Planes y Comprar para usarlo (válido 30 min).",
        "promo_invalid": "❌ El código <b>{code}</b> no es válido o ha caducado.",
        "promo_used": "❌ Ya has usado el código <b>{code}</b>.",
        "promo_plan_mismatch": "❌ El código <b>{code}</b> no se aplica al plan {plan}.",
        "promo_maxed": "❌ El código <b>{code}</b> alcanzó su límite de usos.",
        "buy_invoice_promo": "🧾 Factura de <b>{name}</b>\n💸 <b>{code}</b> ({desc}): <s>{original} {currency}</s> → <b>{price} {currency}</b>\nPaga aquí: {url}\n\nTu suscripción se activa automáticamente tras el pago.",
        "pay_method_prompt": "💳 ¿Cómo quieres pagar <b>{plan}</b>?",
        "pay_stars_btn": "⭐ Telegram Stars",
        "pay_card_btn": "💳 Tarjeta bancaria",
        "pay_crypto_btn": "🪙 Cripto (@CryptoBot)",
        "pay_invoice_desc": "Suscripción {plan} — {days} días de acceso completo a todas las oportunidades.",
        "pay_confirmed_key": "✅ Pago confirmado — <b>{plan}</b> activo hasta {date}.\n\n🔑 <b>Tu clave API (se muestra una vez):</b>\n<code>{apikey}</code>\n\nGuárdala bien — no se mostrará de nuevo.",
        "pay_confirmed_renew": "✅ Pago confirmado — <b>{plan}</b> extendido hasta {date}. Tu clave API sigue siendo válida.",
        "club_invite": "👥 <b>Chat de miembros</b>\nTu suscripción desbloquea el grupo privado de suscriptores. Pulsa para entrar y te dejaré pasar:\n{link}",
        "club_removed": "👋 Tu acceso al chat de miembros terminó con tu suscripción. Renueva cuando quieras — pulsa 📋 Planes — y recibirás una nueva invitación.",
        "club_declined": "🔒 No puedo añadirte al chat de miembros: tu suscripción no está activa. Pulsa 📋 Planes para suscribirte y te enviaré tu propio enlace de invitación.",
    },
    "fr": {
        "choose_language": "🌐 Veuillez choisir votre langue :",
        "language_set": "✅ Langue définie : {lang}.",
        "welcome": "👋 <b>Bienvenue !</b> Ce bot gère votre abonnement, votre clé API et vos appareils.\n\n🎁 Première fois ? Appuyez sur 📋 <b>Forfaits</b> — l'essai est gratuit. Ou posez simplement une question, l'assistant vous aidera.",
        "welcome_back": "👋 <b>Bon retour !</b> Appuyez sur un bouton ci-dessous ou posez-moi une question.",
        "getting_started": (
            "<b>🚀 Démarrage rapide</b>\n"
            "1️⃣ Appuyez sur 📋 <b>Forfaits</b> et choisissez-en un — commencez gratuitement avec l'essai.\n"
            "2️⃣ Appuyez sur 🔑 <b>Clé</b> pour obtenir votre clé API (affichée une fois).\n"
            "3️⃣ Collez la clé dans le produit, et c'est parti.\n\n"
            "Bloqué à une étape ? Écrivez simplement votre question ici. 💬"
        ),
        "days_left": "{n} jours restants",
        "expires_soon": "⏳ expire dans {n} jours",
        "help": (
            "<b>Ce que vous pouvez faire</b>\n"
            "📋 Forfaits — voir les abonnements\n"
            "📊 Statut — votre abonnement et son échéance\n"
            "🔑 Clé — afficher/réémettre votre clé API\n"
            "📱 Appareils — gérer vos appareils\n"
            "🆘 Humain — parler à une vraie personne\n"
            "🌐 Langue — changer de langue\n\n"
            "💬 Vous pouvez aussi simplement <b>poser une question</b> — l'assistant vous aidera."
        ),
        "referrals_block": (
            "🎁 <b>Parrainage</b>\n"
            "Partagez votre lien et gagnez <b>{rate}%</b> quand une personne invitée s'abonne.\n\n"
            "🔗 <b>Votre lien de parrainage :</b>\n{link}\n\n"
            "👥 Invités : <b>{invited}</b>\n✅ Ont payé : <b>{qualified}</b>\n💰 Gagné : <b>{earned}</b>"
        ),
        "reminder_expiring": (
            "⏳ Votre abonnement <b>{plan}</b> expire dans <b>{days}</b> jour(s) — le {date}.\n"
            "Appuyez ci-dessous pour renouveler en un geste et garder votre accès."
        ),
        "renew_button": "🔄 Renouveler {plan}",
        "winback": (
            "👋 Vous nous manquez ! Votre accès <b>{plan}</b> a pris fin il y a {days} jour(s).\n"
            "Revenez quand vous voulez — appuyez sur 📋 Forfaits pour continuer."
        ),
        "plans_header": "<b>📋 Choisissez un forfait</b>\nAppuyez sur un bouton ci-dessous pour vous abonner. Le paiement se fait en crypto et s'active automatiquement.",
        "tier_trial": "essai (opportunités jusqu'à 2%)",
        "tier_all": "toutes les opportunités",
        "price_free": "gratuit",
        "plan_line": "\n• <b>{name}</b> — {price} / {days}j\n  {tier}; {devices} appareil(s), {sessions} session(s), {rate}/min",
        "buy_label": "Acheter {name} — {price} {currency}",
        "buy_unknown": "Forfait inconnu. Appuyez sur 📋 Forfaits.",
        "buy_invoice": "🧾 Facture pour <b>{name}</b> ({price} {currency}).\nPayez ici : {url}\n\nVotre abonnement s'active automatiquement après le paiement.",
        "status_none": "Vous n'avez pas encore d'abonnement actif.\nAppuyez sur 📋 <b>Forfaits</b> pour commencer — l'essai est gratuit.",
        "status_block": "<b>📊 Votre abonnement</b>\nForfait : <b>{plan}</b>\nStatut : {status}\nExpire : {expires} · {days_left}{key_line}",
        "status_key_line": "\nClé API : <code>{prefix}…</code>",
        "status_no_key": "\nPas encore de clé API.",
        "key_none": "Vous n'avez pas de clé API active. Abonnez-vous d'abord via 📋 Forfaits.",
        "key_show": "🔑 Préfixe de la clé : <code>{prefix}…</code>\nLa clé complète n'est affichée qu'une seule fois à l'émission.\n\nLa réémission <b>désactive immédiatement la clé actuelle</b>.",
        "key_reissue_yes": "⚠️ Oui, réémettre",
        "key_reissue_cancel": "Annuler",
        "key_reissue_cancelled": "Réémission annulée. Votre clé actuelle est inchangée.",
        "key_reissued": "✅ Clé réémise. L'ancienne est désactivée.",
        "key_new": "🔑 <b>Votre nouvelle clé API (affichée une fois) :</b>\n<code>{raw}</code>\n\nConservez-la en lieu sûr — elle ne sera plus affichée.",
        "devices_none_key": "Pas encore de clé API. Abonnez-vous d'abord via 📋 Forfaits.",
        "devices_empty": "Aucun appareil enregistré. Ils apparaissent après votre première session.",
        "devices_header": "<b>Appareils enregistrés</b>",
        "devices_remove_hint": "\nSupprimez-en un pour libérer un emplacement :",
        "device_remove_label": "🗑 Supprimer {fp}… ({status})",
        "device_removed": "Appareil supprimé. Un emplacement est libre.",
        "device_remove_ok": "Supprimé — emplacement libéré.",
        "device_remove_fail": "Suppression impossible.",
        "human_connecting": "🧑‍💼 Je vous mets en relation avec une personne — réponse ici sous peu. Tout ce que vous écrivez maintenant va directement à notre équipe.",
        "sent_to_team": "✅ Envoyé à notre équipe.",
        "no_account": "Pas encore de compte. Envoyez /start.",
        "drip_nudge": "👋 Vous hésitez encore ? Commencez <b>gratuitement</b> avec l'essai de 7 jours — voyez de vraies opportunités d'arbitrage sans risque. Appuyez sur 📋 Forfaits quand vous voulez.",
        "digest": "📊 <b>Votre résumé hebdomadaire</b>\nForfait : <b>{plan}</b> · {days} jours restants\nGains de parrainage : <b>{earned}</b>\n\nContinuez ! Invitez des amis via 🎁 Parrainage pour gagner plus.",
        "muted": "🔕 Vous ne recevrez plus de messages promotionnels. Les importants (paiements, expiration) arrivent toujours. Envoyez /unmute pour les réactiver.",
        "unmuted": "🔔 Messages promotionnels réactivés. Envoyez /mute pour les arrêter à tout moment.",
        "referrals_more": "⏳ En attente : <b>{pending}</b>  ·  🏆 Rang : <b>#{rank}</b>",
        "referrals_share": "📤 Partager mon lien",
        "referrals_share_text": "J'utilise cet outil d'arbitrage — commencez gratuitement et trouvez des opportunités rentables 🚀",
        "leaderboard_btn": "🏆 Classement",
        "leaderboard_header": "🏆 <b>Meilleurs parrains</b> (par gains)",
        "leaderboard_you": "\n— — —\n🫵 <b>Vous</b> : #{rank} · {earned} · {count} payés",
        "leaderboard_empty": "Aucun parrainage payé pour l'instant — soyez le premier ! Appuyez sur 🎁 Parrainage pour votre lien.",
        "milestone": "🎉 <b>Palier atteint !</b> Vous avez amené <b>{count}</b> client(s) payant(s). Continuez à partager votre lien pour gagner plus ! 🚀",
        "help_intro": "❓ <b>Aide et support</b>\nChoisissez un sujet ci-dessous, ou appuyez sur ✍️ pour poser votre propre question.",
        "faq_pay": "💳 Comment payer ?",
        "faq_pay_a": "Appuyez sur 📋 <b>Forfaits</b>, choisissez un forfait et payez en crypto via @CryptoBot — votre abonnement s'active automatiquement après le paiement. L'essai de 7 jours est gratuit !",
        "faq_key": "🔑 Ma clé API",
        "faq_key_a": "Après l'abonnement, appuyez sur 🔑 <b>Clé</b> pour afficher votre clé API (montrée une fois) et collez-la dans le produit. Perdue ? Appuyez sur 🔑 Clé → réémettre.",
        "faq_device": "📱 Appareil bloqué ?",
        "faq_device_a": "Ajouter un nouvel appareil au-delà de la limite de votre forfait déclenche un délai de 24h — c'est une protection anti-fraude, pas un blocage. Gérez vos appareils via 📱 <b>Appareils</b>.",
        "help_human_btn": "🗣 Parler à une personne",
        "help_other_btn": "✍️ Poser ma propre question",
        "help_other_prompt": "💬 Allez-y — écrivez votre question et l'assistant vous aidera.",
        "feedback_prompt": "💬 <b>Vos idées nous intéressent !</b> Écrivez votre suggestion dans votre <b>prochain message</b>, elle ira directement à notre équipe. (Pour poser une question, appuyez sur un bouton du menu ou ❓ Aide.)",
        "feedback_thanks": "✅ Merci ! Votre avis a été envoyé à notre équipe. 🙏",
        "human_offer": "🗣 On dirait que vous souhaitez parler à une vraie personne. Appuyez ci-dessous pour vous connecter — ou continuez à écrire et l'assistant vous aidera.",
        "human_hint": "💬 Vous préférez une vraie personne ? Écrivez simplement : opérateur",
        "promo_usage": "🏷 <b>Code de réduction</b>\nEnvoyez <code>/promo VOTRECODE</code> pour appliquer un code, puis appuyez sur 📋 Forfaits et Acheter.",
        "promo_enter": "🏷 <b>Code de réduction</b>\nEnvoyez votre code dans votre <b>prochain message</b> et je le vérifierai. (Appuyez sur un bouton du menu pour annuler.)",
        "promo_applied": "✅ Code <b>{code}</b> appliqué — {desc}. Appuyez sur 📋 Forfaits et Acheter pour l'utiliser (valable 30 min).",
        "promo_invalid": "❌ Le code <b>{code}</b> est invalide ou expiré.",
        "promo_used": "❌ Vous avez déjà utilisé le code <b>{code}</b>.",
        "promo_plan_mismatch": "❌ Le code <b>{code}</b> ne s'applique pas au forfait {plan}.",
        "promo_maxed": "❌ Le code <b>{code}</b> a atteint sa limite d'utilisations.",
        "buy_invoice_promo": "🧾 Facture pour <b>{name}</b>\n💸 <b>{code}</b> ({desc}) : <s>{original} {currency}</s> → <b>{price} {currency}</b>\nPayez ici : {url}\n\nVotre abonnement s'active automatiquement après le paiement.",
        "pay_method_prompt": "💳 Comment souhaitez-vous payer <b>{plan}</b> ?",
        "pay_stars_btn": "⭐ Telegram Stars",
        "pay_card_btn": "💳 Carte bancaire",
        "pay_crypto_btn": "🪙 Crypto (@CryptoBot)",
        "pay_invoice_desc": "Abonnement {plan} — {days} jours d'accès complet à toutes les opportunités.",
        "pay_confirmed_key": "✅ Paiement confirmé — <b>{plan}</b> actif jusqu'au {date}.\n\n🔑 <b>Votre clé API (affichée une seule fois) :</b>\n<code>{apikey}</code>\n\nConservez-la — elle ne sera plus affichée.",
        "pay_confirmed_renew": "✅ Paiement confirmé — <b>{plan}</b> prolongé jusqu'au {date}. Votre clé API reste valable.",
        "club_invite": "👥 <b>Chat des membres</b>\nVotre abonnement débloque le groupe privé des abonnés. Appuyez pour rejoindre, je vous laisse entrer :\n{link}",
        "club_removed": "👋 Votre accès au chat des membres a pris fin avec votre abonnement. Renouvelez à tout moment — appuyez sur 📋 Forfaits — et vous recevrez une nouvelle invitation.",
        "club_declined": "🔒 Je ne peux pas vous ajouter au chat des membres : votre abonnement n'est pas actif. Appuyez sur 📋 Forfaits pour vous abonner et je vous enverrai votre propre lien d'invitation.",
    },
}


def t(lang_code: str | None, key: str, **kwargs) -> str:
    table = STRINGS.get(normalize(lang_code), STRINGS[DEFAULT_LANG])
    s = table.get(key) or STRINGS[DEFAULT_LANG].get(key, key)
    return s.format(**kwargs) if kwargs else s
