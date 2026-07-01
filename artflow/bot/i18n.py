"""i18n — мультиязычность с дружелюбным тоном.

Единый стиль текста:
- Дружелюбный, тёплый тон
- Эмодзи для визуального разделения
- Краткие предложения
- Активный залог
- Без канцелярита
"""
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════
# Русский (ru)
# ═══════════════════════════════════════════════════════════════════════════════

_RU = {
    # Общие
    "welcome": "👋 <b>Привет, {name}!</b>\n\nСоздавай фото, видео и музыку с помощью ИИ — всё в одном месте.",
    "welcome_back": "👋 <b>С возвращением, {name}!</b>\n\nРад тебя видеть снова ✨",
    "main_menu": (
        "👋 <b>APIX</b>\n\n"
        "Твоя AI-студия для фото, видео, музыки и сильных промптов.\n"
        "Создавай, тестируй идеи и собирай результат в одном месте.\n\n"
        "Выбирай, что запустить:"
    ),
    "main_menu_with_session": (
        "👋 <b>APIX</b>\n\n"
        "🎨 <b>Текущая серия изображений</b>\n"
        "<b>{model}</b>\n"
        "{ratio} · {quality} · {count}\n\n"
        "Можешь продолжить эту серию или начать новую."
    ),
    "choose_language": "🌍 <b>Выбери язык</b>\n\nChoose your language:",
    "language_changed": "✅ Язык изменён на русский!",
    "language_changed_en": "✅ Language changed to English!",

    # Баланс
    "balance_title": "💎 <b>Твой баланс</b>",
    "balance_credits": "💋: {credits}",
    "user_tg_id": "🆔 ID: <code>{tg_id}</code>",
    "balance_subscription": "Подписка: {status}",
    "balance_sub_active": "✅ До {date}",
    "balance_sub_inactive": "❌ Не активна",
    "balance_costs_title": "<b>Стоимость генерации:</b>",
    "balance_costs_image": "• Изображения: {amount}",
    "balance_costs_video": "• Видео: {amount}",
    "balance_costs_music": "• Музыка: {amount}",
    "balance_costs_midjourney": "• Midjourney: {amount}",
    "balance_topup_hint": "💳 Пополнить баланс можно прямо здесь.",

    # Пополнение
    "topup_title": "💳 <b>Пополнение баланса</b>\n\nВыбери способ:",
    "topup_rub": "💳 Рубли (T-Bank)",
    "topup_crypto": "🪙 Криптовалюта (USDT)",
    "topup_stars": "⭐ Telegram Stars",
    "topup_select_plan": "Выбери тариф:",
    "topup_stars_title": "⭐ <b>Оплата Telegram Stars</b>",
    "topup_stars_desc": "Тариф: {label}\nСтоимость: <b>{stars} ⭐</b>\n\nНажми кнопку ниже для оплаты.",
    "topup_success": "✅ Оплата подтверждена!\nЗачислено: <b>+{credits} 💋</b>\nБаланс: <b>{balance} 💋</b>",
    "topup_tbank_title": "🏦 <b>Оплата через T-Bанк</b>",
    "topup_tbank_desc": "Тариф: {label}\nСумма: <b>{amount} ₽</b>\n\nОткрой ссылку для оплаты картой или через СБП.\n<i>После успешной оплаты 💋 зачислятся автоматически.</i>",
    "topup_crypto_title": "🪙 <b>Оплата криптой</b>",
    "topup_crypto_desc": "Тариф: {label}\nСумма: <b>{amount} USDT</b>\n\nНажми кнопку для оплаты в CryptoBot.\n<i>После оплаты 💋 зачислятся автоматически.</i>",

    # Рефералы
    "referral_title": "👥 <b>Партнёрская программа</b>",
    "referral_link": "Вот твоя ссылка — можешь просто отправить её друзьям:\n<code>{link}</code>",
    "referral_stats": (
        "<b>Сейчас по приглашениям:</b>\n"
        "• Прямые друзья (L1): <b>{l1}</b>\n"
        "• Второй уровень (L2): <b>{l2}</b>\n"
        "• Третий уровень (L3): <b>{l3}</b>"
    ),
    "referral_earned": "💰 <b>Всего заработано: {amount:.2f}₽</b>",
    "referral_available": "💸 <b>Доступно сейчас: {amount:.2f}₽</b>",
    "referral_feed_remix_rewards": "✨ <b>С повторов из ленты заработано: {amount:.2f}₽</b>",
    "referral_withdraw_min": "🏦 <b>Минимальный вывод денег: {amount:.0f}₽</b>",
    "referral_exchange_rate": "💋 <b>Купить поцелуи: {rate}, минимум {min_amount:.0f}₽</b>",
    "referral_pending_withdrawals": "⏳ Уже в обработке: {amount:.2f}₽",
    "referral_conditions": (
        "<b>Как это работает:</b>\n"
        "• Отправляешь другу свою ссылку приглашения\n"
        "• Когда человек впервые приходит по ней в бота — ты получаешь +{bonus} 💋\n"
        "• L1 — это люди, которых пригласил лично ты\n"
        "• L2 — люди, которых пригласили твои L1\n"
        "• L3 — люди, которых пригласили твои L2\n"
        "• Если кто-то из этой цепочки пополняет баланс, тебе приходит комиссия:\n"
        "  — {l1_pct}% с оплат друзей L1\n"
        "  — {l2_pct}% с оплат друзей L2\n"
        "  — {l3_pct}% с оплат друзей L3\n"
        "• С повторов из ленты ты получаешь 5₽ за каждый повтор\n"
        "• Эти деньги копятся отдельно на партнёрском балансе\n"
        "• Их можно вывести деньгами или купить 💋 по обычному курсу: {rate}"
    ),
    "referral_bonus_received": (
        "🎉 По твоей ссылке пришёл новый пользователь!\n"
        "+{bonus} 💋 начислено."
    ),
    "referral_commission": (
        "💰 Партнёрская комиссия: <b>+{amount:.2f}₽</b>\n"
        "Один из рефералов пополнил баланс на {total:.0f}₽."
    ),

    # Вывод
    "withdraw_title": "💸 <b>Вывод денег</b>",
    "withdraw_amount_prompt": (
        "Введи сумму в рублях, которую нужно вывести деньгами.\n"
        "Минимальная сумма вывода: <b>{min_amount:.0f}₽</b>\n"
        "Сейчас доступно: <b>{available:.2f}₽</b>\n"
        "Например: <code>1500</code>"
    ),
    "withdraw_amount_invalid": "Введи сумму в рублях числом, например: <code>1500</code>",
    "withdraw_amount_zero": "Сумма должна быть больше нуля.",
    "withdraw_amount_exceeds": "Недостаточно доступного партнёрского баланса. Сейчас доступно: <b>{available:.2f}₽</b>.",
    "withdraw_amount_min": "Минимальный вывод — <b>{min_amount:.0f}₽</b>.",
    "withdraw_unavailable": "Сейчас вывод недоступен: нужно минимум <b>{min_amount:.0f}₽</b> на партнёрском балансе.",
    "withdraw_details_prompt": "Теперь отправь реквизиты для выплаты одним сообщением.\n\nНапример: банк + телефон / карта / USDT кошелёк.",
    "withdraw_details_short": "Реквизиты слишком короткие. Напиши банк, телефон, карту или кошелёк.",
    "withdraw_created": (
        "✅ Заявка на вывод #{id} создана.\n"
        "Сумма: <b>{amount:.2f}₽</b>\n\n"
        "Админ получит запрос на подтверждение."
    ),
    "exchange_amount_prompt": (
        "💋 <b>Купить поцелуи с партнёрского баланса</b>\n\n"
        "Курс: <b>{rate}</b>\n"
        "Минимальная сумма: <b>{min_amount:.0f}₽</b>\n"
        "Сейчас доступно: <b>{available:.2f}₽</b>\n\n"
        "Введи сумму в рублях.\n"
        "Например: <code>500</code> → <b>50💋</b>"
    ),
    "exchange_amount_invalid": "Введи сумму в рублях числом, например: <code>500</code>",
    "exchange_amount_min": "Минимальная покупка поцелуев — <b>{min_amount:.0f}₽</b>.",
    "exchange_unavailable": "Сейчас покупка поцелуев недоступна: нужно минимум <b>{min_amount:.0f}₽</b> на партнёрском балансе.",
    "exchange_created": "✅ Готово: <b>{rub:.2f}₽</b> обменяли на <b>{credits:.2f}💋</b>.",
    "withdraw_admin_notify": (
        "💸 <b>Новая заявка на вывод #{id}</b>\n\n"
        "Пользователь: @{username} · <code>{tg_id}</code>\n"
        "Имя: <b>{full_name}</b>\n"
        "Сумма: <b>{amount:.2f}₽</b>\n\n"
        "<b>Реквизиты:</b>\n<code>{details}</code>"
    ),

    # Изображения
    "image_menu": "🎨 <b>Генерация изображений</b>\n\nВыбери модель:",
    "image_model_selected": "✅ <b>{model}</b>\n\nВыбери режим:",
    "image_mode_text": "✍️ Текст → Изображение",
    "image_mode_image": "🖼️ Изображение → Изображение",
    "image_upload_prompt": "🖼️ Загрузи изображение для обработки:",
    "image_prompt_hint": "✍️ Введи промпт — опиши, что хочешь получить:",
    "image_generating": "⏳ Генерирую изображение...\nЭто займёт несколько секунд.",
    "image_done": "✅ Готово! Вот твоё изображение:",
    "image_error": "❌ Что-то пошло не так при генерации.\nПопробуй ещё раз или выбери другую модель.",
    "image_not_enough_credits": "😔 Недостаточно 💋 для генерации.\nНужно: <b>{needed}</b>, у тебя: <b>{has}</b>\n\nПополни баланс в меню 💳",

    # Видео
    "video_menu": "🎬 <b>Генерация видео</b>\n\nВыбери модель:",
    "video_model_selected": "✅ <b>{model}</b>\n\nВыбери режим:",
    "video_mode_text": "✍️ Текст → Видео",
    "video_mode_image": "🖼️ Фото → Видео",
    "video_params": "⚙️ <b>Параметры</b> · {model}\nНажимай кнопки (✅ = выбрано), потом <b>Далее</b>:",
    "video_prompt_hint": "✍️ Введи промпт для видео:",
    "video_generating": "⏳ Генерирую видео...\nЭто может занять 1–3 минуты.",
    "video_done": "✅ Видео готово!",
    "video_error": "❌ Ошибка при генерации видео.\nПопробуй другой промпт или модель.",

    # Музыка
    "music_menu": "🎵 <b>Генерация музыки</b>\n\nВведи описание трека:\n<i>Например: лоу-фай хип-хоп для учёбы, расслабляющий</i>",
    "music_generating": "⏳ Создаю трек...\nОбычно это занимает 30–60 секунд.",
    "music_done": "✅ Трек готов! Наслаждайся 🎧",
    "music_error": "❌ Не удалось создать трек.\nПопробуй другое описание.",

    # Midjourney
    "mj_menu": "🧠 <b>Midjourney</b>\n\nВыбери действие:",
    "mj_imagine": "🖌️ Создать изображение",
    "mj_blend": "🖼️ Смешать изображения",
    "mj_describe": "🔍 Описать изображение",
    "mj_video": "🎬 Создать видео",
    "mj_prompt_hint": "✍️ Введи промпт для Midjourney:",
    "mj_generating": "⏳ Midjourney работает...\nОбычно 30–60 секунд.",
    "mj_done": "✅ Готово!",

    # Лента
    "feed_title": "🔥 <b>Лента генераций</b>",
    "feed_empty": "Лента пока пуста.\nБудь первым — поделись своей работой!",
    "feed_like": "❤️ {count}",
    "feed_share": "📤 Поделиться",
    "feed_publish": "🌍 Опубликовать в ленте",
    "feed_published": "✅ Опубликовано в ленте!",

    # Промпты
    "prompts_title": "📚 <b>Библиотека промптов</b>",
    "prompts_empty": "Пока тут пусто.\nОпубликуй первый промпт или загляни позже.",
    "prompt_use": "🎯 Использовать",
    "prompt_like": "❤️ {count}",

    # История
    "history_title": "📋 <b>История генераций</b>",
    "history_empty": "📋 История пуста. Сделай первую генерацию!",
    "history_item": "{icon} {status} <code>{model}</code>\n   <i>{prompt}</i>\n   -{credits} 💋",

    # Админ
    "admin_title": "👑 <b>Панель администратора</b>",
    "admin_stats": "📊 Статистика",
    "admin_users": "👥 Пользователи",
    "admin_payments": "💳 Платежи",
    "admin_referrals": "👥 Рефералы",
    "admin_withdrawals": "💸 Заявки на вывод",

    # Ошибки
    "error_generic": "😔 Что-то пошло не так. Попробуй ещё раз позже.",
    "error_not_found": "🤷 Ничего не найдено.",
    "error_not_available": "Эта функция пока недоступна.",
    "error_forbidden": "🚫 У тебя нет доступа к этой функции.",
    "error_banned": "🚫 Твой аккаунт заблокирован.\nЕсли это ошибка, напиши в саппорт: @LeLu88",

    # Кнопки общие
    "btn_back": "← Назад",
    "btn_main_menu": "🏠 Главное меню",
    "btn_next": "Далее →",
    "btn_cancel": "❌ Отмена",
    "btn_confirm": "✅ Подтвердить",
    "btn_yes": "✅ Да",
    "btn_no": "❌ Нет",

    # Настройки
    "settings_title": "⚙️ <b>Настройки</b>",
    "settings_language": "🌍 Язык",
    "settings_notifications": "🔔 Уведомления",
}


# ═══════════════════════════════════════════════════════════════════════════════
# English (en)
# ═══════════════════════════════════════════════════════════════════════════════

_EN = {
    # General
    "welcome": "👋 <b>Hi, {name}!</b>\n\nCreate photos, videos, and music with AI — all in one place.",
    "welcome_back": "👋 <b>Welcome back, {name}!</b>\n\nGreat to see you again ✨",
    "main_menu": (
        "👋 <b>APIX</b>\n\n"
        "Your AI studio for images, video, music, and high-performing prompts.\n"
        "Create, explore ideas, and ship results in one place.\n\n"
        "Choose what to launch:"
    ),
    "main_menu_with_session": (
        "👋 <b>APIX</b>\n\n"
        "🎨 <b>Current image session</b>\n"
        "<b>{model}</b>\n"
        "{ratio} · {quality} · {count}\n\n"
        "Continue this session or start a new one."
    ),
    "choose_language": "🌍 <b>Choose language</b>\n\nВыбери язык:",
    "language_changed": "✅ Language changed to Russian!",
    "language_changed_en": "✅ Language changed to English!",

    # Balance
    "balance_title": "💎 <b>Your Balance</b>",
    "balance_credits": "💋: {credits}",
    "user_tg_id": "🆔 ID: <code>{tg_id}</code>",
    "balance_subscription": "Subscription: {status}",
    "balance_sub_active": "✅ Until {date}",
    "balance_sub_inactive": "❌ Inactive",
    "balance_costs_title": "<b>Generation cost:</b>",
    "balance_costs_image": "• Images: {amount}",
    "balance_costs_video": "• Video: {amount}",
    "balance_costs_music": "• Music: {amount}",
    "balance_costs_midjourney": "• Midjourney: {amount}",
    "balance_topup_hint": "💳 Top up your balance right here.",

    # Top-up
    "topup_title": "💳 <b>Top Up Balance</b>\n\nChoose a payment method:",
    "topup_rub": "💳 Rubles (T-Bank)",
    "topup_crypto": "🪙 Crypto (USDT)",
    "topup_stars": "⭐ Telegram Stars",
    "topup_select_plan": "Choose a plan:",
    "topup_stars_title": "⭐ <b>Pay with Telegram Stars</b>",
    "topup_stars_desc": "Plan: {label}\nCost: <b>{stars} ⭐</b>\n\nTap the button below to pay.",
    "topup_success": "✅ Payment confirmed!\nAdded: <b>+{credits} 💋</b>\nBalance: <b>{balance} 💋</b>",
    "topup_tbank_title": "🏦 <b>Pay via T-Bank</b>",
    "topup_tbank_desc": "Plan: {label}\nAmount: <b>{amount} ₽</b>\n\nOpen the link to pay by card or SBP.\n<i>will be added automatically after successful payment.</i>",
    "topup_crypto_title": "🪙 <b>Pay with Crypto</b>",
    "topup_crypto_desc": "Plan: {label}\nAmount: <b>{amount} USDT</b>\n\nTap the button to pay via CryptoBot.\n<i>will be added automatically after payment.</i>",

    # Referrals
    "referral_title": "👥 <b>Partner Program</b>",
    "referral_link": "Here is your link — you can just send it to friends:\n<code>{link}</code>",
    "referral_stats": (
        "<b>Your invite stats:</b>\n"
        "• Direct friends (L1): <b>{l1}</b>\n"
        "• Second level (L2): <b>{l2}</b>\n"
        "• Third level (L3): <b>{l3}</b>"
    ),
    "referral_earned": "💰 <b>Total earned: {amount:.2f}₽</b>",
    "referral_available": "💸 <b>Available now: {amount:.2f}₽</b>",
    "referral_feed_remix_rewards": "✨ <b>Earned from feed reuses: {amount:.2f}₽</b>",
    "referral_withdraw_min": "🏦 <b>Minimum cash withdrawal: {amount:.0f}₽</b>",
    "referral_exchange_rate": "💋 <b>Buy kisses: {rate}, minimum {min_amount:.0f}₽</b>",
    "referral_pending_withdrawals": "⏳ Already being processed: {amount:.2f}₽",
    "referral_conditions": (
        "<b>How it works:</b>\n"
        "• You send your invite link to a friend\n"
        "• When a person opens the bot through it for the first time, you get +{bonus} 💋\n"
        "• L1 = people invited directly by you\n"
        "• L2 = people invited by your L1\n"
        "• L3 = people invited by your L2\n"
        "• If someone in this chain tops up, you receive a commission:\n"
        "  — {l1_pct}% from L1 friends' payments\n"
        "  — {l2_pct}% from L2 friends' payments\n"
        "  — {l3_pct}% from L3 friends' payments\n"
        "• From feed reuses, you receive 5 RUB per reuse\n"
        "• This money is stored separately in your partner balance\n"
        "• You can withdraw it in cash or buy 💋 at the standard rate: {rate}"
    ),
    "referral_bonus_received": (
        "🎉 A new user joined via your link!\n"
        "+{bonus} 💋 added."
    ),
    "referral_commission": (
        "💰 Referral commission: <b>+{amount:.2f}₽</b>\n"
        "One of your referrals topped up {total:.0f}₽."
    ),

    # Withdrawal
    "withdraw_title": "💸 <b>Withdraw money</b>",
    "withdraw_amount_prompt": (
        "Enter the ruble amount you want to withdraw as money.\n"
        "Minimum withdrawal amount: <b>{min_amount:.0f}₽</b>\n"
        "Available now: <b>{available:.2f}₽</b>\n"
        "Example: <code>1500</code>"
    ),
    "withdraw_amount_invalid": "Please enter a number, e.g. <code>1500</code>",
    "withdraw_amount_zero": "Amount must be greater than zero.",
    "withdraw_amount_exceeds": "Not enough available referral balance. Available now: <b>{available:.2f}₽</b>.",
    "withdraw_amount_min": "Minimum withdrawal is <b>{min_amount:.0f}₽</b>.",
    "withdraw_unavailable": "Withdrawal is unavailable right now: you need at least <b>{min_amount:.0f}₽</b> on your referral balance.",
    "withdraw_details_prompt": "Now send your payout details in one message.\n\nExample: bank + phone number / card / USDT wallet.",
    "withdraw_details_short": "Details are too short. Please provide bank/account/wallet info.",
    "withdraw_created": (
        "✅ Withdrawal request #{id} created.\n"
        "Amount: <b>{amount:.2f}₽</b>\n\n"
        "Admin will review and confirm."
    ),
    "exchange_amount_prompt": (
        "💋 <b>Buy kisses from partner balance</b>\n\n"
        "Rate: <b>{rate}</b>\n"
        "Minimum amount: <b>{min_amount:.0f}₽</b>\n"
        "Available now: <b>{available:.2f}₽</b>\n\n"
        "Enter the ruble amount.\n"
        "Example: <code>500</code> → <b>50💋</b>"
    ),
    "exchange_amount_invalid": "Please enter a ruble amount, e.g. <code>500</code>",
    "exchange_amount_min": "Minimum kiss purchase is <b>{min_amount:.0f}₽</b>.",
    "exchange_unavailable": "Kiss purchase is unavailable right now: you need at least <b>{min_amount:.0f}₽</b> on your partner balance.",
    "exchange_created": "✅ Done: <b>{rub:.2f}₽</b> exchanged to <b>{credits:.2f}💋</b>.",
    "withdraw_admin_notify": (
        "💸 <b>New withdrawal request #{id}</b>\n\n"
        "User: @{username} · <code>{tg_id}</code>\n"
        "Name: <b>{full_name}</b>\n"
        "Amount: <b>{amount:.2f}₽</b>\n\n"
        "<b>Details:</b>\n<code>{details}</code>"
    ),

    # Images
    "image_menu": "🎨 <b>Image Generation</b>\n\nChoose a model:",
    "image_model_selected": "✅ <b>{model}</b>\n\nChoose a mode:",
    "image_mode_text": "✍️ Text → Image",
    "image_mode_image": "🖼️ Image → Image",
    "image_upload_prompt": "🖼️ Upload an image to process:",
    "image_prompt_hint": "✍️ Enter a prompt — describe what you want:",
    "image_generating": "⏳ Generating image...\nThis will take a few seconds.",
    "image_done": "✅ Done! Here's your image:",
    "image_error": "❌ Something went wrong during generation.\nTry again or pick another model.",
    "image_not_enough_credits": "😔 Not enough 💋 for generation.\nNeed: <b>{needed}</b>, you have: <b>{has}</b>\n\nTop up your balance 💳",

    # Video
    "video_menu": "🎬 <b>Video Generation</b>\n\nChoose a model:",
    "video_model_selected": "✅ <b>{model}</b>\n\nChoose a mode:",
    "video_mode_text": "✍️ Text → Video",
    "video_mode_image": "🖼️ Photo → Video",
    "video_params": "⚙️ <b>Parameters</b> · {model}\nTap buttons (✅ = selected), then <b>Next</b>:",
    "video_prompt_hint": "✍️ Enter a video prompt:",
    "video_generating": "⏳ Generating video...\nThis may take 1–3 minutes.",
    "video_done": "✅ Video is ready!",
    "video_error": "❌ Video generation failed.\nTry a different prompt or model.",

    # Music
    "music_menu": "🎵 <b>Music Generation</b>\n\nDescribe the track:\n<i>Example: lo-fi hip-hop for studying, relaxing</i>",
    "music_generating": "⏳ Creating your track...\nUsually takes 30–60 seconds.",
    "music_done": "✅ Track is ready! Enjoy 🎧",
    "music_error": "❌ Could not create the track.\nTry a different description.",

    # Midjourney
    "mj_menu": "🧠 <b>Midjourney</b>\n\nChoose an action:",
    "mj_imagine": "🖌️ Create Image",
    "mj_blend": "🖼️ Blend Images",
    "mj_describe": "🔍 Describe Image",
    "mj_video": "🎬 Create Video",
    "mj_prompt_hint": "✍️ Enter a Midjourney prompt:",
    "mj_generating": "⏳ Midjourney is working...\nUsually 30–60 seconds.",
    "mj_done": "✅ Done!",

    # Feed
    "feed_title": "🔥 <b>Generation Feed</b>",
    "feed_empty": "Feed is empty.\nBe the first — share your work!",
    "feed_like": "❤️ {count}",
    "feed_share": "📤 Share",
    "feed_publish": "🌍 Publish to Feed",
    "feed_published": "✅ Published to feed!",

    # Prompts
    "prompts_title": "📚 <b>Prompt Library</b>",
    "prompts_empty": "Nothing here yet.\nPublish the first prompt or check back later.",
    "prompt_use": "🎯 Use",
    "prompt_like": "❤️ {count}",

    # History
    "history_title": "📋 <b>Generation History</b>",
    "history_empty": "📋 History is empty. Make your first generation!",
    "history_item": "{icon} {status} <code>{model}</code>\n   <i>{prompt}</i>\n   -{credits} 💋",

    # Admin
    "admin_title": "👑 <b>Admin Panel</b>",
    "admin_stats": "📊 Statistics",
    "admin_users": "👥 Users",
    "admin_payments": "💳 Payments",
    "admin_referrals": "👥 Referrals",
    "admin_withdrawals": "💸 Withdrawal Requests",

    # Errors
    "error_generic": "😔 Something went wrong. Please try again later.",
    "error_not_found": "🤷 Nothing found.",
    "error_not_available": "This feature is not available yet.",
    "error_forbidden": "🚫 You don't have access to this feature.",
    "error_banned": "🚫 Your account is blocked.\nIf this is a mistake, contact support: @LeLu88",

    # Buttons
    "btn_back": "← Back",
    "btn_main_menu": "🏠 Main Menu",
    "btn_next": "Next →",
    "btn_cancel": "❌ Cancel",
    "btn_confirm": "✅ Confirm",
    "btn_yes": "✅ Yes",
    "btn_no": "❌ No",

    # Settings
    "settings_title": "⚙️ <b>Settings</b>",
    "settings_language": "🌍 Language",
    "settings_notifications": "🔔 Notifications",
}


# ═══════════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════════

_TRANSLATIONS = {
    "ru": _RU,
    "en": _EN,
}


def get_text(key: str, lang: str = "ru", **kwargs) -> str:
    """Получить локализованный текст."""
    texts = _TRANSLATIONS.get(lang, _RU)
    text = texts.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            pass
    return text


def t(key: str, lang: str = "ru", **kwargs) -> str:
    """Короткий алиас для get_text."""
    return get_text(key, lang, **kwargs)
