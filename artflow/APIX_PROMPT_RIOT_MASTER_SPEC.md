# APIX Prompt Riot Zine — Полная продуктовая спецификация

Дата: 2026-05-16  
Проект: APIX standalone site на `apix.chillcreative.ru`  
Зона разработки: `landing/`, `api/web/`, совместимые расширения `/api/v1/*`  
Стиль: Prompt Riot Zine

## 0. Короткое резюме

APIX должен стать самостоятельной web-студией генерации, а не только витриной Telegram-бота.

Целевая цепочка:

```text
витрина -> вход через Telegram -> студия -> очередь -> результат -> следующий шаг -> история/feed
```

Главная идея продукта:

```text
Пользователь не просто получает один результат.
Пользователь работает в цикле: идея -> генерация -> результат -> вариант -> анимация -> публикация -> ремикс.
```

## 1. Принципы продукта

### 1.1. Один главный action на экран

На каждом экране должен быть один очевидный следующий шаг.  
Нельзя давать пользователю 10 равнозначных CTA в одном состоянии.

### 1.2. Цена и модель видны до запуска

Перед списанием всегда показываем:

- выбранную модель;
- friendly label модели;
- technical model key;
- стоимость;
- текущий баланс;
- что будет создано;
- какие медиа будут использованы как reference;
- какие ограничения есть.

### 1.3. Result is not the end

Каждый результат должен иметь next actions:

- Variant;
- Animate;
- Use prompt;
- Use as reference;
- Publish to feed;
- Save to library;
- Download/Open;
- Reuse idea.

### 1.4. Feed и Prompt Library ведут обратно в Studio

Feed и библиотека не должны быть пассивными каталогами.  
Каждая карточка должна предлагать действие:

```text
Use -> Studio
Remix -> Studio
Use as reference -> Studio
```

### 1.5. Telegram sync не должен быть непонятным

Пользователь должен понимать:

- web и Telegram используют один баланс;
- результат может прийти в web и Telegram;
- Telegram нужен для identity, уведомлений и связи аккаунта;
- Mini App — отдельная поверхность, не смешивается со standalone site.

## 2. Поверхности продукта

### 2.1. Public Site

Путь: `/`  
Код: `landing/index.html`, `landing/js/riot-site.js`, `landing/css/riot-site.css`

Роль:

- публичная витрина;
- вход в web-студию;
- реальные примеры;
- Prompt Library preview;
- Feed preview;
- SEO/FAQ.

### 2.2. Web Studio

Путь: `/`, SPA state внутри `landing/`

Роль:

- image/video/music generation;
- active queue;
- results;
- next actions;
- history;
- feed/prompts;
- billing;
- profile.

### 2.3. Web API

Путь: `/api/web/*`  
Роль:

- auth;
- profile;
- feed;
- prompts;
- models;
- plans;
- lightweight web-specific responses.

### 2.4. Generation API

Путь: `/api/v1/*`  
Роль:

- generation launch;
- history;
- models;
- billing;
- referrals;
- active task lifecycle.

### 2.5. Realtime

Путь: `/api/v1/ws/generations`  
Роль:

- push statuses;
- queue sync;
- result events;
- balance updates.

### 2.6. Mini App

Путь: `/app`  
Роль:

- Telegram Mini App;
- отдельная поверхность;
- не смешивать с standalone site.

## 3. Глобальная навигация

Desktop:

```text
APIX logo
Studio
Prompts
Feed
Works
Billing
Profile
Balance badge
Login/Profile CTA
```

Mobile:

```text
Top bar:
- logo
- balance
- menu button

Bottom tabs:
- Studio
- Prompts
- Feed
- Works
- Profile
```

Не делать тяжёлый marketing header внутри authenticated app-mode.

## 4. Глобальные состояния

### 4.1. Guest

Видит:

- public home;
- examples;
- public feed preview;
- prompt library preview;
- pricing preview;
- login CTA.

Не может:

- запускать генерацию;
- лайкать;
- публиковать;
- сохранять;
- покупать.

При попытке действия:

```text
Чтобы использовать этот prompt, войдите через Telegram.
```

### 4.2. Authenticated

Видит:

- баланс;
- studio;
- queue;
- history;
- billing;
- profile;
- referrals.

Может:

- запускать generation;
- использовать prompts;
- делать remix;
- лайкать;
- публиковать;
- пополнять баланс.

### 4.3. Loading

Для каждого major block:

- skeleton card;
- shimmer;
- no layout jump.

### 4.4. Error

Показываем human readable error:

```text
Не удалось загрузить ленту.
Проверьте соединение или обновите страницу.
```

Не показываем raw JSON пользователю.

### 4.5. Empty

Каждая пустая зона должна иметь CTA:

- пустая история -> “Создать первый результат”;
- пустая лента -> “Опубликовать работу”;
- пустая библиотека -> “Добавить prompt”;
- пустая очередь -> “Запустить генерацию”.

## 5. Визуальная система Prompt Riot Zine

### 5.1. Палитра

```css
--riot-bg: #08070b;
--riot-ink: #f6f0e8;
--riot-paper: #f8f1df;
--riot-paper-aged: #e2d6bd;
--riot-pink: #ff007c;
--riot-cyan: #00e5ff;
--riot-yellow: #f7ff00;
--riot-green: #39ff88;
--riot-violet: #9b5cff;
--riot-red: #ff2b4f;
--riot-muted: #a7a7ad;
```

### 5.2. Фоны

Использовать:

- black wall;
- noise overlay;
- photocopy grain;
- scratched texture;
- torn poster shapes;
- neon spray blobs.

Не использовать:

- чистый corporate gradient;
- чрезмерно белые страницы;
- card-in-card перегруз;
- long paragraphs inside tiny cards.

### 5.3. Типографика

Headlines:

- bold condensed sans;
- uppercase;
- poster scale.

Body:

- readable sans;
- normal casing.

Technical:

- monospace for model keys, task ids, costs, websocket status.

### 5.4. Компоненты визуального стиля

- torn paper card;
- sticker tab;
- stamp CTA;
- zine filter chip;
- collage thumbnail;
- tape label;
- photocopy divider;
- noisy empty state;
- drawer on black paper;
- neon focus outline.

## 6. Ключевой user journey

### 6.1. Guest to first generation

1. Гость открывает `/`.
2. Видит hero и реальные примеры.
3. Нажимает `Open Studio`.
4. Видит login gate.
5. Входит через Telegram.
6. Попадает в Studio.
7. Выбирает режим `Image`.
8. Вводит идею.
9. Добавляет reference, если нужно.
10. Выбирает модель.
11. Настраивает параметры.
12. Проверяет review panel.
13. Нажимает `Run`.
14. Видит queue item.
15. Получает result через WS или polling.
16. Нажимает `Variant`, `Animate` или `Publish`.

### 6.2. Prompt library to studio

1. Пользователь открывает Prompts.
2. Выбирает карточку.
3. Открывает preview drawer.
4. Нажимает `Use prompt`.
5. Studio открывается с prefilled idea.
6. Пользователь меняет параметры.
7. Запускает генерацию.

### 6.3. Feed to remix

1. Пользователь открывает Feed.
2. Выбирает работу.
3. Видит автора, модель, prompt policy.
4. Нажимает `Remix`.
5. Видит объяснение: “используется идея автора”.
6. Studio открывается с reference/prompt state.
7. Пользователь запускает remix.

### 6.4. Billing

1. Пользователь открывает Billing.
2. Видит баланс и пакеты.
3. Выбирает план.
4. Видит методы оплаты.
5. Нажимает оплату.
6. Видит pending payment state.
7. После webhook баланс обновляется.
8. UI показывает paid/failed/refunded.

## 7. Главные окна

Подробно каждое окно описано в `docs/SCREEN_BY_SCREEN_SPEC.md`.

Минимальный набор:

1. Landing / Home
2. Auth / Telegram Sync
3. Studio Shell
4. Studio Image Flow
5. Studio Video Flow
6. Studio Music Flow
7. Queue Panel
8. Result Detail Drawer
9. Multi-result Gallery
10. Prompt Library
11. Prompt Detail Drawer
12. Add Prompt
13. Prompt Moderation Status
14. Feed
15. Feed Detail Drawer
16. My Works / History
17. Billing
18. Payment Pending
19. Profile
20. Referrals
21. Admin Moderation
22. Settings / Language
23. Help / FAQ
24. Error / Empty / Loading states
25. Mobile shell

## 8. Release priority

### P0

- stable media URL handling;
- studio review/validation;
- realtime lifecycle;
- mobile layout QA;
- no auth secrets in logs;
- `/api/web/health`;
- `/` actual SPA.

### P1

- result detail drawer;
- multi-result gallery;
- prompt drawer;
- feed detail;
- billing trust states.

### P2

- SEO/FAQ/sitemap;
- modularize `riot-site.js`;
- Playwright visual QA.

## 9. Definition of Done

Итерация считается готовой, если:

- основной user journey проходит без ручного refresh;
- ошибки API видны человеческим текстом;
- нет 404 по stale local upload в нормальном flow;
- realtime работает или polling fallback активен;
- mobile и desktop без наложений;
- форма не запускается без required fields;
- цена видна до запуска;
- result имеет next actions;
- acceptance criteria текущей фазы отмечены в QA report.


---

# Screen-by-screen UI Spec — APIX Prompt Riot Zine

## 1. Landing / Home

### Цель

Гость за первый экран должен понять:

- что APIX — web + Telegram AI media studio;
- можно генерировать image/video/music;
- есть prompt library и remix feed;
- вход через Telegram;
- реальные результаты можно увидеть сразу.

### Layout

Desktop:

```text
Header
Hero
Live examples strip
Studio value block
Prompt Library preview
Feed preview
Pricing preview
FAQ
Footer
```

Mobile:

```text
Logo + Login
Hero compact
CTA
Examples carousel
Features
FAQ
```

### Blocks

#### Header

Elements:

- APIX logo;
- Studio;
- Prompts;
- Feed;
- Pricing;
- FAQ;
- Login via Telegram.

States:

- guest;
- authenticated;
- loading profile.

#### Hero

Title:

```text
AI media studio for images, video, music and remix workflows
```

RU:

```text
AI-студия для изображений, видео, музыки и ремиксов
```

CTA:

- `Открыть студию`
- `Смотреть ленту`
- `Подключить Telegram`

#### Live examples

Show 6-12 curated public cards.

Each card:

- preview;
- model badge;
- prompt excerpt;
- `Remix`;
- `Use idea`.

Empty fallback:

```text
Пока примеры загружаются. Открой студию и создай первый результат.
```

### Acceptance

- Guest understands product in first viewport.
- CTA does not lead to dead end.
- Real examples are dynamic when API is available.
- No hardcoded old prices.

## 2. Auth / Telegram Sync

### Цель

Связать web session с Telegram identity.

### States

#### Guest

Shows:

- Telegram login button;
- why Telegram is needed;
- privacy note;
- guest mode limitation.

#### Connected

Shows:

- Telegram username;
- credits;
- active session count;
- history count.

#### Merge needed

If web guest state or local drafts exist:

- show merge card;
- allow merge;
- allow discard local state.

### Copy

```text
Мы используем Telegram, чтобы синхронизировать баланс, историю и уведомления.
```

### Error states

- Telegram auth expired;
- invalid signature;
- backend unavailable;
- user banned.

### Acceptance

- User sees what will sync.
- No auth token appears in URL logs.
- Login failure has retry button.

## 3. App Shell

### Цель

Единая оболочка authenticated app.

### Desktop layout

```text
Left nav
Top context bar
Main content
Right drawer / inspector
Toast layer
Queue mini panel
```

### Mobile layout

```text
Top compact bar
Content
Bottom tabs
Drawer overlays
```

### Navigation items

- Studio
- Prompts
- Feed
- Works
- Billing
- Profile
- Admin, if admin

### Top bar

Elements:

- current page title;
- credits badge;
- realtime status;
- profile menu.

Realtime indicator:

- hidden by default;
- show only when reconnecting or in technical queue panel.

## 4. Studio Home

### Цель

Запустить image/video/music без путаницы.

### Entry cards

- Image
- Video
- Music
- Prompt from Library
- Continue active queue
- Continue last result

### State

If active queue exists:

- show active queue summary;
- show “Continue work”.

If no history:

- show quick start scenarios.

### Acceptance

- First action is obvious.
- No technical model ids in primary choice.

## 5. Studio Image Flow

### Цель

Создать image за 60-90 секунд после входа.

### Stepper

```text
mode -> idea -> media -> model -> settings -> review -> run
```

### Step 1. Mode

Options:

- Text to Image
- Image to Image
- Edit / Reference
- Prompt Library
- From Feed

Fields:

- mode card;
- short explanation;
- required media indicator.

### Step 2. Idea

Fields:

- prompt textarea;
- helper chips;
- negative prompt optional;
- enhance prompt toggle optional;
- prompt length indicator.

Helper chips:

- photorealistic;
- cinematic;
- product;
- fashion;
- anime;
- poster;
- grunge;
- neon;
- clean background.

Validation:

- prompt required;
- minimum useful length warning, not blocker;
- show inline error.

### Step 3. Media

Fields:

- upload image;
- drag/drop;
- reference list;
- clear ref;
- use last result;
- use feed card ref.

States:

- empty;
- uploading;
- uploaded;
- unsupported file;
- too large;
- broken preview.

### Step 4. Model

Shows:

- friendly label;
- technical model key;
- cost;
- capabilities.

Filters:

- fast;
- quality;
- edit;
- image-compatible;
- cheap;
- pro.

### Step 5. Settings

Fields:

- aspect ratio;
- quality;
- count;
- seed optional;
- safety/content checker if available.

Aspect ratio order:

- 9:16 first when available;
- then 1:1, 16:9, 4:5, 3:4, others.

### Step 6. Review

Panel:

- mode;
- model;
- cost;
- balance after run;
- prompt preview;
- refs count;
- settings;
- warnings.

CTA:

- Run generation
- Save draft
- Back

### Step 7. Run / Queue

After click:

- lock submit;
- create queue item;
- show task status;
- show WebSocket/polling fallback state;
- allow cancel only if backend supports cancellation.

### Acceptance

- Run disabled until required fields exist.
- Cost visible before click.
- Error near field.
- Review panel readable on mobile.

## 6. Studio Video Flow

### Цель

Создать video из text/image/video reference.

### Modes

- Text to Video
- Image to Video
- Video to Video
- Animate image
- Motion / Camera control

### Fields

- prompt;
- media upload;
- model;
- duration;
- aspect ratio;
- resolution;
- reference video;
- first frame;
- last frame if supported.

### Review

Must show:

- expected generation time;
- cost;
- model;
- media requirements;
- output type.

### Result actions

- Open;
- Download;
- Reuse idea;
- Publish/share;
- Save to history.

## 7. Studio Music Flow

### Цель

Создать music/audio без ухода в Telegram/Mini App.

### Modes

- Lyrics to Song
- Idea to Song
- Instrumental
- Remix lyrics

### Fields

- style;
- lyrics;
- genre;
- mood;
- duration if supported;
- vocal/instrumental.

### Result

- audio player;
- title;
- style;
- lyrics drawer;
- download/open;
- reuse lyrics/idea.

## 8. Queue Panel

### Цель

Показывать lifecycle генераций.

### Queue item fields

- task id short;
- generation type;
- model;
- cost;
- status;
- progress if known;
- started at;
- retry/inspect.

### Statuses

- draft;
- validating;
- queued;
- processing;
- done;
- failed;
- refunded;
- stale.

### WebSocket states

- connected;
- reconnecting;
- fallback polling;
- offline.

### On done

Update:

- queue item;
- history;
- balance;
- result preview;
- toast once.

### On failed

Show:

- reason;
- refund status;
- retry action.

## 9. Result Card

### Цель

Единый формат для image/video/music.

### Base fields

- media preview;
- type;
- model;
- cost;
- created time;
- prompt excerpt;
- status;
- actions.

### Image actions

- Variant;
- Animate;
- Use prompt;
- Publish to feed;
- Save to library;
- Use as reference;
- Download.

### Video actions

- Preview;
- Open;
- Download;
- Reuse idea;
- Publish/share.

### Music actions

- Play;
- Download;
- Reuse lyrics;
- Reuse style;
- Open detail.

## 10. Result Detail Drawer

### Цель

Сделать результат управляемым.

### Sections

- preview;
- prompt full;
- model;
- settings;
- references;
- cost;
- source;
- task lifecycle;
- result URLs;
- next actions.

### Special

For multi-result image:

- show gallery;
- select primary;
- download all;
- publish selected.

## 11. Prompt Library

### Цель

Каталог промптов как growth loop.

### Views

- Catalog
- Popular
- Best
- My Prompts
- Collections
- Pending moderation

### Filters

- search;
- category;
- tags;
- model;
- media type;
- popularity;
- date.

### Card fields

- preview;
- title;
- description;
- tags;
- model;
- likes;
- uses;
- author;
- status if own prompt.

### Actions

- Use prompt;
- Remix;
- Like;
- Share;
- Save;
- Open detail.

### Empty states

No prompts:

```text
Пока нет промптов в этой категории.
Попробуйте другой фильтр или добавьте свой prompt.
```

## 12. Prompt Detail Drawer

### Sections

- large preview;
- prompt text;
- author;
- usage stats;
- model hint;
- tags;
- moderation status;
- actions.

### Actions

- Use prompt;
- Remix from preview;
- Copy;
- Like;
- Report if needed.

### Use prompt behavior

On click:

- route to Studio;
- prefill idea;
- preselect model if compatible;
- preserve source prompt id;
- show “Prompt loaded” toast.

## 13. Add Prompt

### Цель

Пользователь может отправить prompt в библиотеку.

### Steps

```text
preview -> prompt -> metadata -> review -> submit
```

### Fields

- preview image/url;
- prompt text;
- title optional;
- description optional;
- tags optional;
- category optional;
- model optional.

### Auto meta

If title/description/tags missing:

- derive title;
- derive description;
- infer tags.

### Moderation lifecycle

- draft;
- pending;
- approved;
- rejected;
- deactivated.

### Rejected state

Show:

- reject reason;
- edit and resubmit action.

## 14. Feed

### Цель

Публичная лента результатов и ремиксов.

### Filters

- recent;
- top day;
- top all;
- my;
- public;
- image only;
- video only.

### Card fields

- preview;
- author;
- model;
- prompt excerpt or visibility label;
- likes;
- remix count;
- shares;
- created time.

### Actions

- Like;
- Share;
- Remix;
- Use as reference;
- Open detail.

### Remix explanation

Before first remix:

```text
Вы используете идею автора как основу. Результат будет вашей новой генерацией.
```

## 15. Feed Detail Drawer

### Sections

- media;
- author;
- model;
- prompt visibility;
- remix chain;
- actions.

### Restrictions

- `Use as reference` only if media type is image-compatible.
- Disable unsupported actions with reason.

## 16. My Works / History

### Цель

Личный архив.

### Filters

- all;
- image;
- video;
- music;
- published;
- drafts;
- failed;
- refunded.

### Card actions

- Open detail;
- Remix;
- Repeat;
- Publish;
- Download;
- Send to Telegram;
- Delete/hide if policy allows.

### Empty state

```text
Здесь появятся ваши генерации.
Начните с первого prompt.
```

## 17. Billing

### Цель

Понятное и доверенное пополнение.

### Blocks

- current balance;
- price plans;
- payment methods;
- pending payments;
- transaction history;
- refunds.

### Payment methods

Show only if enabled:

- TBank;
- Stars;
- Crypto.

### Plan card

Fields:

- credits;
- price;
- price per credit;
- bonus if any;
- recommended badge.

### States

- idle;
- creating invoice;
- pending;
- paid;
- failed;
- refunded.

### Anti-double-click

After click:

- button busy;
- disable repeated submit;
- show pending invoice.

## 18. Profile

### Цель

Пользователь понимает identity и настройки.

### Fields

- Telegram username;
- tg id masked;
- full name;
- language;
- balance;
- created date;
- referral code;
- connected surfaces.

### Actions

- copy referral link;
- reconnect Telegram;
- logout;
- open support.

## 19. Referrals

### Цель

Показывать уровни и выплаты.

### Sections

- referral link;
- L1/L2/L3 stats;
- available balance;
- pending withdrawals;
- withdrawal form;
- history.

### Validation

Before submit:

- minimum amount;
- payout details required;
- available balance enough.

## 20. Admin Moderation

### Цель

Модерация prompt library.

### Views

- pending;
- approved;
- rejected;
- deactivated.

### Prompt moderation card

Fields:

- preview;
- title;
- prompt excerpt;
- author;
- tags;
- model;
- created time.

Actions:

- approve;
- reject with reason;
- deactivate;
- view author.

## 21. Help / FAQ

### Public FAQ

- What is APIX?
- How Telegram login works?
- What are credits?
- How long generation takes?
- Can results fail?
- What happens to credits on failure?
- How to use prompt library?
- How to pay?
- Privacy.

### In-app help

- model choice tips;
- prompt tips;
- reference tips;
- billing support;
- status explanation.

## 22. Mobile rules

### Breakpoints

- 360px
- 390px
- 768px
- desktop

### Rules

- no horizontal scroll;
- bottom nav fixed;
- drawers full-screen;
- cards one column;
- sticky run button near bottom;
- media preview above settings;
- review panel after form.

## 23. Accessibility

- visible focus state;
- all form controls have labels;
- queue updates use `aria-live`;
- buttons have disabled states;
- error text near fields;
- color not sole indicator;
- media alt fallback.

## 24. Error and fallback states

### API 500

```text
Не удалось выполнить действие. Попробуйте ещё раз.
```

### Missing media

Show placeholder, not broken image.

### Lost WebSocket

```text
Realtime временно недоступен. Статусы обновляются автоматически.
```

### Payment provider disabled

```text
Этот способ оплаты сейчас недоступен.
```

### Unsupported action

```text
Эту работу нельзя использовать как reference для выбранной модели.
```
