# Telegram Stars — как подключить в APIX

Коротко: для **Telegram Stars не нужен внешний эквайринг** вроде Stripe/ЮKassa/T-Bank.
Если бот продаёт **цифровые товары/услуги** внутри Telegram, оплата идёт в валюте **`XTR`** через Telegram Stars.

В текущем проекте Stars уже поддержаны кодом:
- бот: `bot/handlers/stars_payment.py`
- mini app API: `api/miniapp_routes.py` (`POST /api/v1/topup/stars`)
- учёт транзакций: `transactions.provider = telegram_stars`

---

## 1. Что нужно заранее

1. Действующий Telegram-бот через **@BotFather**
2. Боевой токен бота в `.env`:
   - `BOT_TOKEN=...`
3. HTTPS-домен и рабочий webhook бота
4. Понимание, что Stars подходят для **цифровых товаров**:
   - кредиты
   - генерации
   - подписки
   - внутриигровые/внутрисервисные цифровые штуки

---

## 2. Где регистрироваться

### Для Stars отдельно регистрироваться в банке/эквайринге не нужно

В отличие от T-Bank / CryptoBot:
- **не нужен merchant account**
- **не нужен provider token платёжной системы**
- **не нужно заводить кассу**
- **не нужно вручную подключать провайдера в BotFather для Stars**

Пользователь сам покупает Stars внутри Telegram, а бот принимает оплату в `XTR`.

---

## 3. Что нужно сделать в BotFather

Минимум:
1. Создать бота или использовать существующего
2. Проверить, что у бота:
   - есть username
   - выставлен production token
   - настроен webhook
3. При желании настроить:
   - `/setdescription`
   - `/setabouttext`
   - `/setuserpic`
   - меню команд `/setcommands`

### Важно
Для **Telegram Stars** не нужен отдельный payment provider token.
В коде для Stars используется:
- `currency="XTR"`
- `provider_token=""` или без него, в зависимости от клиента/API-обёртки

В этом проекте сейчас используется пустой `provider_token`, и это уже работает.

---

## 4. Что уже должно быть включено в проекте

### Бот-оплата Stars
Файл: `bot/handlers/stars_payment.py`

Что делает flow:
1. Пользователь выбирает `⭐ Telegram Stars`
2. Выбирает тариф
3. Бот вызывает `send_invoice(...)`
4. Telegram присылает:
   - `pre_checkout_query`
   - `successful_payment`
5. Бот подтверждает транзакцию и начисляет `💋`

### Mini app оплата Stars
Файл: `api/miniapp_routes.py`

Что делает flow:
1. Mini app вызывает `POST /api/v1/topup/stars`
2. Сервер делает `bot.create_invoice_link(...)`
3. Клиент открывает invoice внутри Telegram
4. После успешной оплаты Telegram шлёт success в бот
5. Баланс пополняется автоматически

---

## 5. Какие места обязательно проверить

### `.env`
Нужны как минимум:
- `BOT_TOKEN`
- `BOT_USERNAME`
- `WEBHOOK_URL`
- `WEBHOOK_PATH`

### Webhook бота
Проверь, что Telegram webhook живой:
- `POST /webhook/telegram`

### Кнопки пополнения
Проверь:
- бот: `topup:stars`
- mini app: метод `stars`

### Тарифы
В БД у активных тарифов должны быть:
- `key`
- `label`
- `credits`
- `price_rub`
- желательно `price_stars`

Если `price_stars` пустой, проект сейчас считает fallback как:
- `max(1, int(price_rub / 10))`

---

## 6. Как проходит оплата технически

### Для обычного bot flow
Используется `send_invoice(...)`:
- `currency="XTR"`
- `prices=[LabeledPrice(...)]`
- `payload="stars:<tx_id>:<plan_key>"`

Далее:
1. Telegram показывает invoice
2. Пользователь платит Stars
3. Приходит `successful_payment`
4. Бот находит транзакцию
5. Транзакция помечается как оплаченная
6. Пользователю начисляются кредиты

### Для mini app flow
Используется `create_invoice_link(...)`, потом эта ссылка открывается через Telegram WebApp.

---

## 7. Что проверить после подключения

### Обязательный smoke test
1. Открыть бота
2. Нажать `Пополнить`
3. Нажать `⭐ Telegram Stars`
4. Выбрать тариф
5. Убедиться, что invoice открывается без ошибки
6. Провести тестовую/боевую оплату
7. Проверить:
   - запись в `transactions`
   - смену статуса на `paid`
   - начисление `💋`
   - сообщение об успешном пополнении

### Для mini app отдельно
1. Открыть `/app` внутри Telegram
2. Нажать `Пополнить`
3. Выбрать `⭐ Stars`
4. Выбрать тариф
5. Проверить, что invoice link открывается внутри Telegram
6. После оплаты проверить баланс

---

## 8. Частые проблемы

### 1) Invoice не открывается
Проверь:
- запуск именно внутри Telegram
- валидный `BOT_TOKEN`
- что бот не сломан по webhook
- что используется `currency="XTR"`

### 2) HTTP 500 при повторном нажатии на один и тот же тариф
Это уже было исправлено в проекте.
Причина была в duplicate pending transaction по `external_id`.
Теперь pending-транзакция переиспользуется идемпотентно.

### 3) Деньги списались, а кредиты не пришли
Проверь:
- пришёл ли `successful_payment`
- существует ли transaction
- не обработана ли уже транзакция ранее
- нет ли ошибок в `.logs/bot.log`

### 4) В mini app всё ок, а в боте нет
Проверь отдельно оба flow:
- bot invoice (`send_invoice`)
- mini app invoice link (`create_invoice_link`)

Они похожи, но это разные точки входа.

---

## 9. Где смотреть логи

Основное:
- `.logs/bot.log`
- `.logs/watcher.log`

Полезно искать по словам:
- `Stars`
- `successful_payment`
- `invoice`
- `topup/stars`
- `duplicate key`

---

## 10. Что НЕ нужно для Stars

Не нужно:
- регистрироваться в T-Bank
- подключать Stripe
- заводить CryptoBot
- получать `provider_token` от внешней платёжки
- настраивать отдельный webhook платёжного провайдера

Это всё нужно для других способов оплаты, но **не для Telegram Stars**.

---

## 11. Что может понадобиться дополнительно

Если хочешь полноценный production checklist, потом можно отдельно добавить:
- возвраты/refund flow для Stars
- админ-экран по Stars-транзакциям
- алерт на зависшие pending-транзакции
- отдельный smoke script для Stars after deploy

---

## 12. Короткая памятка

Если совсем коротко:
1. Создай бота через `@BotFather`
2. Поставь `BOT_TOKEN`
3. Подними webhook
4. Убедись, что в коде invoice идёт в `XTR`
5. Проверь `send_invoice` / `create_invoice_link`
6. Проведи оплату
7. Проверь начисление `💋`

---

## Полезная ссылка

Официальная документация Telegram:
- https://core.telegram.org/bots/payments-stars
