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
