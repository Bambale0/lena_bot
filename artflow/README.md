# APIX — Telegram AI Generation Bot

Telegram-бот и мини-приложение для генерации изображений, видео и музыки с помощью AI-моделей. Поддерживает кредитную систему, реферальную программу, маркетплейс промптов и несколько платёжных провайдеров.

---

## Архитектура

```
artflow/
├── main.py                 # FastAPI-приложение, webhook-роуты
├── run_polling.py          # Режим polling (local dev)
│
├── core/
│   ├── config.py           # Pydantic-Settings (.env)
│   └── logger.py           # Настройка логирования
│
├── bot/
│   ├── handlers/           # Aiogram-роутеры
│   │   ├── start.py        # /start, welcome
│   │   ├── image_gen.py    # Генерация изображений (KIE.AI)
│   │   ├── video_gen.py    # Генерация видео (KIE.AI / CometAPI)
│   │   ├── music_gen.py    # Генерация музыки
│   │   ├── midjourney.py   # Midjourney (imagine, blend, describe, video)
│   │   ├── feed.py         # Публичная лента генераций
│   │   ├── balance.py      # Баланс кредитов
│   │   ├── payment.py      # Оплата (Юкасса, CryptoBot, Т-Банк)
│   │   ├── admin.py        # Админ-панель
│   │   └── marketplace.py  # Маркетплейс промптов
│   │
│   ├── middlewares/
│   │   ├── auth.py         # Авто-регистрация, 3-уровневые рефералы, бан
│   │   ├── db.py           # Инъекция сессии БД в хендлеры
│   │   └── throttling.py   # Антиспам через Redis
│   │
│   ├── keyboards/          # Inline/reply-клавиатуры
│   │   ├── models.py       # Клавиатуры выбора модели, параметров
│   │   ├── payment.py      # Кнопки оплаты
│   │   ├── feed.py         # Кнопки ленты
│   │   └── main_menu.py    # Главное меню
│   │
│   ├── states/             # FSM-состояния (aiogram FSM)
│   ├── ui/                 # Шаблоны сообщений (экраны меню)
│   ├── filters/            # Фильтр is_admin
│   ├── services/           # session_service.py (работа с ImageSession)
│   └── utils/telegram_ui.py
│
├── api/
│   ├── web/               # Standalone web API /api/web/* для сайта
│   ├── image_service.py    # Интеграция с KIE.AI (изображения)
│   ├── video_service.py    # Интеграция с KIE.AI/CometAPI (видео)
│   ├── music_service.py    # Интеграция с KIE.AI (музыка)
│   ├── midjourney_service.py
│   ├── comet_client.py     # HTTP-клиент CometAPI
│   ├── kieai_client.py     # HTTP-клиент kie.ai
│   ├── aivideoapi_client.py # HTTP-клиент aivideoapi.ai (HappyHorse)
│   ├── kie_model_specs.py  # Спецификации моделей KIE (параметры)
│   ├── kie_webhook.py      # Парсинг payload KIE webhook
│   ├── polling.py          # Long-polling для ожидания результата
│   ├── public_files.py     # Зеркалирование файлов (stable public URLs)
│   ├── webapp_auth.py      # Верификация Telegram WebApp initData
│   └── webapp_routes.py    # FastAPI-роутер /api/webapp/*
│
├── db/
│   ├── models.py           # SQLAlchemy ORM-модели
│   ├── repository.py       # CRUD-функции (users, generations, ...)
│   ├── prompt_repository.py # CRUD для UserPrompt (маркетплейс)
│   ├── session.py          # AsyncSessionLocal, get_session
│   ├── seed.py             # Начальные данные (тарифы, модели)
│   └── migrations/         # Alembic-миграции (9 версий)
│
├── payments/
│   ├── cryptobot.py        # CryptoBot (крипто-оплата)
│   ├── tbank.py            # Т-Банк эквайринг
│   └── yookassa.py         # ЮКасса
│
├── webapp/                 # React + Vite мини-приложение
│   └── src/
│       ├── App.tsx          # Корневой компонент (роутинг страниц)
│       ├── api/client.ts    # Fetch-обёртки над /api/webapp/*
│       ├── pages/          # Home, Feed, Library, History, Profile, Referrals
│       ├── components/     # AppShell, Header, BottomNav, FeedCard, PromptCard…
│       ├── theme/themes.ts  # Определения тем (neonPink, …)
│       └── telegram.ts     # Telegram WebApp SDK-обёртка
│
├── landing/                # Standalone web-сайт для / (vanilla JS)
│   ├── index.html
│   ├── css/riot-site.css
│   └── js/riot-site.js
│
├── web/static/prompt-riot/ # Прототип/референс prompt-riot интерфейса
│
├── tests/                  # Pytest suite (backend contracts, providers, web API)
│   ├── conftest.py
│   ├── test_bot_tester.py
│   ├── test_keyboards_and_ui.py
│   ├── test_kie_webhook.py
│   ├── test_marketplace_previews.py
│   ├── test_middlewares.py
│   ├── test_project_smoke.py
│   ├── test_prompt_repository.py
│   ├── test_public_files.py
│   ├── test_webapp_auth.py
│   └── test_webapp_routes.py
│
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
└── requirements.txt
```

---

## Схема данных (PostgreSQL)

| Таблица | Назначение |
|---|---|
| `users` | Пользователи, баланс, реф-коды (3 уровня рефералов), бан |
| `generations` | Записи генераций: модель, статус, task_id, result_url, лайки |
| `image_sessions` | Сессия настроек изображения (модель, соотношение, ref-файл) |
| `transactions` | Платёжные транзакции (pending→paid/failed/refunded) |
| `referral_withdrawal_requests` | Заявки на вывод реф-бонусов |
| `price_plans` | Тарифы пополнения (редактируется через /admin) |
| `model_costs` | Стоимость генерации в кредитах (редактируется через /admin) |
| `user_prompts` | Маркетплейс промптов (статус: pending/approved/rejected) |

**Enum-типы:** `GenerationType`, `GenerationStatus`, `ImageSessionStatus`, `ImageGenerationAction`, `TransactionStatus`, `PaymentProvider`, `WithdrawalStatus`, `PromptCategory`, `PromptStatus`

---

## Технологический стек

| Компонент | Технология |
|---|---|
| Python | 3.12 |
| Bot framework | aiogram 3.13 |
| Web framework | FastAPI 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 (async) + asyncpg |
| Миграции | Alembic (9 версий) |
| FSM-хранилище | Redis (aiogram RedisStorage) |
| Антиспам | Redis (ThrottlingMiddleware) |
| Mini App Frontend | React + TypeScript + Vite |
| Public Web Frontend | HTML + CSS + vanilla JavaScript |
| Деплой | Docker Compose (app + postgres + redis + nginx) |
| Тесты | pytest + pytest-asyncio |

---

## AI-провайдеры и модели

### Изображения
| Модель | Провайдер | Кредитов |
|---|---|---|
| Seedream 4.5 | KIE.AI | 3 |
| Grok Imagine T2I / I2I | KIE.AI | 3 |
| WAN 2.7 Image Pro | KIE.AI | 5 |
| Nano Banana / 2 / Pro | KIE.AI | 2–4 |
| Midjourney (imagine/blend/describe) | CometAPI | 10–12 |

### Видео
| Модель | Провайдер | Кредитов |
|---|---|---|
| Kling 2.6 T2V / I2V / Motion | KIE.AI | 30–40 |
| Kling 3.0 / Motion | KIE.AI | 40–50 |
| WAN 2.7 T2V / I2V | KIE.AI | 25–30 |
| Seedance 2 / Fast | KIE.AI | 25–35 |
| Grok T2V / I2V | KIE.AI | 35 |
| HappyHorse T2V / I2V | aivideoapi.ai | 25–30 |
| Veo 3 / Fast / Lite | CometAPI | 35–70 |
| Midjourney Video | CometAPI | 15 |

---

## Платёжные системы

| Провайдер | Webhook URL | Валюта |
|---|---|---|
| Telegram Stars | Telegram native flow | XTR |
| ЮКасса | `/webhook/yookassa` | RUB |
| Т-Банк (Тинькофф) | `/webhook/tbank` | RUB |
| CryptoBot | `/webhook/cryptobot` | Крипта |

Подробная инструкция по Stars: `docs/telegram_stars_setup.md`

Все вебхуки верифицируются подписью перед обработкой. Транзакции идемпотентны — повторный вебхук не начисляет кредиты дважды.

---

## Реферальная система

- **3 уровня** глубины: L1 (+20 кр) → L2 (+10 кр) → L3 (записывается, без бонуса по умолчанию)
- Реферальный код передаётся через `?start=<code>` в ссылке на бота
- Обрабатывается автоматически в `AuthMiddleware` при регистрации нового пользователя
- Пользователь получает уведомление при приходе реферала
- Вывод реф-бонусов через `ReferralWithdrawalRequest` с ручной проверкой администратором

---

## Webhook-архитектура

```
Интернет
    │
    ▼
 Nginx (443) → SSL termination
    │
    ▼
 Uvicorn :8000 (FastAPI / main.py)
    │
    ├── POST /webhook/telegram        → aiogram Dispatcher → handlers
    ├── POST /webhook/cryptobot       → подтверждение оплаты CryptoBot
    ├── POST /webhook/tbank           → подтверждение оплаты Т-Банк
    ├── POST /webhook/kie             → callback завершённой генерации KIE.AI
    ├── GET  /                        → standalone web-сайт из landing/
    ├── GET  /api/web/*               → Web API сайта (Telegram login / dev-token)
    ├── GET  /api/webapp/*            → WebApp API (auth via initData)
    ├── GET  /app                     → React SPA (статика из webapp/dist)
    └── GET  /static/upload/*         → зеркалированные файлы (публичные URL)
```

---

## Поток генерации изображения

```
Пользователь → выбирает модель → выбирает параметры (ratio, quality, count)
    → отправляет промпт (текст) или фото (референс)
    → бот списывает кредиты → создаёт Generation(status=pending)
    → отправляет задачу в KIE.AI
    → если KIE.AI не принял задачу, пробует CometAPI fallback
    → сохраняет task_id, статус → processing
    → KIE.AI или CometAPI вызывает /webhook/kie
    → бот зеркалирует результат (mirror_url)
    → finish_generation(result_url)
    → отправляет фото пользователю с клавиатурой (remix / repeat / settings)
    → ImageSession обновляется (last_result_url, last_generation_id)
```

При ошибке: кредиты возвращаются автоматически, пользователь уведомляется.

---

## Тарифные планы (по умолчанию)

| Ключ | Кредиты | Цена |
|---|---|---|
| `credits_100` | 100 | 199 ₽ |
| `credits_300` | 300 | 499 ₽ |
| `credits_1000` | 1000 | 1 490 ₽ |

Приветственный бонус: **15 кредитов**.

---

## Мини-приложение (WebApp)

React-SPA, встроенное в Telegram WebApp. Доступно по `/app`.

**Страницы:** Home · Feed · Library (маркетплейс промптов) · History · Referrals · Profile

**API-эндпоинты:**

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/webapp/me` | Профиль + активная ImageSession |
| GET | `/api/webapp/feed` | Лента (trending / top_day / new) |
| POST | `/api/webapp/feed/{id}/like` | Лайк |
| POST | `/api/webapp/feed/{id}/remix` | Ремикс (копирует настройки в ImageSession) |
| GET | `/api/webapp/prompts` | Маркетплейс промптов |
| GET | `/api/webapp/prompts/{id}` | Детали промпта |
| POST | `/api/webapp/prompts/{id}/use` | Применить промпт (создаёт ImageSession) |
| GET | `/api/webapp/history` | История генераций |
| GET | `/api/webapp/referrals` | Реферальная статистика |

Аутентификация: Telegram `initData` (HMAC-SHA256 с BOT_TOKEN). Реализована в `api/webapp_auth.py`.

---

## Standalone Web-Сайт

Отдельный web-интерфейс доступен на `/` и обслуживается из `landing/`. Он не ведёт пользователя в mini app: до авторизации показывает витрину-презентацию, после входа через Telegram переключается в полноценную студию генерации контента.

**Ключевые части:**

| Компонент | Назначение |
|---|---|
| `landing/index.html` | Продуктовый вход и сценарии создания |
| `landing/css/prototype-premium.css` | Визуальный стиль сайта и кабинета |
| `landing/js/prototype-premium.js` | Vanilla JS: авторизация, каталог, создание, кабинет |
| `api/web/` | Web API поверх существующих сущностей `User`, `Generation`, `UserPrompt`, `PricePlan` |

**Web API:**

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/web/health` | Healthcheck web-слоя |
| GET | `/api/web/me` | Профиль авторизованного пользователя |
| GET | `/api/web/feed` | Лента генераций |
| GET | `/api/web/prompts` | Библиотека и маркетплейс промптов |
| GET | `/api/web/landing` | Единый публичный payload для сайта |
| GET | `/api/web/price-plans` | Тарифы пополнения |
| POST | `/api/web/auth/telegram-login` | Вход через Telegram Login Widget |
| POST | `/api/web/generate/image` | Создание картинки |
| POST | `/api/web/generate/video` | Создание видео |
| POST | `/api/web/generate/music` | Создание музыки |
| POST | `/api/web/assistant` | Помощник кабинета |

Студия использует web-обертки `/api/web/models/*`, `/api/web/generate/*`, `/api/web/billing/*`, чтобы сайт не зависел от внутренних mini app маршрутов.

Подробнее о UX-архитектуре и текущем frontend-анализе: `docs/web_studio_frontend.md`.
Workflow для frontend/dev agents: `docs/frontend-agent-workflow.md`.

**MCP для агентов разработки:**

- `Context7` — основной источник актуальной документации и best practices для backend, frontend, тестов, интеграций и CI.
- `shadcn` — обязательный MCP для frontend/UI задач: поиск компонентов, паттернов интерфейса и shadcn-compatible референсов.
- Секреты MCP не хранятся в репозитории; они настраиваются в пользовательском Codex config.

---

## Конфигурация (.env)

```dotenv
# Telegram
BOT_TOKEN=...
BOT_USERNAME=apix_ai_bot
WEBHOOK_URL=https://yourdomain.com
WEBHOOK_SECRET=change_me_secret
ADMIN_IDS=[123456789]

# DB
DATABASE_URL=postgresql+asyncpg://bot:password@postgres:5432/artflow
REDIS_URL=redis://redis:6379

# AI провайдеры
COMET_API_KEY=...
KIE_AI_KEY=...
AIVIDEOAPI_KEY=...
KIE_WEBHOOK_SECRET=...

# Платежи
TBANK_TERMINAL_KEY=...
TBANK_PASSWORD=...
CRYPTOBOT_TOKEN=...
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...

# Бонусы
WELCOME_BONUS_CREDITS=15
REFERRAL_L1_CREDITS=20
REFERRAL_L2_CREDITS=10
```

---

## Запуск

### Продакшн (Docker Compose)

```bash
cd /root/mkdir/lena_bot/artflow
cp .env.example .env   # заполнить переменные при первом деплое
docker compose up -d

# Применить миграции
docker compose exec app alembic upgrade head

# Собрать фронтенд
cd webapp
npm ci
npm run build
```

Production serves the Mini App from `webapp/dist` through the Docker Compose
`app` and `nginx` containers. After frontend changes, rebuild `webapp/dist` and
restart the app container:

```bash
cd /root/mkdir/lena_bot/artflow
docker run --rm -v "$PWD:/workspace" -w /workspace/webapp node:22-alpine sh -lc "npm ci && npm run build"
docker compose restart app
curl -I https://apixbotai.com/app
curl https://apixbotai.com/api/v1/health
```

CI runs backend quality checks and the frontend build on `main` and on pull requests.

### Локальная разработка (polling)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Запустить postgres + redis локально или через docker
docker compose up postgres redis -d

alembic upgrade head
python run_polling.py
```

### Тесты

```bash
pytest tests/ -v
# Тесты используют моки/ASGI-клиент и не требуют реального DB/Redis для основной проверки.
```

---

## Алembic миграции

| Версия | Описание |
|---|---|
| 001 | Начальная схема (users, generations, transactions, plans, costs) |
| 002 | Добавлен провайдер tbank |
| 003 | Таблица image_sessions |
| 004a | Поле last_prompt в image_sessions |
| 004b | Поле reference_url в image_sessions |
| 005 | Merge двух heads 004 |
| 006 | Промпт-маркетплейс (user_prompts) |
| 007 | reference_file_ids (multiple refs) |
| 008 | Метрики ленты (likes_count, shares_count) |
| 009 | referral_withdrawal_requests |

---

## Администрирование (команды /admin)

- Рассылка по всем пользователям
- Просмотр статистики (кол-во юзеров, генераций сегодня, выручка)
- Управление тарифами (`/admin prices`)
- Управление стоимостью моделей (`/admin costs`)
- Бан / разбан пользователей
- Просмотр реферального лидерборда
- Подтверждение/отклонение заявок на вывод реф-бонусов
- Модерация промптов маркетплейса

---

## Диагностика

### PostgreSQL connection refused

`ConnectionRefusedError: [Errno 111] Connection refused` означает, что app не
может подключиться к PostgreSQL. Это диагностический сценарий, а не текущий
статус прода. В продакшне PostgreSQL запущен как Docker Compose service
`postgres` и доступен на хосте через `127.0.0.1:5433`.

Пример лога:

```
ConnectionRefusedError: [Errno 111] Connection refused
INFO: 91.108.5.111 - "POST /webhook/telegram HTTP/1.0" 500 Internal Server Error
```

Если база недоступна, входящие Telegram-обновления могут падать с HTTP 500,
пока app снова не получит подключение к PostgreSQL.

Проверить текущее состояние:

```bash
cd /root/mkdir/lena_bot/artflow
docker compose ps
docker compose exec postgres pg_isready -U bot -d artflow
docker compose exec app python - <<'PY'
import asyncio
from db.session import engine

async def main():
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql("select 1")
        print(result.scalar())

asyncio.run(main())
PY
```

Если PostgreSQL остановлен, поднять его:

```bash
cd /root/mkdir/lena_bot/artflow
docker compose up -d postgres
docker compose up -d --force-recreate app
```
