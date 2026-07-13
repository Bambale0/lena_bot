# Mini App Audit And Agent Instructions

Документ только про Telegram Mini App и его backend. Не описывать отдельный web-кабинет как целевой продукт.

## Цель

Сделать Mini App полноценной интерактивной оболочкой уже существующего Telegram-бота: генерация изображений, видео и музыки, история, фид, ремиксы, промпты, пополнение, рефералка и профиль должны работать из Mini App, но не ломать привычные bot flows.

Главный принцип: бот остается точкой входа, уведомлений и совместимости, Mini App становится удобным интерфейсом для сложных действий.

## Текущий Контур

Frontend:

- `webapp/src/main.jsx` - вся React Mini App в одном файле, примерно 3.6k строк.
- `webapp/src/style.css` - вся визуальная система и стили экранов в одном файле, примерно 1.2k строк.
- `webapp/package.json` - минимальный Vite/React стек без роутинга, state manager, test runner и UI-kit.

Backend:

- `api/miniapp_routes.py` - основной REST API `/api/v1/*`, примерно 3.3k строк.
- `api/miniapp_auth.py` - Telegram `initData`, web auth token, получение пользователя.
- `api/realtime.py` - websocket `/api/v1/ws/generations` для live-обновлений генераций.
- `api/webapp_routes.py` и `api/webapp_auth.py` - legacy bridge, оставлять для обратной совместимости.

Связь с ботом:

- Пользователь Mini App ищется по `tg_id`, поэтому Telegram-бот остается первичным источником пользователя.
- Deep links строятся через существующие bot helpers.
- Генерации, кредиты, фид, промпты и рефералка используют общие таблицы и репозитории.
- Webhook KIE завершает задачи и публикует realtime-события.

## Что Уже Хорошо

- Есть единый `/api/v1` backend для Mini App с рабочими сценариями: модели, генерация, история, фид, промпты, рефералка, платежи, админка.
- Авторизация Mini App проверяет Telegram `initData` по HMAC и сроку жизни.
- Есть fallback доставки статусов: websocket плюс polling на клиенте.
- Кредиты списываются атомарно через SQL update с условием `User.credits >= amount`.
- Скрытие промптов для feed remix уже заложено в `_generation_prompt_hidden`, `_feed_card_out` и realtime payload.
- Есть targeted tests для miniapp auth/routes/realtime.
- Vite build проходит, текущий bundle около 290 KB JS / 34 KB CSS до gzip.

## Главные Проблемы

1. Слишком крупные файлы.

`webapp/src/main.jsx` и `api/miniapp_routes.py` содержат почти все сразу: API client, state, экраны, карточки, бизнес-валидацию, платежи, админку, генерацию и фид. Это ускоряло MVP, но дальше любое изменение будет дорогим и рискованным.

2. Backend route handlers стали use-case слоем.

`api/miniapp_routes.py` не только принимает HTTP-запросы, но и решает, сколько списывать, какие модели разрешены, как запускать провайдера, как создавать generation, как делать refund, как скрывать промпты. Для гармоничной интеграции с ботом эту логику нужно вынести в shared services, чтобы бот и Mini App вызывали один и тот же сценарий.

3. Frontend state смешан с экранами.

`App()` держит глобальное состояние генерации, polling, websocket, screen navigation, theme, topup, presets, feed/history scopes. Новая функциональность будет цепляться к одному центральному компоненту и раздувать его.

4. Нет typed API contract на frontend.

Клиент строит payload вручную в `generate()` и `generateMusic()`. При изменении backend-схемы легко получить тихую несовместимость.

5. Валидация моделей и возможностей размазана.

Capabilities берутся из bot keyboards, локальных словарей Mini App и service enums. Это лучше привести к единому каталогу возможностей, чтобы бот и Mini App показывали одно и то же.

6. Realtime хорошо начат, но lifecycle еще не единый.

Клиент поддерживает websocket и polling, backend публикует события, но генерационный lifecycle лучше описать как один контракт: `pending -> processing -> done|failed`, refund, result URLs, prompt visibility, feed/library flags.

7. Тесты покрывают backend лучше, чем frontend.

Mini App backend покрыт targeted pytest. У frontend нет unit/e2e smoke tests, поэтому визуальные и сценарные регрессии будут ловиться вручную.

## Целевая Архитектура

### Frontend Structure

Разделить `webapp/src/main.jsx` на такие зоны:

```text
webapp/src/
  app/
    App.jsx
    navigation.js
    telegram.js
    theme.js
  api/
    client.js
    generations.js
    models.js
    feed.js
    prompts.js
    billing.js
    referrals.js
  hooks/
    useApi.js
    useRealtimeGenerations.js
    useGenerationPolling.js
    useTelegramTheme.js
  components/
    Avatar.jsx
    NoticeBar.jsx
    MediaThumb.jsx
    GenerationResultCard.jsx
    TopupModal.jsx
  screens/
    Home.jsx
    Studio.jsx
    Midjourney.jsx
    Music.jsx
    Feed.jsx
    History.jsx
    Prompts.jsx
    Profile.jsx
    Referrals.jsx
    Help.jsx
    AdminDashboard.jsx
  styles/
    base.css
    theme.css
    layout.css
    components.css
    screens.css
```

Порядок выноса:

1. Сначала вынести `api/client.js`, `app/telegram.js`, `hooks/useApi.js`.
2. Потом вынести чистые shared-компоненты без изменения JSX.
3. Потом по одному экрану: `Home`, `Studio`, `Feed`, `History`, `Profile`.
4. Только после этого менять UX или добавлять крупные функции.

### Backend Structure

Разделить `api/miniapp_routes.py` на тонкие роуты и shared use-cases:

```text
api/miniapp/
  router.py
  auth.py
  schemas.py
  models.py
  generations.py
  feed.py
  prompts.py
  billing.py
  referrals.py
  admin.py
  media.py

services/
  generation_usecases.py
  generation_catalog.py
  feed_usecases.py
  prompt_usecases.py
  billing_usecases.py
  referral_usecases.py
```

Правило: HTTP-роут должен только проверить auth, распарсить request, вызвать use-case и вернуть response. Списание кредитов, provider routing, refund, prompt hiding и публикация событий живут не в route файле.

## Provider Policy

Для Mini App провайдеры должны идти так:

```text
Per-model provider routing in api/image_service.py / api/video_service.py
Image nano-banana-2 and nano-banana-pro: CometAPI primary
Other KIE image/video models: KIE.AI primary
CometAPI fallback only when supported KIE create/start fails
```

Это правило должно быть зафиксировано в одном месте и использоваться всеми поверхностями. Сейчас image routing живёт в `api/image_service.py`, поэтому Mini App не должен дублировать provider-логику на фронте.

Нельзя делать отдельную provider-логику в Mini App и отдельную в боте. Иначе пользователь увидит разные цены, статусы и ошибки для одной модели.

## Как Вписывать В Бот

1. Не менять существующие bot handlers ради Mini App UI.

Если нужно добавить новый сценарий, сначала выделить общий service/use-case, затем подключить его в Mini App. Бот можно подключать к нему отдельной задачей, если это явно требуется.

2. Общие сущности должны оставаться общими.

Использовать текущие таблицы `users`, `generations`, `image_sessions`, `transactions`, `credit_ledger`, `user_prompts`, referral tables. Не создавать miniapp-only user или miniapp-only generation.

3. Бот и Mini App должны сходиться в lifecycle.

Одна генерация должна иметь одинаковые:

- model key;
- credits_spent;
- task_id;
- status;
- result_url/result_urls;
- prompt visibility;
- feed/library flags.

4. Deep links вести обратно в бот, но Mini App открывать для сложной работы.

Фид, промпты и рефералка могут давать Telegram start links. Сложные действия вроде remix, batch refs, prompt editing, Midjourney blend удобнее открывать внутри Mini App.

5. Уведомления оставить за ботом, интерактив за Mini App.

После завершения генерации backend должен обновить запись, отправить realtime event и, если текущий bot flow это делает, отправить пользователю Telegram-сообщение. Mini App не должен становиться единственным способом узнать результат.

## Функционал, Который Делать В Mini App

### Studio

- Выбор типа генерации: image/video/music.
- Каталог моделей с возможностями: text, image refs, counts, aspect ratios, quality, duration, resolution.
- Prompt editor с улучшением промпта.
- Upload/reference URLs.
- Предпросмотр цены до запуска.
- Проверка баланса до запроса.
- Pending/result card сразу после запуска.
- Realtime status update.
- Повтор, remix, публикация в фид, сохранение промпта.

### Feed

- Лента public generations.
- Скрывать исходный prompt для чужого feed remix.
- Like/share/remix.
- Remix должен использовать скрытый source prompt на backend, не отправлять его на frontend.
- Для автора показывать свои действия публикации/снятия.

### Prompts

- Каталог approved prompts.
- Мои промпты и статусы модерации.
- Создание промпта с auto moderation.
- Use prompt открывает Studio с preset.
- Save generation prompt добавляет в библиотеку только если generation не является feed derivative.

### History

- История всех генераций пользователя.
- Фильтры по image/video/music/Midjourney.
- Показ pending/processing/done/failed.
- Retry/reuse prompt.
- Download/open result.

### Billing

- Планы пополнения.
- Telegram Stars, TBank, Crypto, Lava только если включены настройками.
- Ошибка 402 из генерации должна открывать topup modal.
- После успешного платежа обновлять `/me`.

### Referrals

- Код и referral link.
- Баланс, уровни, начисления.
- Withdraw/exchange.
- Admin review остается backend/admin сценарием.

### Profile And Settings

- Telegram user info как основа.
- Тема Mini App.
- Язык.
- Баланс, история, мои публикации.
- Кнопки перехода к боту и поддержке.

## Backend Acceptance Criteria

Для каждого нового Mini App сценария:

- Auth идет через `get_miniapp_user`.
- Пользователь не может читать или менять чужие приватные generation/prompt/payment данные.
- Кредиты списываются атомарно до provider call.
- При ошибке provider start generation переводится в `failed`, кредиты возвращаются один раз.
- Если provider возвращает async task, сохраняется `task_id`.
- Если provider возвращает sync result, generation сразу становится `done`.
- Webhook completion идемпотентен.
- Realtime event публикуется после изменения generation.
- Prompt hiding проверен тестом.
- Feed remix не раскрывает source prompt на frontend.

## Frontend Acceptance Criteria

Для каждого нового экрана/фичи:

- Работает внутри Telegram WebApp при наличии `initData`.
- Без `initData` показывает demo/warn state, а не ломается белым экраном.
- Состояния loading/empty/error готовы.
- Ошибка 402 открывает topup.
- Pending generation видна сразу.
- Done/failed приходят через websocket или polling.
- Текст не вылезает за кнопки и карточки на мобильной ширине 360px.
- Нет новых глобальных переменных кроме уже существующих Telegram helpers.

## Testing Checklist

Минимум перед сдачей Mini App изменений:

```bash
npm run build
pytest tests/test_webapp_auth.py tests/test_webapp_routes.py tests/test_realtime.py -q
```

Если менялись provider routing или KIE/Comet fallback:

```bash
pytest tests/test_comet_fallback.py -q
```

Если менялись общие bot/keyboards/deeplinks:

```bash
tools/codex_static_checks.sh
```

Для frontend-рефакторинга желательно добавить smoke e2e:

- Mini App opens.
- `/me` loaded.
- Studio model selected.
- Generate request mocked and pending card shown.
- Realtime done event updates result card.
- 402 opens topup modal.

## Recommended Implementation Plan

### Phase 1: Stabilize Without Feature Changes

- Убрать backup-файлы из `webapp/src` и держать их вне репозитория.
- Вынести API client, Telegram helpers, theme helpers, `useApi`.
- Вынести realtime/polling hooks.
- Не менять поведение экранов.

### Phase 2: Extract Backend Use-Cases

- Вынести schemas из `api/miniapp_routes.py`.
- Вынести generation create/remix use-cases.
- Вынести feed/prompt/billing/referral routes в отдельные модули.
- Сохранить публичные URL `/api/v1/*` без изменения.
- Оставить legacy bridge imports.

### Phase 3: Make Model Catalog Single Source

- Собрать capabilities, цены, режимы, limits в один catalog service.
- Mini App и бот должны читать один catalog.
- Тестами закрепить ключевые модели и reference limits.

### Phase 4: Improve UX

- Сделать Studio как основной первый экран для генерации.
- Упростить Home до dashboard/shortcuts.
- Добавить ясные empty states.
- Улучшить topup modal и balance refresh.
- Добавить e2e smoke на критический путь.

### Phase 5: Add New Functionality

Новые функции добавлять только после фаз 1-3. Тогда они будут ложиться в:

- frontend: `screens/*` + `api/*` + `hooks/*`;
- backend: thin route + shared use-case;
- бот: только deep link/notification, если нужно.

## Что Не Делать

- Не переписывать Mini App на новый стек.
- Не заводить отдельную БД или отдельного пользователя для Mini App.
- Не дублировать provider logic в frontend.
- Не раскрывать скрытые prompts feed remix на клиенте.
- Не менять Telegram bot flows как побочный эффект Mini App задач.
- Не добавлять новый большой экран прямо в `main.jsx` без декомпозиции.
