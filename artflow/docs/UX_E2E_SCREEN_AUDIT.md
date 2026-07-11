# APIX — screen-by-screen UX and E2E audit

Дата: 2026-07-11  
Baseline: `miniapp-mvp`  
Канонический standalone frontend: `landing/*.html`, `landing/css/prototype-premium.css`, `landing/js/prototype-premium.js`.

## 1. Область проверки

В проекте две отдельные поверхности:

1. **Standalone сайт** — публичные страницы, Studio и web-кабинет в `landing/`.
2. **Telegram Mini App** — React/Vite приложение в `webapp/`, доступное по `/app`.

Этот аудит покрывает standalone сайт. Mini App проверяется отдельной сборкой; поведение внутри Telegram WebView требует отдельного device smoke.

## 2. Карта экранов

| Экран | URL | Главная задача |
|---|---|---|
| Главная | `/` | Понять продукт и выбрать сценарий |
| Studio | `/studio.html` | Создать картинку, видео или музыку |
| Модели | `/models.html` | Выбрать модель по задаче и цене |
| Модель | `/model.html?model=<key>` | Изучить возможности и запустить тест |
| Лента | `/gallery.html` | Найти идею и повторить результат |
| Кабинет | `/account.html` | Управлять работами и аккаунтом |
| Очередь | `/account.html#queue` | Следить за активными задачами |
| История | `/account.html#library` | Открывать и скачивать результаты |
| Billing | `/account.html#billing` | Проверить баланс и пополнить credits |
| Referrals | `/account.html#referrals` | Ссылка, статистика и выплаты |
| Prompts | `/account.html#prompts` | Сохранять и публиковать идеи |
| Assistant | `/account.html#assistant` | Получить помощь по идее или продукту |
| Profile | `/account.html#profile` | Изменить данные и пароль |
| Admin | `/account.html#admin` | Управлять проектом и модерацией |
| Mini App | `/app` | Работать внутри Telegram |

## 3. Главный E2E-маршрут

```text
Главная
→ выбрать сценарий
→ вход
→ Studio
→ заполнить prompt
→ выбрать модель и параметры
→ review modal
→ подтвердить стоимость
→ создать задачу
→ очередь
→ результат
→ история / скачать / повторить
```

Критерии:

- пользователь понимает следующее действие;
- обязательные данные проверяются до запроса;
- review показывает модель, сценарий, параметры, references и стоимость;
- повторное нажатие не создаёт вторую задачу;
- результат обновляется без ручного refresh;
- ошибка показывает понятную причину и возврат credits.

## 4. Проверенные сильные стороны

### Главная

- оффер ясно объясняет картинки, видео и музыку;
- сценарии разделены на отдельные карточки;
- есть прямые переходы в Studio, модели и ленту;
- canonical и social preview используют основной домен.

### Studio

- отдельные маршруты для `text`, `reference`, `edit`, `video`, `music`;
- основные настройки расположены выше advanced controls;
- reference upload ограничен JPEG, PNG и WebP;
- **review modal уже реализован** и показывает сценарий, модель, формат, качество, количество, references, prompt и стоимость;
- запуск происходит только после второго явного подтверждения;
- есть переходы в очередь и ленту.

### Models

- каталог загружается динамически;
- работают фильтры image/video/music;
- показывается стоимость;
- варианты model family группируются для пользователя.

### Gallery

- лента публична;
- работают `feed` и `top_day`;
- есть быстрые переходы в image/reference/video/music;
- карточки отображают реальные media previews.

### Account

- hash-routing открывает нужный раздел напрямую;
- queue, history, billing, referrals, prompts, assistant, profile и admin находятся в одной оболочке;
- admin navigation имеет отдельный permission marker.

## 5. Реальные UX-разрывы

### P0

1. **Гость не может собрать черновик Studio.** Composer и выбор сценария скрыты до входа. Главный CTA «Начать создание» приводит к auth gate. Это не пустой экран, но создаёт лишний шаг до первого контакта с продуктом.
2. **Защита от случайного запуска.** Ранее textarea содержала готовый prompt как значение. Исправлено: пример перенесён в placeholder, поле открывается пустым.
3. **Exactly-once launch.** Review существует, но submit, confirm и API должны сохранять busy/idempotency state до получения ответа.

### P1

1. После входа нужно гарантированно сохранять `type`, `flow`, `model`, prompt draft и references.
2. Auth microcopy различается между страницами: «Email или Telegram», «Email или телефон», разные placeholders.
3. Все динамические блоки должны отдельно иметь loading, empty, error и retry states.
4. `model.html` должен показывать понятный not-found/error state, а не бесконечное «Загружаем модель».
5. Account на мобильном требует отдельной проверки sidebar, hash navigation и экранной клавиатуры.
6. Скрытие admin-кнопки не является защитой: backend обязан возвращать 403.

### P2

1. Нужна отдельная SEO-стратегия для параметрических страниц `model.html?model=...`.
2. Требуется accessibility pass: keyboard navigation, focus states, labels, `aria-live` для статусов.
3. Для Mini App нужен device smoke внутри реального Telegram WebView.

## 6. Автоматизированное E2E-покрытие

Playwright suite находится в `tests/e2e/`. API и WebSocket замоканы, поэтому тесты не списывают credits и не вызывают AI/payment providers.

| Тест | Проверка |
|---|---|
| Home guest | Hero, CTA, login modal |
| Models | Каталог и фильтр video |
| Gallery | Media cards и top-day switch |
| Studio guest | Явный auth gate вместо blank screen |
| Studio authenticated | Prompt → review modal → один generation request |
| Account | Hash routing billing → referrals |
| Admin visibility | Admin navigation только для admin |
| Mobile 390 px | Нет горизонтального overflow |
| API failure | Public shell остаётся видимым при ошибке API |

При падении CI сохраняет:

- HTML Playwright report;
- screenshots;
- trace;
- video;
- screen captures ключевых страниц.

## 7. Что mock E2E не заменяет

На staging или production-like окружении отдельно проверить:

- реальный Telegram Login;
- initData и Telegram WebView;
- TBank, Stars, Crypto и Lava sandbox/webhooks;
- фактическую KIE/Comet generation lifecycle;
- WebSocket upgrade через nginx;
- большие video/audio results;
- Telegram notifications;
- восстановление после рестарта app, Redis и Postgres.

## 8. Рекомендуемый порядок UX-доработки

1. Закрепить пустой prompt по умолчанию и inline validation.
2. Сохранять выбранный сценарий и draft через auth flow.
3. Укрепить review: balance-after, busy state, duplicate-submit protection.
4. Добавить независимые loading/error/empty/retry states.
5. Унифицировать auth microcopy.
6. Пройти staging smoke реальных интеграций.
7. Только затем продолжать декоративную полировку.

## 9. Команды

Из `artflow/tests/e2e/`:

```bash
npm install
npx playwright install chromium
npm test
```

Из `artflow/`:

```bash
python -m compileall api bot core db main.py
node --check landing/js/prototype-premium.js
pytest -q
```

Из `artflow/webapp/`:

```bash
npm ci
npm run build
```

## 10. Definition of done

Экран или flow готов, когда:

- следующее действие очевидно;
- normal/loading/empty/error/unauthorized states определены;
- стоимость и последствия видны до подтверждения;
- protected action проверяется backend;
- desktop и mobile E2E проходят;
- реальные интеграции проверены staging smoke;
- production deploy заблокирован при падении любого quality gate.
