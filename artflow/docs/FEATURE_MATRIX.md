# Feature Matrix — APIX Web Studio

## 1. Public / Guest features

### Public Home

Status: required P0  
Surface: `landing/`  
API: `/api/web/feed`, `/api/web/prompts`, `/api/web/models`, `/api/web/price-plans`

Capabilities:

- hero offer;
- CTA to login/studio;
- live examples;
- prompt library preview;
- feed preview;
- pricing preview;
- FAQ;
- SEO meta.

States:

- guest;
- loading;
- API unavailable;
- logged-in redirect prompt.

### Public Feed Preview

Status: required P1  
Surface: `landing/`  
API: `/api/web/feed`

Capabilities:

- recent cards;
- top cards;
- open detail;
- login gate for remix/like.

### Public Prompt Preview

Status: required P1  
Surface: `landing/`  
API: `/api/web/prompts`

Capabilities:

- popular prompts;
- best prompts;
- collections;
- login gate for use/remix.

## 2. Auth features

### Telegram Login

Status: required P0  
Surface: `landing/`, `api/web/auth`

Capabilities:

- validate Telegram auth;
- create/resolve web token;
- sync profile;
- show balance.

Fallback:

- dev token only in non-production.

### Account Sync

Status: required P1  
Surface: profile  
API: `/api/web/me`

Capabilities:

- show Telegram identity;
- show linked surfaces;
- refresh profile.

## 3. Studio features

### Studio Shell

Status: required P0  
Surface: `landing/js/riot-site.js`

Capabilities:

- route state;
- app nav;
- balance badge;
- queue indicator;
- realtime indicator;
- mobile shell.

### Image Generation

Status: required P0  
API: `/api/v1/*` generation endpoints

Flow:

```text
mode -> idea -> media -> model -> settings -> review -> run
```

Capabilities:

- text-to-image;
- image-to-image;
- edit/reference;
- prompt prefill;
- feed reference prefill;
- cost review;
- result preview;
- next actions.

### Video Generation

Status: required P1  
Capabilities:

- text-to-video;
- image-to-video;
- video reference;
- animate image;
- duration;
- resolution;
- output preview.

### Music Generation

Status: P1/P2  
Capabilities:

- idea to song;
- lyrics to song;
- instrumental;
- audio player;
- reuse lyrics.

### Queue

Status: required P0  
API: `/api/v1/ws/generations`, polling fallback

Capabilities:

- active tasks;
- status updates;
- done/failed;
- balance update;
- history update.

## 4. Result features

### Unified Result Card

Status: required P1

Types:

- image;
- video;
- music.

Actions:

- open detail;
- variant;
- animate;
- reuse idea;
- publish;
- save to library;
- download.

### Multi-result Gallery

Status: required P1

Capabilities:

- show all `result_urls`;
- choose primary;
- download all;
- publish selected;
- use selected as reference.

### Result Detail Drawer

Status: required P1

Fields:

- prompt;
- model;
- cost;
- created time;
- refs;
- source;
- status lifecycle;
- result URLs.

## 5. Feed features

### Feed Catalog

Status: required P1  
API: `/api/web/feed`

Filters:

- recent;
- top day;
- top all;
- my;
- public.

Actions:

- like;
- share;
- remix;
- use as reference;
- open detail.

### Feed Detail

Status: required P1

Capabilities:

- media detail;
- author;
- prompt policy;
- remix chain;
- action eligibility.

## 6. Prompt Library features

### Prompt Catalog

Status: required P1  
API: `/api/web/prompts`

Views:

- catalog;
- popular;
- best;
- my prompts;
- collections.

Filters:

- tags;
- category;
- model;
- search.

Actions:

- use;
- remix;
- like;
- share;
- save.

### Prompt Detail Drawer

Status: required P1

Fields:

- preview;
- prompt text;
- model;
- tags;
- stats;
- author;
- moderation status.

### Prompt Submit Flow

Status: required P1

Steps:

- preview;
- prompt text;
- metadata;
- review;
- submit.

Moderation states:

- pending;
- approved;
- rejected;
- deactivated.

## 7. Billing features

### Billing Screen

Status: required P1  
API: `/api/web/price-plans`, `/api/v1/topup/*`

Capabilities:

- balance;
- plans;
- methods;
- transaction history;
- pending states;
- refund states.

### Payment Creation

Status: required P1

Methods:

- TBank;
- Stars;
- Crypto.

Rules:

- show only enabled methods;
- disable double click;
- show pending invoice.

## 8. Profile and referrals

### Profile

Status: required P1

Fields:

- Telegram identity;
- balance;
- language;
- referral code;
- connected surfaces.

### Referrals

Status: required P1

Fields:

- referral link;
- L1/L2/L3;
- available to withdraw;
- pending withdrawals;
- min amount;
- history.

## 9. Admin

### Prompt Moderation

Status: P2 unless marketplace is production-critical

Capabilities:

- pending queue;
- approve;
- reject with reason;
- deactivate;
- audit info.

## 10. Observability

### Frontend safe render

Status: P0

Capabilities:

- safe render wrapper;
- user fallback;
- no blank screen.

### Client event logging

Status: P2

Events:

- login_attempt;
- generation_started;
- generation_done;
- generation_failed;
- prompt_used;
- feed_remix;
- payment_started;
- payment_completed.

Rules:

- no tokens;
- no initData;
- no raw prompt unless policy allows.

### Playwright smoke

Status: P2

Scenarios:

- public home;
- login mock/dev token;
- studio form fill;
- queue item rendering;
- feed actions;
- missing media fallback.
