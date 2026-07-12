# LLM-инструкция: как разработать AI Telegram-бота уровня APIX

Дата аудита: 2026-06-13  
Проект-референс: `/root/mkdir/lena_bot/artflow`

Этот документ - карта проекта и практическая инструкция для LLM, которой нужно спроектировать и разработать похожего по смыслу и функционалу бота. Цель - не копировать бренд APIX и конкретные тексты, а воспроизвести архитектурный паттерн: Telegram AI-студия с генерацией изображений, видео и музыки, платежами, кредитной экономикой, лентой работ, маркетплейсом промптов, реферальной системой, web/mini app поверхностями и админкой.

## 1. Что это за продукт

Проект представляет собой AI-студию, где пользователь:

- заходит через Telegram-бота, Telegram Mini App или web-сайт;
- получает приветственные кредиты;
- создает изображения, видео, музыку и Midjourney-задачи;
- загружает референсы, повторяет и ремиксит свои результаты;
- публикует удачные результаты в публичную ленту;
- берет чужой результат из ленты и запускает remix без раскрытия чужого промпта;
- пользуется библиотекой промптов, лайкает, шарит и загружает свои промпты на модерацию;
- пополняет баланс через T-Bank, CryptoBot, Lava.top или Telegram Stars;
- приглашает пользователей по реферальной ссылке и получает бонусы/комиссии;
- выводит или конвертирует реферальный баланс;
- общается с ассистентом;
- в роли администратора управляет ценами, моделями, пользователями, промокодами, выводами, рассылками и AI-админом.

Главная инженерная идея: все пользовательские поверхности работают поверх одной доменной модели и одного набора сервисов генерации. Telegram-бот, mini app и web-сайт не должны иметь разные бизнес-правила начисления кредитов, статусов задач, реферальных выплат или прав публикации.

## 2. Технологический стек

Фактический стек проекта:

- Python backend: FastAPI `0.115.0`, Uvicorn, aiogram `3.27.0`.
- Хранилище: PostgreSQL через SQLAlchemy `2.0` async + asyncpg.
- Миграции: Alembic.
- FSM и технический кэш: Redis, aiogram RedisStorage.
- HTTP-клиенты: httpx.
- Изображения/превью: Pillow.
- Bot UI: aiogram routers, callback keyboards, FSM states.
- Mini app: React `19.2.6` + Vite `8.0.11` в `webapp/`.
- Public web: статический vanilla HTML/CSS/JS сайт в `landing/`.
- Тесты: pytest, pytest-asyncio, pytest-mock.
- Линтинг: Ruff, Python target `py312`.

Важное расхождение: `Dockerfile` использует `python:3.11-slim`, а локальные скрипты и `pyproject.toml` ориентируются на Python 3.12+. Для нового проекта лучше сразу унифицировать версию Python.

## 3. Карта репозитория

Ключевые файлы и директории:

```text
main.py                       # единое FastAPI-приложение, Telegram webhook, provider webhooks, mounts
run_polling.py                # локальный polling-режим, сейчас покрывает только часть routers
core/config.py                # pydantic-settings, env vars, feature flags, provider secrets
core/broadcast_scheduler.py   # отложенные рассылки

bot/
  handlers/                   # Telegram flows: start, image, video, music, payments, admin, feed, prompts
  keyboards/                  # модельные capability-карты и inline keyboards
  middlewares/                # DB session, auth/auto-register, throttling
  services/                   # main menu context, broadcasts, admin AI, maintenance mode
  states/                     # aiogram FSM states
  i18n.py                     # ru/en тексты

api/
  image_service.py            # image generation facade: KIE primary, Comet fallback
  video_service.py            # video generation facade: KIE/Veo primary, Comet fallback
  music_service.py            # KIE Suno music generation
  midjourney_service.py       # CometAPI Midjourney endpoints
  kie_model_specs.py          # центральная карта model key -> provider payload
  kieai_client.py             # KIE HTTP client
  public_files.py             # local mirroring, public URLs, previews, file extensions
  miniapp_routes.py           # Telegram Mini App API under /api/v1
  web/                        # public site API under /api/web

db/
  models.py                   # ORM models and enums
  repository.py               # domain operations and invariants
  prompt_repository.py        # prompt marketplace
  seed.py                     # default tariffs and model costs
  migrations/versions/        # Alembic migrations

payments/
  cryptobot.py                # CryptoBot invoice and signature verification
  tbank.py                    # T-Bank Init/GetState/notifications
  lava.py                     # Lava invoice creation and payment URL cache

webapp/
  src/main.jsx                # Telegram Mini App React client
  src/style.css
  package.json

landing/
  index.html                  # public entry
  studio.html                 # standalone web studio
  gallery.html                # public feed
  models.html                 # model catalog
  model.html                  # model detail page
  account.html                # user cabinet
  css/prototype-premium.css
  js/prototype-premium.js

tests/                        # unit/API contract/provider/webhook tests
tools/codex_static_checks.sh  # required verification command
```

Для разработки аналога держите разделение таким же:

- Telegram bot logic - в `bot/`.
- Provider clients and HTTP APIs - в `api/`.
- Domain state and money/credits invariants - в `db/repository.py`.
- Web API for standalone site - в `api/web/`.
- Telegram mini app API - в `api/miniapp_routes.py`.
- Static public site - в `landing/`.
- Telegram Mini App frontend - в `webapp/`.

## 4. Runtime-архитектура

Упрощенная схема:

```text
Telegram user
  -> Telegram webhook POST /webhook/telegram
  -> FastAPI main.py
  -> aiogram Dispatcher
  -> DB/Auth/Throttle middleware
  -> handler FSM
  -> repository.spend_credits()
  -> create Generation(status=pending)
  -> provider service creates async task
  -> store provider task_id

Provider callback
  -> /webhook/kie, /webhook/kie/music, /webhook/comet/midjourney
  -> verify secret/signature
  -> find Generation by task_id
  -> mirror result URLs into /static/upload
  -> repository.finish_generation()
  -> publish realtime event
  -> notify Telegram user if needed

Web/Mini App user
  -> /api/v1/* or /api/web/*
  -> same repository and provider services
  -> WebSocket /api/web/ws/generations or /api/realtime
  -> generation status/result delivered to frontend
```

Главные правила:

- Запуск генерации всегда асинхронный, даже если provider иногда возвращает direct result.
- Кредит списывается до отправки provider task.
- При ошибке старта или финальном failed статусе кредит возвращается.
- Provider callback должен быть идемпотентным.
- `Generation.task_id` - связка с provider task. Для web-задач используется prefix `web:`; для Comet fallback - `comet:<kind>:<raw_id>`.
- `finish_generation()` должен быть единственной нормальной точкой перехода в `done`.

## 5. Конфигурация и env

Минимальные группы env vars:

- Bot: `BOT_TOKEN`, `BOT_USERNAME`, `WEBHOOK_URL`, `WEBHOOK_PATH`, `WEBHOOK_SECRET`.
- Admin: `ADMIN_IDS`.
- API: `ENV`, `API_HOST`, `API_PORT`, `WEB_PUBLIC_URL`, `APIX_WEB_DEV_AUTH`.
- DB/Redis: `DATABASE_URL`, `REDIS_URL`.
- AI providers: `KIE_AI_KEY`, `KIE_WEBHOOK_SECRET`, `COMET_API_KEY`, `COMET_BASE_URL`, `MIDJOURNEY_WEBHOOK_SECRET`, `AIVIDEOAPI_KEY`.
- Payments: `CRYPTOBOT_TOKEN`, `TBANK_TERMINAL_KEY`, `TBANK_PASSWORD`, `LAVA_API_KEY`, `LAVA_OFFER_ID_*`, `TELEGRAM_STARS_ENABLED`.
- Web auth: `WEB_AUTH_EMAIL_ENABLED`, `RESEND_*`, `SMTP_*`.
- Economy: `WELCOME_BONUS_CREDITS`, `REFERRAL_L1_CREDITS`, `REFERRAL_COMMISSION_L1/L2/L3`, `REFERRAL_WITHDRAW_MIN_RUB`, `REFERRAL_EXCHANGE_*`.
- Public files: `STATIC_UPLOAD_DIR`, `STATIC_UPLOAD_URL_PATH`.

Советы:

- В production `WEBHOOK_SECRET` и provider webhook secrets обязательны.
- Не допускайте `APIX_WEB_DEV_AUTH=true` в production.
- Не держите provider keys в коде или frontend.
- Для каждого нового provider сразу задайте callback URL и секрет.
- `.env.example` в референсе содержит legacy YooKassa vars и неактуальный `REFERRAL_L2_CREDITS`. В новом проекте держите example строго синхронным с `Settings`.

## 6. База данных и доменная модель

Основные enum:

- `GenerationType`: `image`, `video`, `music`.
- `GenerationStatus`: `pending`, `processing`, `done`, `failed`.
- `ImageSessionStatus`: `active`, `archived`.
- `ImageGenerationAction`: `initial`, `remix`, `repeat`, `reference_update`, `animate`.
- `TransactionStatus`: `pending`, `paid`, `failed`, `refunded`.
- `PaymentProvider`: `cryptobot`, `tbank`, `telegram_stars`, `lava` плюс legacy `yookassa`.
- `PromoRewardType`: `credits`, `discount_percent`, `discount_amount`, `free_generation`.
- `WithdrawalStatus`: `pending`, `approved`, `rejected`.
- `PromptCategory`: `art`, `business`, `marketing`, `photo`, `other`.
- `PromptStatus`: `pending`, `approved`, `rejected`, `deactivated`.

Ключевые таблицы:

- `User`: Telegram ID, contact auth fields, photo, credits, subscription flags, 3-level referral chain, referral code, referral balance, language, ban flag.
- `WebAuthCode`: hashed auth codes for email/Telegram contact login.
- `Generation`: task id, model, type, prompt, result URL(s), source feed generation, likes/shares, credits spent, status/error.
- `ImageSession`: активная серия изображений с моделью, режимом, aspect ratio, quality, refs, last prompt/result.
- `Transaction`: payment provider, amount rub, credits, external id, status.
- `PromoCode` and `PromoRedemption`: промокоды, скидки, free credits.
- `CreditLedgerEntry`: аудит всех кредитных изменений.
- `ReferralWithdrawalRequest`: вывод/конвертация реферального баланса.
- `FeedRemixPayout`: выплаты автору исходника за feed remix.
- `PricePlan`: тарифы пополнения.
- `ModelCost`: стоимость моделей и вариантов.
- `UserPrompt` and `PromptLike`: маркетплейс промптов.

Инварианты repository-слоя:

- Нельзя менять `User.credits` напрямую. Используйте `add_credits()` и `spend_credits()`.
- `spend_credits()` должен быть атомарным: списание только при `credits >= amount`.
- Каждое изменение кредитов пишет `CreditLedgerEntry`.
- `create_user()` и `create_contact_user()` начисляют welcome bonus через ledger.
- `confirm_transaction()` и `confirm_transaction_and_add_credits()` должны переводить только `pending -> paid`.
- Payment webhook и ручная проверка оплаты не должны удваивать начисление.
- `finish_generation()` должен работать только для `pending/processing`, зеркалить URLs, публиковать realtime event и начислять feed remix royalty.
- `fail_generation()` должен работать только для `pending/processing`; возврат кредитов делает вызывающий код.
- Публикация в feed/library разрешена только владельцу, только для `done`, только если есть result URL.
- Ремиксы чужой ленты не должны раскрывать промпт и не должны повторно публиковаться как свои оригинальные промпты.

## 7. Seed-данные и экономика

В `db/seed.py` создаются:

- тарифы `credits_100`, `credits_300`, `credits_1000`;
- стоимости image/video/music/Midjourney моделей;
- вариантные стоимости по quality, duration, resolution;
- отключение legacy aliases.

Для аналога seed должен быть идемпотентным:

- `upsert` по ключам тарифов и моделей;
- не создавать дубликаты при каждом старте;
- хранить человекочитаемое имя модели;
- отдельно хранить технический model key, который идет в provider payload;
- иметь `is_active`, чтобы админ мог отключать тарифы/модели без удаления.

Модель стоимости:

- Images: обычно фиксированная стоимость за запрос, иногда вариант по quality `basic/2K/4K`.
- Videos: либо flat cost, либо `credits_per_second * duration`.
- Gemini Omni/Veo/Kling-like models: стоимость зависит от duration/resolution/video input.
- Music: flat cost за трек/задачу.
- Midjourney: отдельные costs для imagine/action/blend/describe/video.

## 8. Telegram bot UX

### 8.1 Main menu

Главное меню должно показывать:

- кнопку открытия Mini App;
- баланс;
- продолжение активной image-сессии или новую серию;
- создание фото, видео, песни;
- Midjourney для разрешенных пользователей или админов;
- ассистента;
- ленту и библиотеку промптов;
- историю;
- рефералов/помощь;
- пополнение;
- настройки языка;
- админку для админов.

В референсе тексты локализованы через `bot/i18n.py`, основной язык русский, есть английский. Кредиты в UI называются `💋`/kisses. Для аналога лучше выбрать один продуктовый термин и использовать его везде.

### 8.2 Start, auth, referrals

`AuthMiddleware`:

- создает пользователя при первом контакте;
- разбирает `/start` payload;
- связывает referrer chain L1/L2/L3;
- выдает welcome bonus;
- начисляет L1 signup bonus;
- проверяет ban flag;
- поддерживает maintenance mode через flag file;
- injects `db_user`.

Deep links:

- обычный referral code;
- combined payload вида `ref_CODE__feed_ID`;
- combined payload вида `ref_CODE__prompt_ID`.

LLM должна реализовать deep link builder/parser отдельно, покрыть тестами и не размазывать parsing по handlers.

### 8.3 Image generation

Основной UX:

- быстрый сценарий "картинка с нуля";
- сценарий "по фото/референсу";
- сценарий "улучшить/изменить фото";
- расширенный выбор модели;
- фото -> промпт;
- активная серия, где пользователь продолжает работу с теми же настройками.

Важные возможности:

- до 6 одновременных генераций на пользователя;
- модельные capability-карты в `bot/keyboards/models.py`;
- разные `modes`: `text`, `image`;
- разные aspect ratios;
- quality options и автоматическая нормализация несовместимых вариантов;
- `count` результатов;
- `max_refs` по модели;
- несколько reference images;
- style edit presets: одежда, прическа, цвет волос, ногти;
- repeat последнего prompt;
- remix последнего результата;
- animate результата в video flow;
- publish to feed;
- publish to prompt library;
- hide prompt actions для feed derivatives.

Паттерн запуска image generation:

```text
validate model and capabilities
normalize aspect_ratio/quality/count/refs
resolve model cost
reconcile stale active generations
check concurrent generation limit
spend credits atomically
create ImageSession or update active session
create Generation(status=pending)
call image_service.generate_image(... callback_url=...)
if provider returns direct result:
  finish_generation()
else:
  update task_id
return/send pending status
```

Provider layer:

- `ImageModel` enum - только поддерживаемые ключи.
- `api/kie_model_specs.py` - source of truth для provider payload.
- `api/image_service.py` - подготавливает refs, усиливает prompt для сохранения identity, отправляет в KIE, fallback в CometAPI.
- local uploaded refs для некоторых моделей надо сначала загрузить/provider-friendly URL.

### 8.4 Video generation

Видео UX:

- группы моделей: быстрые, image-to-video, motion control, Gemini Omni, Veo/Midjourney;
- режимы `text`, `image`, `video`, `motion`;
- duration, aspect ratio, resolution;
- refs/images;
- reference video для Gemini Omni;
- audio IDs и character IDs для Gemini Omni;
- seed;
- Grok mode;
- repeat previous video from stored params.

Стоимость:

- per-second модели: `rate * duration`;
- flat модели: `credits`;
- для некоторых моделей duration/resolution дают отдельный `ModelCost`.

Паттерн запуска video generation такой же, как image, но обязательно:

- проверять, что image-required модели получили ref;
- ограничивать video upload duration/size;
- нормализовать aspect ratio референса через `ensure_video_reference_aspect_url()`;
- не fallback-ить provider validation errors, если ошибка означает неверный payload;
- хранить task_id и ждать webhook/poll.

### 8.5 Music generation

Music flow:

- выбор lyrics/instrumental;
- выбор active Suno/KIE model, fallback `suno/v5.5 -> suno/v5.0 -> suno/v4.5`;
- flat cost;
- create `Generation(gen_type=music)`;
- `api/music_service.create_music_task()`;
- callback `/webhook/kie/music`;
- промежуточные статусы вроде `TEXT_SUCCESS` не завершают задачу;
- финальный success извлекает mp3/audio URLs;
- финальный fail возвращает кредиты.

Текущий риск: mapping music task -> Telegram user частично in-memory. В новом проекте лучше опираться на `Generation.task_id` и persistent user lookup, чтобы restart не терял уведомления.

### 8.6 Midjourney

В референсе Midjourney доступен только администраторам в Telegram UI, но в Mini App есть публичный catalog.

Функции:

- imagine с bot type Midjourney/Niji;
- speed Fast/Relax/Turbo;
- optional reference image;
- action buttons U/V/reroll/zoom/pan;
- modal action handling;
- blend 2-6 фото;
- describe фото -> промпт;
- image -> video с motion low/high.

Provider:

- `api/midjourney_service.py`;
- CometAPI `/mj/submit/*`;
- notifyHook строится из `WEBHOOK_URL + MIDJOURNEY_WEBHOOK_PATH + secret`;
- webhook парсит `MJTaskResult`, idempotently finishes/fails.

### 8.7 Feed

Feed - публичная лента готовых image generations:

- только `done`;
- только с результатом;
- prompt скрыт от не-авторов или для производных;
- можно лайкать;
- можно шарить deep link;
- владелец может удалить публикацию;
- remix чужой работы использует hidden source prompt;
- автор исходника получает royalty от remix.

Для аналога обязательно разделите:

- `source_feed_gen_id` - откуда взят скрытый промпт;
- `parent_generation_id` - техническая родительская генерация/цепочка;
- `is_public_feed` - опубликовано ли в ленту;
- `is_prompt_library` - опубликовано ли как prompt/library item.

### 8.8 Prompt marketplace

Prompt library:

- browse catalog;
- top today, trending/popular, best, collections by tags;
- like;
- share deep link;
- use prompt;
- remix with references;
- submit own prompt with preview image/text;
- moderation pending/approved/rejected/deactivated;
- author rewards when prompt is used.

Референсная экономика prompts:

- author получает `max(1, floor(credits_spent * 0.30))`;
- author referrer получает примерно 7%;
- author referrer L2 получает примерно 3%;
- пользователь не должен получать reward за использование своего prompt.

Правило продукта: prompt marketplace - это отдельная UGC-система. Не смешивайте ее с feed: feed хранит результаты, prompt marketplace хранит reusable текстовые рецепты.

### 8.9 Balance, payments, referrals

Balance screen:

- текущий баланс;
- стоимость моделей/диапазоны;
- subscription state, если включена;
- пополнение;
- промокод;
- referrals.

Referral screen:

- referral link `https://t.me/<bot>?start=<code>`;
- counts L1/L2/L3;
- signup bonus;
- payment commissions 30%/7%/3%;
- feed remix rewards;
- withdrawal min;
- exchange referral balance -> credits;
- список последних referrals/withdrawals.

### 8.10 Assistant

Assistant:

- обычный chat helper;
- history в FSM или frontend state;
- KIE Responses API primary, CometAPI fallback;
- photo/prompt moderation helpers;
- admin-only planner for operational actions.

Не давайте ассистенту выполнять опасные действия без plan validation и confirmation.

### 8.11 Admin

Telegram admin panel:

- статистика;
- AI-админ;
- инструкция AI-админа;
- referrals overview;
- withdrawal requests approve/reject;
- price plans CRUD/toggle;
- promocodes;
- model costs edit;
- add/remove user credits;
- ban/unban;
- prompt moderation;
- broadcast now/scheduled.

Mini App admin dashboard:

- overview metrics;
- charts users/revenue/generations;
- top models/providers;
- users search/detail;
- credits adjustment;
- ban toggle;
- withdrawal review.

Admin AI pattern:

- LLM returns structured plan;
- `validate_plan()` checks allowed action/params;
- dangerous actions require confirmation;
- execution uses normal repository functions;
- logs are redacted before sending to LLM.

## 9. Mini App API

Telegram Mini App API lives under `/api/v1` in `api/miniapp_routes.py`.

Auth:

- `get_miniapp_user` verifies Telegram initData or web auth token.
- `/auth/config`
- `/auth/telegram-login`

Core endpoints:

- `GET /me`, `GET /me/feed`, `POST /me/photo`
- `POST /assistant`
- `POST /settings/language`
- `GET /referrals`
- `POST /referrals/withdrawals`
- `POST /referrals/exchange`
- `POST /photo-prompt`
- `POST /prompt/improve`
- `GET /help`
- `GET /models/image`
- `GET /models/video`
- `GET /models/music`
- `GET /public/midjourney`
- `GET /public/models`
- `POST /generate/image`
- `POST /generate/video`
- `POST /generate/music`
- `GET /generations/{id}`
- `GET /history`
- `GET /feed`
- `POST /generations/{id}/share`
- `POST /feed/{id}/remove`
- `POST /feed/{id}/like`
- `POST /feed/{id}/remix`
- `GET /feed/{id}/link`
- `POST /generations/{id}/share-library`
- `POST /generations/{id}/remove-library`
- `GET /prompts`
- `GET /prompts/my`
- `GET /prompts/{id}`
- `POST /prompts/{id}/like`
- `GET /prompts/{id}/link`
- `POST /prompts/{id}/use`
- `POST /prompts/{id}/deactivate`
- `POST /prompts`
- admin endpoints under `/admin/*`
- payments: `/payment-methods`, `/payment-options`, `/plans`, `/topup/tbank`, `/topup/stars`, `/topup/crypto`, `/topup/lava`
- `POST /generations/{id}/publish`

Response contract:

- Generation response includes `id`, `model`, `gen_type`, `prompt`, `prompt_hidden`, `prompt_actions_allowed`, `status`, `result_url`, `preview_url`, `result_urls`, `preview_urls`, `credits_spent`, flags.
- Model response includes modes, aspect ratios, quality prices, durations, resolutions, per-second rate, refs limits, Omni IDs, seed support, price tables.

## 10. Standalone web API

Standalone site API lives under `/api/web`.

Auth options:

- Telegram Login widget;
- password login/register;
- contact code request/verify by email or Telegram username;
- logout;
- cookie `WEB_AUTH_COOKIE_NAME` or header `X-Web-Auth-Token`;
- dev header `X-Dev-Tg-Id` only when `APIX_WEB_DEV_AUTH=true` and not production.

Core endpoint groups:

- `/auth/*`
- `/me`, `/me/profile`, `/me/password`
- `/models`, `/price-plans`
- `/models/image`, `/models/video`, `/models/music`
- `/generate/image`, `/generate/video`, `/generate/music`
- `/generations/active`, `/generations/{id}`, download/share/publish/library
- `/uploads/reference`
- `/photo-prompt`, `/prompt/improve`
- `/billing/*`
- `/feed`, `/feed/top`, like/share/remix/remove/link
- `/prompts` plus admin prompt moderation
- `/image-sessions/*`
- `/history`
- `/referrals/*`
- `/assistant`, `/help`, `/settings/language`
- `/ws/generations`

Important: `/api/web` and `/api/v1` должны использовать одинаковую domain logic. Различия должны быть только в auth, schemas и frontend-friendly formatting.

## 11. Frontend surfaces

### 11.1 Telegram Mini App

`webapp/src/main.jsx` - React client with screens:

- Home/Profile strip;
- Studio for image/video generation;
- Music;
- Feed;
- History;
- Midjourney module;
- Capabilities;
- Assistant;
- Referrals;
- Profile/settings/theme/language/avatar;
- Prompts marketplace and photo->prompt tool;
- Admin dashboard.

Mini App использует:

- Telegram WebApp initData;
- haptic feedback;
- modal topup;
- realtime WebSocket for generation status;
- same model catalogs from backend;
- local state for references and selected model params.

Для аналога не хардкодьте capabilities на frontend. Frontend должен получать модельные возможности с backend, а backend должен быть source of truth.

### 11.2 Public standalone site

`landing/` is static, served by FastAPI root mount:

- `index.html`: product entry and scenarios.
- `studio.html`: authenticated creator for image/video/music.
- `models.html`: model catalog.
- `model.html?model=<model_key>`: model education page.
- `gallery.html`: public feed.
- `account.html`: queue, library/history, balance, referrals, assistant.
- `features.html`, `guide.html`, `contact.html`: support pages.

Actual JS/CSS layer:

- `landing/js/prototype-premium.js`
- `landing/css/prototype-premium.css`

The site talks to `/api/web/*`, not `/api/v1/*`.

## 12. Provider integrations

### 12.1 KIE.AI

KIE is the primary provider for many image/video/music tasks.

Patterns:

- central client in `api/kieai_client.py`;
- central model spec mapping in `api/kie_model_specs.py`;
- retry 5xx/request errors;
- callback URL with secret;
- endpoints include generic jobs, Veo, Omni audio/character, music.

`api/kie_model_specs.py` must be the source of truth for:

- provider model name;
- media type image/video;
- reference type: none/single/list/first-last/motion/Gemini Omni;
- field names;
- param mappers for aspect ratio, duration, resolution, mode, seed, IDs.

### 12.2 CometAPI

CometAPI is used for:

- fallback image/video generation;
- assistant chat fallback;
- Midjourney wrapper;
- direct inline/base64 result persistence.

Comet fallback task IDs use prefix `comet:<kind>:<raw_id>`. Webhooks add query params `provider=comet&comet_kind=<kind>`.

### 12.3 Public file mirroring

`api/public_files.py` solves several real production problems:

- provider CDN URLs can expire;
- Telegram/KIE can reject `.bin` files;
- previews should be lightweight;
- video refs may have unsupported aspect ratio.

Required functions for an analogue:

- save bytes to content-addressed filename;
- detect image/video/audio extension from MIME and magic bytes;
- create public URL under `/static/upload`;
- mirror external provider URL into local static storage;
- mirror Telegram file by `file_id`;
- generate WebP preview for local images;
- create fitted video reference image with blurred background if aspect ratio is too extreme.

### 12.4 Webhook handling

Provider webhooks must:

- verify secret/signature;
- tolerate duplicate callbacks;
- parse provider-specific status and URLs robustly;
- map provider task id to internal `Generation`;
- ignore intermediate music statuses;
- refund on final failure;
- mirror result URLs;
- call `finish_generation()`;
- notify Telegram user only for bot-origin tasks;
- publish realtime event for web/mini app.

Do not do long polling inside request handlers unless it is explicitly bounded and cheap. Prefer provider callbacks and background reconciliation for stale tasks.

## 13. Payments

Supported providers in reference:

- T-Bank acquiring;
- CryptoBot USDT invoices;
- Lava.top offer-based invoices;
- Telegram Stars.

Payment flow:

```text
user selects active PricePlan
create provider invoice
create Transaction(status=pending, external_id=provider_id)
show pay URL/invoice link
provider webhook or manual check confirms
if pending -> paid:
  add credits
  write ledger
  accrue referral commissions
  consume active discount promo if applicable
if refund/reversal:
  mark refunded
  subtract credits if business rules require
  reverse referral commission if implemented
```

Security:

- CryptoBot: verify HMAC signature header.
- T-Bank: verify notification token.
- Lava: verify configured webhook path/contract/status.
- Stars: use Telegram successful payment handler and transaction payload.

Promo behavior:

- `credits/free_generation` rewards can be applied immediately.
- `discount_percent/discount_amount` reserve a redemption for the next payment.
- When payment transaction is created, attach/consume reserved discount.

Referral commissions:

- L1/L2/L3 percentages from settings.
- Skip if `REFERRAL_FREEZE=true`.
- Store money in `User.referral_balance`, not credits.
- Withdrawal requests reserve available balance.
- Exchange creates withdrawal-like record with `AUTO_CREDITS` and credits user.

## 14. Realtime

Realtime events are used by web/mini app to avoid polling-only UX.

Pattern:

- WebSocket endpoint accepts auth token as first message or header.
- Connection manager maps `user_id -> set[websocket]`.
- `repository.finish_generation()` calls `publish_generation_event(gen)`.
- Payload includes id, status, result URLs, previews, prompt visibility flags, model, type, credits.
- Backend still exposes polling `GET /generations/{id}` as fallback.

## 15. Security checklist

Implement from the start:

- Telegram webhook secret token verification.
- Duplicate Telegram update dedupe by update id in Redis or memory fallback.
- Bot auth middleware with ban check.
- Throttling middleware per user.
- Maintenance mode flag.
- Provider webhook secrets.
- Payment signature verification.
- Telegram WebApp initData verification.
- Web auth token HMAC.
- Password hashing and login rate limiting.
- Email/contact auth codes hashed, one-time, TTL, attempt limits.
- CORS allowlist.
- Upload limits by size and MIME/magic bytes.
- SSRF-safe reference URL validation for frontend-uploaded refs.
- Admin guards on every admin endpoint and callback.
- Redaction before sending logs to any LLM.

## 16. Recommended build order for an LLM

When asked to implement an analogue from scratch, follow this order.

### Phase 1: Skeleton

1. Create FastAPI app with lifespan.
2. Configure settings via pydantic-settings.
3. Add Postgres async engine/session.
4. Add Redis connection and graceful fallback where acceptable.
5. Add aiogram Bot, Dispatcher, RedisStorage.
6. Add webhook route and health route.
7. Add Alembic.

### Phase 2: Domain model

1. Add `User`, `Generation`, `Transaction`, `PricePlan`, `ModelCost`, `CreditLedgerEntry`.
2. Add enums.
3. Implement repository credit functions with ledger.
4. Implement generation lifecycle functions.
5. Implement seed for tariffs/model costs.
6. Add tests for credits and idempotency.

### Phase 3: Telegram MVP

1. `/start` and main menu.
2. DB session middleware.
3. Auth/auto-register middleware.
4. Throttling middleware.
5. Balance screen.
6. One image generation flow with one provider and webhook.
7. History.

### Phase 4: Generation platform

1. Model capability map.
2. Image sessions and refs.
3. Video generation.
4. Music generation.
5. Provider callback unification.
6. Public file mirroring.
7. Realtime events.

### Phase 5: Economy

1. Price plans.
2. Payments.
3. Payment webhooks.
4. Promo codes.
5. Referrals.
6. Withdrawal/exchange.

### Phase 6: Social and UGC

1. Public feed.
2. Feed remix with prompt hiding.
3. Prompt marketplace.
4. Prompt moderation.
5. Author rewards.

### Phase 7: Web surfaces

1. Mini App API.
2. React Mini App.
3. Standalone web auth.
4. `/api/web` contract.
5. Static site pages.
6. WebSocket status.

### Phase 8: Admin and operations

1. Admin panel.
2. Model/price editing.
3. User management.
4. Withdrawals.
5. Broadcasts.
6. AI-admin with structured plans and confirmations.
7. Monitoring/reconciliation jobs.

## 17. Pseudocode: generation lifecycle

```python
async def start_generation(user, request):
    model = validate_model(request.model)
    params = normalize_params(model, request)
    cost = await resolve_cost(model, params)

    await reconcile_stale_generations(user.id)
    if await count_active_generations(user.id) >= MAX_CONCURRENT:
        raise TooManyRequests

    if not await spend_credits(user.id, cost):
        raise InsufficientCredits

    generation = await create_generation(
        user_id=user.id,
        model=model.key,
        gen_type=model.type,
        prompt=request.prompt,
        credits_spent=cost,
    )

    try:
        provider_result = await provider.create_task(
            params,
            callback_url=provider_callback_url(),
        )
    except Exception as exc:
        if await fail_generation(generation.id, str(exc)):
            await add_credits(user.id, cost, note="generation_refund")
        raise

    if provider_result.is_direct:
        await finish_generation(generation.id, provider_result.urls)
    else:
        await update_generation_task(generation.id, provider_result.task_id)

    return generation
```

## 18. Pseudocode: provider webhook

```python
async def provider_webhook(payload, secret):
    verify_secret(secret)
    task_id = extract_task_id(payload)
    status = extract_status(payload)

    generation = await get_generation_by_task_id(task_id)
    if not generation:
        return ok()

    if generation.status in {"done", "failed"}:
        return ok()

    if status in INTERMEDIATE_STATUSES:
        await mark_processing(generation.id)
        return ok()

    if status in FAILED_STATUSES:
        if await fail_generation(generation.id, extract_error(payload)):
            await add_credits(generation.user_id, generation.credits_spent)
        await notify_user_failed(generation)
        return ok()

    urls = extract_result_urls(payload)
    mirrored_urls = [await mirror_url(url) for url in urls]
    generation = await finish_generation(generation.id, mirrored_urls)
    await notify_user_success(generation)
    return ok()
```

## 19. Pseudocode: payment confirmation

```python
async def confirm_payment(provider_payload):
    verify_provider_signature(provider_payload)
    external_id = extract_external_id(provider_payload)

    transaction = await get_transaction_by_external_id(external_id)
    if not transaction:
        return ok()

    if transaction.status == "paid":
        return ok()

    if provider_payload.status == "paid":
        paid = await confirm_transaction(transaction.external_id)
        if paid:
            await add_credits(transaction.user_id, transaction.credits)
            await accrue_referral_commissions(transaction)
        return ok()

    if provider_payload.status in {"failed", "cancelled"}:
        await set_transaction_status(transaction.id, "failed")
        return ok()

    if provider_payload.status in {"refunded", "reversed"}:
        await set_transaction_status(transaction.id, "refunded")
        await reverse_credits_and_commissions_if_required(transaction)
        return ok()
```

## 20. Testing strategy

Минимальный test suite для аналога:

- import smoke: app imports without real provider calls;
- config parsing;
- repository credits and ledger;
- transaction idempotency;
- webhook signature/security;
- KIE model payload specs;
- image/video/music service payload building;
- provider fallback task id parsing;
- public file extension/mirroring/preview helpers;
- FSM transitions for image/video/music;
- main menu contract;
- callback coverage;
- feed publish/remix rules;
- prompt marketplace likes/rewards/moderation;
- payment webhooks;
- Telegram Stars successful payment;
- mini app auth;
- web auth;
- `/api/v1` and `/api/web` schema contracts;
- realtime event payload.

Manual QA before release:

- fresh user `/start`;
- referral deep link;
- welcome/referral bonus ledger;
- image text generation success;
- image with ref success;
- failed provider refund;
- video generation with per-second cost;
- music success with audio URLs;
- payment success and duplicate webhook;
- payment failure/refund;
- feed publish/remix and hidden prompt;
- prompt submit/approve/use/reward;
- web login and generation status via WebSocket;
- admin price/model edit;
- ban user;
- withdrawal approve/reject;
- broadcast dry run.

In this repository, run before final delivery:

```bash
tools/codex_static_checks.sh
```

For frontend/static JS changes also run:

```bash
node --check landing/js/prototype-premium.js
npm --prefix webapp run build
```

## 21. Deployment checklist

1. Create `.env` from a synchronized example.
2. Set production `ENV=production`.
3. Configure PostgreSQL and Redis.
4. Run Alembic migrations.
5. Run seed.
6. Build Mini App: `npm --prefix webapp run build`.
7. Serve FastAPI behind nginx/HTTPS.
8. Set Telegram webhook with secret.
9. Configure provider callback URLs:
   - Telegram: `/webhook/telegram`
   - KIE: `/webhook/kie?secret=...`
   - KIE music: `/webhook/kie/music?secret=...`
   - Midjourney/Comet: `/webhook/comet/midjourney?secret=...`
   - T-Bank/CryptoBot/Lava payment webhooks
10. Mount `/static/upload` and back it up.
11. Verify CORS origins.
12. Verify public `WEBHOOK_URL` and `WEB_PUBLIC_URL`.
13. Test each payment method in sandbox/low amount.
14. Test duplicate webhooks.
15. Enable monitoring for failed generations and pending transactions.

## 22. Known risks and technical debt in the reference

Use these as improvement notes when designing a new project:

- `README.md` is partially stale: aiogram version and migration count differ from current files.
- `Dockerfile` Python version differs from local scripts/pyproject target.
- `run_polling.py` includes only a subset of routers and can mislead local development.
- `.env.example` contains legacy YooKassa vars and a referral var not present in `Settings`.
- `PaymentProvider.yookassa` remains as legacy enum value, but current payment implementation is T-Bank/CryptoBot/Lava/Stars.
- Music task mappings are partly in-memory; a restart may lose direct bot notification context.
- Static upload fallback can hide missing files by returning transparent 1x1 for missing paths.
- Some backup files are present in `landing/`, `webapp/src/`, and `api/web/`; keep active source files clearly documented.
- There is a dirty local change in `db/seed.py` at audit time; do not overwrite it blindly.

## 23. Advice to the future LLM

When implementing a similar bot:

- Treat credits, transactions and generation statuses as financial state, not UI state.
- Put every provider-specific payload rule in one spec layer.
- Make callbacks idempotent before adding more models.
- Keep Telegram handlers thin: validation and UX in handlers, business invariants in repository/services.
- Do not duplicate pricing logic between bot, mini app and web.
- Make model capabilities backend-driven.
- Mirror provider results locally if users need history, downloads, refs and previews.
- Hide source prompts for feed remixes by default.
- Do not expose admin actions to a free-form LLM without schema validation and confirmation.
- Prefer explicit enums and typed request schemas over ad hoc strings.
- Add tests for every payment/webhook branch before adding the next provider.
- Keep public site, mini app and bot visually different if needed, but behaviorally consistent.

The product can be rebuilt in smaller increments, but the invariants above should exist from the first production version. Most bugs in this class of bot are not model bugs; they are duplicate webhooks, double credits, lost task IDs, stale provider URLs, hidden prompts leaking into public UI, and frontend/backend capability drift.
