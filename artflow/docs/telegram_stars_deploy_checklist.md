# Telegram Stars — deploy checklist

Используй этот список перед релизом или сразу после деплоя.

## Перед деплоем

- [ ] В `.env` заполнен `BOT_TOKEN`
- [ ] В `.env` заполнен `BOT_USERNAME`
- [ ] В `.env` заполнен `WEBHOOK_URL`
- [ ] Бот существует в `@BotFather` и отвечает
- [ ] В боте включены команды `/start`, `/menu`, `/help`
- [ ] В БД есть активные `price_plans`
- [ ] Для тарифов проверены `price_rub`, `credits`, `price_stars`
- [ ] Если `price_stars` не задан, fallback `price_rub / 10` вас устраивает

## После деплоя

- [ ] Открывается бот в Telegram
- [ ] Открывается mini app внутри Telegram
- [ ] Кнопка `Пополнить` работает в боте
- [ ] Кнопка `⭐ Telegram Stars` видна в боте
- [ ] Кнопка `⭐ Stars` видна в mini app
- [ ] `POST /webhook/telegram` живой
- [ ] `POST /api/v1/topup/stars` возвращает invoice link без 500

## Smoke в боте

- [ ] Нажать `Пополнить`
- [ ] Нажать `⭐ Telegram Stars`
- [ ] Выбрать тариф
- [ ] Открылся invoice
- [ ] После оплаты пришло `successful_payment`
- [ ] В `transactions` статус стал `paid`
- [ ] Пользователю начислены `💋`

## Smoke в mini app

- [ ] Нажать `Пополнить`
- [ ] Выбрать `⭐ Stars`
- [ ] Выбрать тариф
- [ ] Invoice открылся внутри Telegram
- [ ] После оплаты баланс обновился

## Что смотреть, если что-то сломалось

- `.logs/bot.log`
- `.logs/watcher.log`
- поиск по словам: `Stars`, `successful_payment`, `invoice`, `topup/stars`, `duplicate key`

## Критичные симптомы

### Invoice не открывается
Проверь:
- запуск внутри Telegram
- корректный `BOT_TOKEN`
- что invoice идёт в `XTR`

### Повторный запуск тарифа даёт 500
Проверь idempotency pending transaction по `external_id`.

### Оплата прошла, но баланс не изменился
Проверь обработчик `successful_payment` и статус транзакции в БД.
