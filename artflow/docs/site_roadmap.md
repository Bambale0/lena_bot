# APIX Site Roadmap

Дата: 2026-05-16

Документ описывает roadmap standalone-сайта APIX на `apixbotai.com`.
Фокус: публичная витрина и web-студия в `landing/`, web API в `api/web/`,
shared generation API в `/api/v1/*`.

## 1. Цель

Сайт должен стать самостоятельной web-студией генерации, а не только
витриной Telegram-бота. Гость должен быстро понять ценность APIX, увидеть
живые примеры и войти через Telegram. Авторизованный пользователь должен
создать image/video/music, получить realtime-статус, продолжить результат в
следующий шаг, сохранить работу, использовать feed/prompts и пополнить баланс.

Целевая формула продукта:

```text
витрина -> вход через Telegram -> студия -> очередь -> результат -> следующий шаг -> история/feed
```

## 2. Текущая baseline-архитектура

| Поверхность | Путь | Код | Роль |
|---|---|---|---|
| Standalone site | `/` | `landing/index.html`, `landing/js/riot-site.js`, `landing/css/riot-site.css` | Публичный сайт и web-студия |
| Web API | `/api/web/*` | `api/web/` | Auth, feed, prompts, models, plans, profile |
| Generation API | `/api/v1/*` | `api/miniapp_routes.py` | Генерация, история, модели, billing, referrals |
| Realtime | `/api/v1/ws/generations` | `api/realtime.py` | Push статусов генераций |
| Mini App | `/app` | `webapp/` | Telegram Mini App, отдельная поверхность |

Guardrails:

- Сайт развиваем в `landing/` и `api/web/`.
- Telegram bot flows не трогать без отдельной задачи.
- Mini App не смешивать со standalone site.
- WebSocket и `/api/v1/*` можно расширять только совместимо с текущими клиентами.
- Docker не использовать для локального плана внедрения, если нет отдельного запроса.

## 3. Метрики успеха

| Направление | KPI |
|---|---|
| Первый запуск | Пользователь после входа запускает первую генерацию за 60-90 секунд |
| Результаты | Готовый результат появляется без ручного refresh через WebSocket или polling fallback |
| Продолжение работы | У каждой готовой image-карточки есть понятные действия: variant, animate, reuse idea |
| Надежность | Нет 404 по отсутствующим local upload URLs в нормальном пользовательском потоке |
| UX | На мобильном нет горизонтального скролла, наложений текста и неработающих CTA |
| Доверие | Цена, модель, ограничения и статус видны до списания и после запуска |
| SEO/public | Гость видит реальные примеры, сценарии и понятный вход в Telegram |

## 4. Roadmap По Фазам

### Фаза 0. Стабилизация И Инвентаризация

Срок: 1-2 дня.

Цель: закрыть шумные ошибки и получить карту текущих экранов/API перед
дальнейшим развитием.

Задачи:

- Зафиксировать screen map текущего `landing/js/riot-site.js`: home, examples, features, studio, prompts, feed, works, billing, profile.
- Сделать endpoint inventory для `/api/web/*` и используемых `/api/v1/*`.
- Проверить, что WebSocket работает через nginx upgrade и не пишет секреты в URL.
- Проверить, что битые `/static/upload/*` не ломают интерфейс.
- Зафиксировать список legacy-файлов в `landing/`, которые не являются entrypoint.
- Добавить краткий smoke-check сценарий для ручного QA.

Acceptance criteria:

- `GET /api/web/health` отвечает 200.
- `/` открывается как актуальный SPA, а не legacy html.
- `/api/v1/ws/generations` работает через `wss://`.
- Отсутствующий `/static/upload/*.jpg` не возвращает 404 пользователю.
- В docs есть актуальная карта поверхностей.

### Фаза 1. UX-Каркас Web-Студии

Срок: 3-5 дней.

Цель: сделать studio workflow предсказуемым, быстрым и понятным без изменения
backend-контрактов.

Задачи UX:

- Пересобрать студию вокруг одного главного действия на шаг:
  `mode -> idea -> media -> model -> settings -> review -> run`.
- Упростить тексты шагов: меньше технических id, больше сценариев.
- Сохранить user-friendly labels моделей рядом с technical model key.
- Сделать review panel перед запуском: модель, стоимость, refs, параметры, предупреждения.
- Добавить понятные empty states для истории, feed, prompts, queue.
- Добавить loading/skeleton states для моделей, истории, feed и prompt library.

Задачи UI:

- Использовать shadcn-compatible паттерны как reference: tabs, form, badge, empty, drawer, progress, toast.
- Не мигрировать стек ради компонентов: реализовать в текущем vanilla JS.
- Удерживать рабочий стиль студии: dense, сканируемый, без landing-page тяжести внутри app-mode.
- Проверить mobile first: 360px, 390px, 768px, desktop.

Acceptance criteria:

- Пользователь всегда понимает, на каком шаге находится.
- Кнопка запуска disabled, пока обязательные поля не заполнены.
- Цена и модель видны до запуска.
- Ошибка формы появляется рядом с полем, а не только в toast.
- На мобильном нет перекрытия навигации, форм и result preview.

### Фаза 2. Realtime И Lifecycle Генерации

Срок: 2-4 дня.

Цель: результат должен появляться мгновенно, но polling должен оставаться
fallback-слоем.

Задачи backend:

- Сохранить WebSocket auth первым сообщением: `{ "type": "auth", "token": "..." }`.
- Оставить совместимость для legacy клиентов без раскрытия query в nginx -> uvicorn.
- Отдавать snapshot активных задач после auth.
- Отправлять события при `finish_generation` и `fail_generation`.
- Добавить heartbeat/ping-pong policy и чистку stale sockets.

Задачи frontend:

- Показывать realtime-connected/reconnecting state только в технически уместных местах.
- Не создавать бесконечный reconnect storm: ограничить попытки и оставлять polling.
- На `done`: обновлять queue item, history, balance, result preview.
- На `failed`: показывать причину и сохранять карточку в истории.
- На lost WS: тихо продолжать polling активных задач.

Acceptance criteria:

- Готовая генерация появляется без refresh.
- При отключенном WS polling продолжает работать.
- В access logs нет `token=` и `init_data=`.
- Нет повторного flash/toast для одного и того же result.

### Фаза 3. Media Result Experience

Срок: 4-6 дней.

Цель: результат должен быть не концом, а началом следующего действия.

Задачи:

- Унифицировать result card для image/video/music.
- Для image добавить действия:
  - `Variant`;
  - `Animate`;
  - `Use prompt`;
  - `Publish to feed`;
  - `Save to library`, если применимо.
- Для video добавить:
  - preview;
  - download/open;
  - reuse idea;
  - publish/share, если политика продукта разрешает.
- Для music добавить:
  - audio player;
  - track metadata;
  - reuse lyrics/idea;
  - history state.
- Для multi-result image (`result_urls`) добавить gallery view вместо потери 2-4 результатов.
- Добавить detail drawer для результата: prompt, model, cost, created time, source.

Acceptance criteria:

- Все типы результата отображаются без перехода в Mini App.
- `result_urls` не теряются.
- Сломанный media URL не ломает сетку и не показывает сырой alt.
- Следующее действие запускает studio с корректно подставленным prompt/ref.

### Фаза 4. Feed И Prompt Library Как Growth Loop

Срок: 1-2 недели.

Цель: feed и prompt library должны приводить пользователя обратно в студию.

Задачи feed:

- Сделать фильтры: recent, top day, top all, my/public.
- Добавить detail view карточки: результат, автор, модель, prompt visibility policy.
- Сделать `Use as reference` только для image-compatible media.
- Сделать `Remix` с явным объяснением: используется скрытая идея автора.
- Добавить graceful empty state для новых/пустых категорий.

Задачи prompts:

- Разделить catalog, popular, best, my prompts.
- Добавить preview prompt drawer.
- Добавить `Use prompt` с переходом в studio и prefilled idea.
- Добавить submit flow с moderation status.
- Добавить tags/category filter.

Acceptance criteria:

- Из feed/prompt пользователь попадает в studio с заполненным состоянием.
- Нельзя случайно ремикснуть неподдерживаемый media type.
- Лайк/share/use не допускают двойной клик.
- Prompt submit имеет понятный pending/approved/rejected lifecycle.

### Фаза 5. Billing, Profile, Referrals

Срок: 3-6 дней.

Цель: сделать финансовые и аккаунтные действия спокойными, понятными и
доверенными.

Задачи:

- Пересобрать billing screen вокруг баланса, планов и истории пополнений.
- Показать доступные методы оплаты: TBank, Stars, Crypto только если включены.
- Добавить ясный post-payment state: pending, paid, failed, refunded.
- В profile показать Telegram identity, referral code/link, language.
- В referrals показать:
  - уровни;
  - доступно к выводу;
  - pending withdrawals;
  - минимальная сумма;
  - история заявок.
- Сделать копирование referral link с fallback для старых браузеров.

Acceptance criteria:

- Пользователь понимает, сколько кредитов получит до оплаты.
- Повторный клик по оплате не создает хаос в UI.
- После оплаты баланс обновляется без ручного refresh.
- Referral withdrawal validation видна до submit.

### Фаза 6. Public Site, SEO И Контент

Срок: 4-7 дней.

Цель: гость должен захотеть войти, а поисковики и соцсети должны корректно
понимать страницу.

Задачи:

- Переписать hero под конкретный offer: AI media studio in Telegram/web.
- Добавить реальные curated examples из публичной ленты.
- Добавить сценарии:
  - image prompt to result;
  - image to video;
  - prompt library/remix;
  - music generation.
- Добавить FAQ: оплата, Telegram login, приватность, кредиты, сроки генерации.
- Обновить Open Graph/Twitter meta на абсолютные URL.
- Добавить sitemap/robots при подтверждении домена и финальных routes.
- Подготовить RU/EN microcopy parity.

Acceptance criteria:

- Гость без логина понимает продукт за первый экран.
- CTA не ведет в тупик: login/profile работает стабильно.
- Социальный preview показывает корректную картинку.
- Нет устаревших цен/моделей в статическом тексте.

### Фаза 7. Наблюдаемость И Качество

Срок: 3-5 дней, затем постоянно.

Цель: ловить проблемы до пользователя и быстрее понимать production-инциденты.

Задачи:

- Добавить frontend error boundary pattern для vanilla JS: safe render wrapper + user-visible fallback.
- Добавить structured client event logging для ключевых действий без персональных секретов.
- Добавить Playwright smoke:
  - public home;
  - login mock/dev token;
  - studio form fill;
  - queue item rendering;
  - feed card actions;
  - missing media fallback.
- Добавить visual screenshots для desktop/mobile.
- Добавить lightweight accessibility checklist:
  - focus states;
  - labels;
  - aria-live for queue/status;
  - keyboard actions.

Acceptance criteria:

- Build/check pipeline ловит сломанную SPA до деплоя.
- Smoke покрывает главный user journey.
- Логи не содержат auth token/initData.
- UI fallback выглядит осмысленно при API 500/timeout.

### Фаза 8. Архитектурное Укрепление

Срок: 1-3 недели, после стабилизации UX.

Цель: уменьшить сложность `landing/js/riot-site.js`, не ломая production.

Вариант A: остаться на vanilla JS.

- Разделить `riot-site.js` на модули:
  - api client;
  - state;
  - router;
  - render components;
  - studio feature;
  - feed/prompts;
  - realtime/queue.
- Ввести простую typed JSDoc-схему payloads.
- Добавить unit tests для pure helpers.

Вариант B: миграция standalone site на React/Vite.

- Делать только после отдельного решения.
- Не смешивать с `webapp/`; это разные приложения.
- Перенести route/state/API постепенно.
- Сохранить текущие endpoint contracts.

Рекомендация: сначала вариант A. Текущий vanilla stack уже работает; главная боль
сейчас не framework, а размер файла и сложность state/render.

## 5. Приоритетный Backlog

| Priority | Инициатива | Почему важно | Зона |
|---|---|---|---|
| P0 | Stable media URL handling | Убирает 404 и сломанные карточки | `api/public_files.py`, serializers, `main.py` |
| P0 | WebSocket production hardening | Мгновенные результаты без утечки токенов | `api/realtime.py`, nginx, `landing/js/riot-site.js` |
| P0 | Studio review/validation | Предотвращает ошибочные списания и плохие запуски | `landing/js/riot-site.js` |
| P0 | Mobile layout QA | Основная аудитория может быть мобильной | `landing/css/riot-site.css` |
| P1 | Result detail drawer | Делает результаты управляемыми | `landing/` |
| P1 | Multi-result gallery | Не терять несколько изображений от провайдера | `landing/`, serializers |
| P1 | Feed filters and detail | Growth loop из публичной ленты | `api/web/feed.py`, `landing/` |
| P1 | Prompt library drawer | Быстрое применение идей | `api/web/prompts.py`, `landing/` |
| P1 | Billing trust states | Снижает тревожность оплаты | `api/web/`, `/api/v1/topup/*`, `landing/` |
| P2 | SEO/FAQ/sitemap | Рост органики и доверия | `landing/`, deploy |
| P2 | Modularize riot-site.js | Скорость будущей разработки | `landing/js/` |
| P2 | Playwright visual QA | Предотвращает UI regressions | tests/tooling |

## 6. Agent Work Packages

### Product UX Agent

Read:

- `docs/web_studio_frontend.md`
- `landing/README.md`
- `landing/js/riot-site.js`
- `api/web/`

Output:

- Обновленный PRD по web-студии.
- User journey для guest/authenticated.
- Список microcopy проблем RU/EN.

Quality gate:

- Нет предложений, которые требуют менять Telegram bot flows.
- Все flow используют существующие endpoints или явно помечены как backend gap.

### UI Design Agent

Read:

- `landing/css/riot-site.css`
- `landing/js/riot-site.js`
- shadcn registry references: tabs, form, drawer, empty, badge, progress, toast.

Output:

- Screen-by-screen UI spec.
- Responsive rules для 360/390/768/desktop.
- Component inventory для vanilla implementation.

Quality gate:

- Не использовать card-in-card layouts.
- Не превращать app-mode в marketing landing.
- Все form controls имеют visible label/error/disabled/loading state.

### Frontend Agent

Read/write:

- `landing/js/riot-site.js`
- `landing/css/riot-site.css`
- `landing/index.html`, если нужны meta/SEO изменения.

Output:

- Реализация UI/UX задач по фазе.
- Обновленные static assets только при необходимости.

Quality gate:

- `node --check landing/js/riot-site.js`
- Mobile smoke вручную или Playwright screenshot.
- Не ломать Mini App в `webapp/`.

### Backend Web API Agent

Read/write:

- `api/web/`
- `api/realtime.py`
- shared serializers только совместимо.

Output:

- Web-friendly endpoints для сайта.
- Тесты API contracts.

Quality gate:

- Не менять payment/KIE webhook без отдельной задачи.
- Не отдавать stale local upload URLs.
- Auth tokens не появляются в logs/query.

### QA Agent

Read:

- roadmap phase acceptance criteria;
- changed files;
- `.logs/bot.log` для production smoke.

Output:

- QA report с passed/failed/blockers.
- Список regression risk.

Quality gate:

- Проверить guest route, authenticated route, generation queue, missing media, WS fallback.
- Запустить `tools/codex_static_checks.sh` перед финалом, если были code changes.

## 7. Recommended Implementation Order

1. Закрыть P0 bugs и production log noise.
2. Довести studio validation/review/result lifecycle.
3. Улучшить result cards и multi-result gallery.
4. Сделать feed/prompts настоящим входом в studio.
5. Укрепить billing/profile/referrals.
6. Добавить public SEO/content слой.
7. Разбить `riot-site.js` на модули.
8. Добавить Playwright visual/e2e smoke.

## 8. Release Checklist

Перед каждым release сайта:

- `node --check landing/js/riot-site.js`
- `npm run build` в `webapp/`, если менялся Mini App
- `nginx -t`, если менялся nginx config
- `tools/codex_static_checks.sh`, если были code changes
- Проверить `/api/web/health`
- Проверить `/`
- Проверить `/api/v1/ws/generations` через браузер или WS-клиент
- Проверить отсутствующий `/static/upload/missing.jpg`
- Проверить, что `.logs/bot.log` не содержит новых auth secrets в URL
- Проверить mobile viewport 390px

## 9. Риски

| Риск | Симптом | Митигация |
|---|---|---|
| `riot-site.js` станет слишком большим | Новые фичи ломают старые routes | Фаза 8: модульное разделение |
| Разные клиенты используют один `/api/v1/*` | Правка сайта ломает Mini App | Добавлять совместимые поля, не менять required payloads |
| Provider result URLs исчезают | Карточки ломаются или 404 | Фильтр local upload + media fallback + external URL fallback UI |
| WebSocket зависит от nginx | Realtime не работает в production | Dedicated `/api/v1/ws/` location + polling fallback |
| Static тексты устаревают | Цены/модели на сайте не совпадают с БД | Динамически тянуть models/plans, не хардкодить цены |
| Payment UX вызывает дубли | Несколько invoice/session на один клик | Busy state, idempotent UI, clear pending state |

## 10. Definition Of Done Для Большой Итерации

Итерация считается завершенной, если:

- основной user journey проходит без ручного refresh;
- ошибки API отображаются человеку понятным текстом;
- нет новых 404 по stale local upload в нормальном flow;
- realtime работает или graceful fallback polling активен;
- mobile и desktop выглядят без наложений;
- acceptance criteria текущей фазы отмечены в QA report;
- проверки пройдены и warnings/risks явно перечислены.
