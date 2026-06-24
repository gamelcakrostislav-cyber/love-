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
    "human":    {"en": "🆘 Human", "ru": "🆘 Оператор", "uk": "🆘 Оператор", "es": "🆘 Persona", "fr": "🆘 Humain"},
    "language": {"en": "🌐 Language", "ru": "🌐 Язык", "uk": "🌐 Мова", "es": "🌐 Idioma", "fr": "🌐 Langue"},
    "help":     {"en": "❓ Help", "ru": "❓ Помощь", "uk": "❓ Допомога", "es": "❓ Ayuda", "fr": "❓ Aide"},
}
MENU_ORDER = ["plans", "status", "key", "devices", "human", "language", "help"]

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
    "human":    {"en": "Talk to a real person", "ru": "Связаться с человеком", "uk": "Зв'язатися з людиною", "es": "Hablar con una persona", "fr": "Parler à une personne"},
    "language": {"en": "Change language", "ru": "Сменить язык", "uk": "Змінити мову", "es": "Cambiar idioma", "fr": "Changer de langue"},
    "help":     {"en": "How the bot works", "ru": "Как работает бот", "uk": "Як працює бот", "es": "Cómo funciona el bot", "fr": "Comment le bot fonctionne"},
}
COMMAND_ORDER = ["start", "plans", "status", "key", "devices", "human", "language", "help"]


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
        "welcome": "👋 <b>Welcome!</b> This bot manages your arbitrage subscription, API key and devices.\n\nTap a button below to begin — or just type a question and the assistant will help.",
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
    },
    "ru": {
        "choose_language": "🌐 Пожалуйста, выберите язык:",
        "language_set": "✅ Язык установлен: {lang}.",
        "welcome": "👋 <b>Добро пожаловать!</b> Этот бот управляет вашей подпиской, API-ключом и устройствами.\n\nНажмите кнопку ниже, чтобы начать — или просто напишите вопрос, и ассистент поможет.",
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
    },
    "uk": {
        "choose_language": "🌐 Будь ласка, оберіть мову:",
        "language_set": "✅ Мову встановлено: {lang}.",
        "welcome": "👋 <b>Ласкаво просимо!</b> Цей бот керує вашою підпискою, API-ключем і пристроями.\n\nНатисніть кнопку нижче, щоб почати — або просто напишіть запитання, і асистент допоможе.",
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
    },
    "es": {
        "choose_language": "🌐 Por favor, elige tu idioma:",
        "language_set": "✅ Idioma establecido: {lang}.",
        "welcome": "👋 <b>¡Bienvenido!</b> Este bot gestiona tu suscripción, clave API y dispositivos.\n\nPulsa un botón abajo para empezar — o simplemente escribe una pregunta y el asistente te ayudará.",
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
    },
    "fr": {
        "choose_language": "🌐 Veuillez choisir votre langue :",
        "language_set": "✅ Langue définie : {lang}.",
        "welcome": "👋 <b>Bienvenue !</b> Ce bot gère votre abonnement, votre clé API et vos appareils.\n\nAppuyez sur un bouton ci-dessous pour commencer — ou posez simplement une question, l'assistant vous aidera.",
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
    },
}


def t(lang_code: str | None, key: str, **kwargs) -> str:
    table = STRINGS.get(normalize(lang_code), STRINGS[DEFAULT_LANG])
    s = table.get(key) or STRINGS[DEFAULT_LANG].get(key, key)
    return s.format(**kwargs) if kwargs else s
