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
