# Mini-App API — Эндпоинты генерации

Base URL: `https://apix.chillcreative.ru/api/v1`

## Авторизация

Все запросы требуют заголовок:
```
X-Telegram-Init-Data: <Telegram WebApp initData>
```
Значение берётся из `window.Telegram.WebApp.initData`. Подписывается HMAC-SHA256 через BOT_TOKEN на сервере.

---

## Пользователь

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/me` | Профиль: баланс, имя, реф-код |

**GET /me — ответ:**
```json
{
  "id": 1,
  "tg_id": 123456789,
  "username": "johndoe",
  "full_name": "John Doe",
  "credits": 42,
  "referral_code": "abc123",
  "referral_balance": 0.0
}
```

---

## Модели

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/models/image` | Список image-моделей с ценами и параметрами |
| GET | `/models/video` | Список video-моделей с ценами и параметрами |

**GET /models/image — элемент ответа:**
```json
{
  "key": "seedream/4.5-text-to-image",
  "display_name": "Seedream 4.5",
  "credits": 2,
  "modes": ["text", "image"],
  "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "2:3", "3:2", "21:9"],
  "quality_options": [
    {"value": "basic", "label": "🔷 2K"},
    {"value": "high",  "label": "💎 4K"}
  ],
  "counts": [1, 2, 4],
  "has_quality": true
}
```

---

## Генерация изображений

| Метод | Путь | Описание |
|-------|------|---------|
| POST | `/generate/image` | Запустить async генерацию изображения |
| GET | `/generations/{id}` | Опросить статус / получить результат |

**POST /generate/image — тело:**
```json
{
  "model": "seedream/4.5-text-to-image",
  "prompt": "cinematic sunset over tokyo, hyperrealistic",
  "aspect_ratio": "16:9",
  "quality": "basic",
  "count": 1,
  "reference_url": null
}
```

**Ответ 202:**
```json
{
  "id": 1001,
  "model": "seedream/4.5-text-to-image",
  "gen_type": "image",
  "prompt": "cinematic sunset...",
  "status": "pending",
  "result_url": null,
  "credits_spent": 2,
  "created_at": "2026-05-08T12:00:00"
}
```

**Поля `quality` для разных моделей:**
| Модель | Значения |
|--------|---------|
| seedream/4.5-text-to-image | `basic` (2K), `high` (4K) |
| nano-banana-pro | `2K`, `4K` |
| nano-banana-2 | `1K`, `2K` |
| остальные | `basic` |

---

## Генерация видео

| Метод | Путь | Описание |
|-------|------|---------|
| POST | `/generate/video` | Запустить async генерацию видео |

**POST /generate/video — тело:**
```json
{
  "model": "kling-3.0/video",
  "prompt": "woman walking through rainy neon streets",
  "mode": "text",
  "duration": 5,
  "aspect_ratio": "16:9",
  "resolution": "720p",
  "image_url": null,
  "grok_mode": "normal"
}
```
> `mode: "image"` → передавать `image_url`; `grok_mode` только для `grok-imagine/*` моделей.

---

## Статус генерации / история

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/generations/{id}` | Один результат (polling) |
| GET | `/history?limit=20` | История генераций пользователя |

**GET /generations/{id} — ответ (done):**
```json
{
  "id": 1001,
  "status": "done",
  "result_url": "https://apix.chillcreative.ru/static/upload/abc123.jpg",
  "credits_spent": 2,
  ...
}
```

**Статусы:** `pending` → `processing` → `done` | `failed`

Рекомендуемый интервал polling: **3–5 сек**.

---

## Лента

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/feed?limit=20` | Публичная лента изображений |
| POST | `/feed/{id}/like` | Поставить лайк |

**GET /feed — элемент:**
```json
{
  "id": 500,
  "model": "seedream/4.5-text-to-image",
  "prompt": "cyberpunk girl...",
  "result_url": "https://...",
  "likes_count": 12,
  "shares_count": 3,
  "aspect_ratio": "9:16",
  "author": "@johndoe"
}
```

---

## Библиотека промптов

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/prompts?category=image&page=1&limit=20` | Список промптов |
| GET | `/prompts/{id}` | Детали промпта |
| POST | `/prompts` | Отправить промпт на модерацию |

**Категории:** `image`, `video`, `midjourney`, `other`

**POST /prompts — тело:**
```json
{
  "title": "Cyberpunk portrait",
  "description": "Детальный портрет в стиле киберпанк",
  "prompt_text": "cyberpunk female portrait, neon lights, detailed...",
  "category": "image"
}
```

---

## Тарифы и оплата

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/plans` | Список активных тарифов |
| POST | `/topup/tbank` | Создать инвойс T-Bank → `pay_url` |
| POST | `/topup/crypto` | Создать инвойс CryptoBot → `pay_url` |

**GET /plans — элемент:**
```json
{
  "key": "credits_100",
  "title": "100 кредитов",
  "credits": 100,
  "price_rub": 199.0,
  "price_usdt": 2.21
}
```

**POST /topup/tbank — тело:**
```json
{ "plan_key": "credits_100" }
```

**Ответ:**
```json
{
  "pay_url": "https://securepay.tinkoff.ru/...",
  "transaction_id": 42,
  "credits": 100,
  "amount_rub": 199.0
}
```

---

## Коды ошибок

| Код | Причина |
|-----|---------|
| 401 | Невалидный/отсутствующий `X-Telegram-Init-Data` |
| 402 | Недостаточно кредитов |
| 403 | Пользователь заблокирован |
| 404 | Ресурс не найден |
| 422 | Невалидные параметры запроса |
| 429 | Превышен лимит одновременных генераций (макс. 6) |
| 502 | Ошибка внешнего AI-сервиса |

**Формат ошибки:**
```json
{ "detail": "Insufficient credits: need 4, have 1" }
```

---

## Файлы реализации

| Файл | Назначение |
|------|-----------|
| `api/miniapp_routes.py` | Все FastAPI-роуты `/api/v1/*` |
| `api/miniapp_auth.py` | Верификация Telegram initData |
