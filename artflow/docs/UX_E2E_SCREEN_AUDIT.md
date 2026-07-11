# APIX — screen-by-screen UX and E2E audit

Дата: 2026-07-11  
Ветка baseline: `miniapp-mvp`  
Канонический standalone frontend: `landing/*.html`, `landing/css/prototype-premium.css`, `landing/js/prototype-premium.js`.

## 1. Область проверки

В проекте существуют две разные пользовательские поверхности:

1. **Standalone сайт** — публичные страницы, Studio и web-кабинет в `landing/`.
2. **Telegram Mini App** — React/Vite приложение в `webapp/`, публикуемое по `/app`.

Их нельзя смешивать в одном UX-аудите. Этот документ фиксирует основной web-путь standalone сайта. Mini App проверяется отдельной сборкой и отдельным мобильным smoke.

## 2. Карта экранов

| Экран | URL | Основная задача пользователя |
|---|---|---|
| Главная | `/` | Понять продукт и выбрать сценарий |
| Studio | `/studio.html` | Запустить картинку, видео или музыку |
| Каталог моделей | `/models.html` | Выбрать модель по задаче и цене |
| Страница модели | `/model.html?model=<key>` | Изучить модель и перейти в Studio |
| Лента | `/gallery.html` | Найти пример и повторить идею |
| Кабинет | `/account.html` | Управлять работами и аккаунтом |
| Очередь | `/account.html#queue` | Следить за активными задачами |
| История | `/account.html#library` | Открывать и скачивать результаты |
| Billing | `/account.html#billing` | Проверить баланс и пополнить credits |
| Referrals | `/account.html#referrals` | Получить ссылку, статистику и выплаты |
| Prompts | `/account.html#prompts` | Хранить и отправлять идеи на модерацию |
| Feed | `/account.html#feed` | Работать с лентой из кабинета |
| Assistant | `/account.html#assistant` | Получить помощь по идее или продукту |
| Profile | `/account.html#profile` | Изменить данные и пароль |
| Admin | `/account.html#admin` | Управлять проектом и модерацией |
| Telegram Mini App | `/app` | Мобильная работа внутри Telegram |

## 3. Основные пользовательские маршруты

### 3.1. Гость → понимание продукта → вход

```text
Главная
→ выбор сценария
→ Studio / Models / Gallery
→ объяснение ограничений гостя
→ вход
→ возврат к выбранному сценарию
```

Критерии:

- первый экран объясняет image/video/music;
- CTA не приводит к пустой странице;
- после входа сохраняется выбранный сценарий;
- пользователь понимает, зачем нужна авторизация.

### 3.2. Первая генерация изображения

```text
Вход
→ Studio
→ Картинка с нуля
→ промпт
→ модель
→ формат и качество
→ проверка стоимости
→ запуск
→ очередь
→ результат
→ история / скачать / повторить
```

Критерии:

- запуск невозможен без обязательных данных;
- цена и итоговые параметры видны до списания;
- двойной клик не создаёт две задачи;
- результат появляется без ручного refresh;
- ошибка показывает возврат credits.

### 3.3. Работа по референсу

```text
Studio
→ Картинка по референсу
→ загрузить JPEG/PNG/WebP
→ preview
→ prompt-from-photo при необходимости
→ модель с поддержкой reference/edit
→ запуск
```

Критерии:

- неподдерживаемый файл отклоняется до API;
- пользователь видит, сколько референсов принято;
- модель без reference capability недоступна;
- сломанное preview имеет fallback.

### 3.4. Видео и музыка

```text
Studio
→ Video или Music
→ только релевантные поля
→ стоимость
→ запуск
→ очередь
→ video/audio result
```

Критерии:

- image-only поля не мешают music/video;
- duration/resolution влияют на стоимость;
- готовый media result можно открыть и скачать.

### 3.5. Billing

```text
Кабинет
→ Баланс
→ пакет
→ способ оплаты
→ pending
→ webhook paid/failed/refunded
→ обновлённый баланс
```

Критерии:

- показываются только включённые провайдеры;
- повторный клик не создаёт хаос из invoice;
- webhook идемпотентен;
- баланс обновляется без refresh.

### 3.6. Referrals

```text
Кабинет
→ Партнёрка
→ скопировать ссылку
→ регистрация реферала
→ оплата реферала
→ комиссия
→ заявка на вывод
```

Критерии:

- нельзя пригласить самого себя;
- нельзя создать цикл;
- видны L1/L2/L3, pending и minimum withdrawal;
- refund откатывает комиссию один раз.

### 3.7. Admin

```text
Администратор
→ Управление
→ пользователи / генерации / тарифы / withdrawals / prompts
→ действие
→ подтверждение
→ audit/ledger
```

Критерии:

- обычный пользователь не видит навигацию;
- backend возвращает 403 независимо от скрытия кнопки;
- финансовое действие фиксируется в audit/ledger.

## 4. Screen-by-screen findings

### 4.1. Главная

**Что уже хорошо**

- оффер объясняет image/video/music;
- основные сценарии разведены отдельными карточками;
- есть переходы в модели и Studio;
- canonical и social preview используют основной домен.

**Разрывы**

- **P0:** CTA «Начать создание» ведёт в Studio, но гостю Studio показывает auth gate вместо формы. Это не технический тупик, но обещание CTA и следующий экран не совпадают.
- **P1:** после входа необходимо гарантированно возвращать пользователя к выбранному `type/flow/model`, а не в общий кабинет.
- **P1:** auth microcopy на разных страницах различается: «Email или Telegram», «Email или телефон» и разные placeholders.

### 4.2. Studio

**Что уже хорошо**

- есть отдельные маршруты text/reference/edit/video/music;
- основные параметры находятся выше advanced settings;
- reference upload ограничен JPEG/PNG/WebP;
- есть queue/result links.

**Разрывы**

- **P0:** выбор сценария и composer скрыты через `data-auth-only`; гость не может спокойно собрать черновик и войти только перед запуском.
- **P0:** textarea содержит готовый промпт как значение, а не placeholder. Пользователь может запустить чужой пример и потратить credits.
- **P0:** в статическом screen contract нет отдельного review блока с моделью, ценой, refs, параметрами и балансом после запуска.
- **P1:** в одном composer присутствуют image/video/music controls; JS обязан безошибочно скрывать нерелевантные поля для каждого режима.
- **P1:** launch CTA должен иметь явные `disabled`, `busy` и idempotency states.

### 4.3. Models

**Что уже хорошо**

- есть фильтры image/video/music;
- показатели и карточки загружаются динамически;
- пользователь видит стоимость и переход к обучению.

**Разрывы**

- **P1:** нужно явно отличать loading, empty и API error, а не оставлять пустой grid.
- **P1:** варианты одной model family должны группироваться, чтобы пользователь не видел технические дубли.
- **P2:** карточка должна объяснять, требует ли модель reference и какие ограничения имеет.

### 4.4. Model detail

**Что уже хорошо**

- экран выделен отдельно и может быть SEO-входом;
- предусмотрен переход к тесту в Studio.

**Разрывы**

- **P1:** базовая разметка содержит только «Загружаем модель и примеры...». При API error нужен полноценный retry/fallback.
- **P1:** неизвестный `model` должен показывать 404-like state, а не бесконечную загрузку.
- **P2:** canonical всех моделей сейчас общий `/model.html`; для SEO нужна осознанная стратегия параметрических страниц.

### 4.5. Gallery

**Что уже хорошо**

- доступны recent/top-day сценарии;
- есть быстрые переходы в image/reference/video/music;
- лента публична для гостя.

**Разрывы**

- **P1:** detail/remix/use-reference должны объяснять, что произойдёт после клика;
- **P1:** карточка без media должна иметь устойчивый fallback;
- **P1:** auth copy отличается от остальных страниц.

### 4.6. Account

**Что уже хорошо**

- queue, library, billing, referrals, prompts, assistant, profile и admin собраны в одной оболочке;
- hash-routing позволяет открывать нужный раздел напрямую;
- admin navigation имеет отдельный marker.

**Разрывы**

- **P1:** экран очень плотный; на mobile sidebar должен превращаться в компактную навигацию без горизонтального overflow;
- **P1:** queue/history/billing/referrals требуют независимых loading/error/empty states;
- **P1:** скрытие admin кнопки не является защитой — E2E и API tests должны отдельно проверять 403;
- **P2:** account не должен индексироваться и рекламироваться через sitemap.

### 4.7. Telegram Mini App

**Что уже хорошо**

- отдельный React/Vite frontend;
- отдельная сборка;
- backend проверяет Telegram initData;
- `/app` не смешан с standalone страницами.

**Разрывы**

- **P1:** нужен отдельный device smoke внутри Telegram WebView;
- **P1:** safe-area, системная клавиатура и back button нельзя полноценно проверить обычным desktop браузером;
- **P1:** auth fallback вне Telegram должен быть понятным и не показывать demo state как production.

## 5. Автоматизированное E2E-покрытие

Playwright suite расположен в `tests/e2e/` и использует детерминированные mock API/WebSocket. Он не списывает реальные credits и не вызывает AI/payment providers.

| Тест | Что проверяет |
|---|---|
| Home guest | Hero, основные CTA, login modal |
| Models | Загрузка каталога и фильтр video |
| Gallery | Загрузка real-like feed cards и top-day switch |
| Studio guest | Явный auth gate вместо blank screen |
| Studio authenticated | Заполнение prompt и POST generation API |
| Account | Hash routing billing → referrals |
| Admin visibility | Admin navigation только для admin user |
| Mobile 390 px | Отсутствие горизонтального overflow на ключевых страницах |
| API failure | Public shell остаётся видимым при ошибке landing API |

Каждый ключевой тест прикладывает screenshot в Playwright report. При падении сохраняются trace, screenshot и video.

## 6. Что mock E2E не заменяет

Следующие сценарии требуют staging или production-like среды:

- реальный Telegram Login и initData;
- реальный Telegram WebView;
- реальные TBank/Stars/Crypto/Lava webhooks;
- фактический KIE/Comet generation lifecycle;
- nginx WebSocket upgrade;
- provider URLs, большие video/audio files;
- push-уведомления в Telegram;
- восстановление после рестарта app/Redis/Postgres.

Для них нужен отдельный staging smoke с тестовыми аккаунтами и нулевыми/минимальными расходами.

## 7. Рекомендуемый порядок UX-доработки

1. Убрать готовый prompt из значения textarea и оставить его примером-placeholder.
2. Разрешить гостю собрать черновик Studio; открывать вход перед фактическим запуском.
3. Добавить review step: model, price, refs, settings, balance after run.
4. Установить disabled/busy/idempotency states на launch/payment/actions.
5. Унифицировать auth microcopy на всех страницах.
6. Добавить явные loading/error/empty/retry states.
7. После стабилизации screen flow — улучшать декоративный visual.

## 8. Команды

Из `artflow/tests/e2e/`:

```bash
npm install
npx playwright install chromium
npm test
```

Результаты:

- `playwright-report/` — HTML report;
- `test-results/` — trace, screenshot, video и вложенные screen captures.

## 9. Definition of done

Экран или flow считается готовым, когда:

- пользователь понимает следующее действие;
- normal/loading/empty/error/unauthorized states определены;
- цена и последствия действия видны заранее;
- мобильный viewport не ломается;
- protected action проверяется backend, а не только UI;
- E2E проходит на desktop и mobile;
- реальный staging smoke пройден для интеграций, которые нельзя безопасно замокать.
