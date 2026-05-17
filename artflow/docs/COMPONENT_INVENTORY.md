# Component Inventory — Vanilla JS Implementation

## 1. Base components

### RiotButton

Variants:

- primary pink;
- cyan;
- yellow;
- ghost;
- danger;
- disabled;
- loading.

Props:

- label;
- icon;
- onClick;
- disabled;
- loading;
- ariaLabel.

States:

- idle;
- hover;
- focus;
- active;
- disabled;
- loading.

### RiotCard

Variants:

- paper;
- dark;
- media;
- compact;
- danger;
- success.

Rules:

- do not nest card inside card without visual separation;
- long text goes into drawer, not tiny card.

### StickerTab

Used for:

- filters;
- nav;
- status badges;
- category chips.

### Drawer

Positions:

- right desktop;
- bottom/mobile full-screen.

Used for:

- result detail;
- prompt detail;
- feed detail;
- billing invoice;
- settings.

### Toast

Types:

- success;
- error;
- warning;
- info.

Rules:

- one toast per result id;
- do not show critical form errors only in toast.

### EmptyState

Fields:

- title;
- body;
- CTA;
- optional image/icon.

### Skeleton

Types:

- card skeleton;
- list skeleton;
- media skeleton;
- form skeleton.

## 2. Studio components

### StudioStepper

Steps:

- mode;
- idea;
- media;
- model;
- settings;
- review;
- run.

Props:

- activeStep;
- completedSteps;
- blockedSteps.

### ModeCard

Fields:

- title;
- description;
- required media;
- suggested models.

### PromptTextarea

Fields:

- label;
- textarea;
- helper chips;
- char count;
- error;
- enhance toggle optional.

### MediaUploader

States:

- empty;
- dragover;
- uploading;
- uploaded;
- invalid;
- too large;
- broken preview.

Props:

- accepted types;
- max size;
- max count;
- required;
- uploaded files.

### ModelPicker

Fields:

- friendly label;
- technical key;
- cost;
- capability badges;
- selected state.

Filters:

- fast;
- quality;
- edit;
- cheap;
- image-compatible.

### SettingsPanel

Controls:

- aspect ratio;
- quality;
- count;
- duration;
- resolution;
- seed;
- safety checker.

### ReviewPanel

Shows:

- mode;
- prompt;
- model;
- settings;
- refs;
- cost;
- balance after run;
- warnings.

### QueueItem

Fields:

- type;
- model;
- status;
- task id;
- cost;
- started at;
- progress/fallback;
- error.

## 3. Result components

### ResultCard

Types:

- image;
- video;
- music.

Fields:

- media preview;
- title;
- prompt excerpt;
- model;
- status;
- cost;
- actions.

### ResultActions

Buttons:

- Variant;
- Animate;
- Use prompt;
- Publish;
- Save;
- Download;
- Detail.

### ResultDetailDrawer

Sections:

- media;
- prompt;
- model;
- settings;
- refs;
- lifecycle;
- URLs;
- actions.

### MultiResultGallery

Fields:

- result grid;
- selected primary;
- publish selected;
- download all.

## 4. Prompt Library components

### PromptGrid

Layouts:

- masonry desktop;
- one-column mobile.

### PromptCard

Fields:

- preview;
- title;
- description;
- tags;
- likes;
- uses;
- author;
- status.

Actions:

- Use;
- Remix;
- Like;
- Share.

### PromptFilterBar

Controls:

- search;
- source tabs;
- tag chips;
- category select;
- model select.

### PromptDetailDrawer

Sections:

- preview;
- full prompt;
- metadata;
- stats;
- actions.

### AddPromptWizard

Steps:

- preview;
- prompt;
- meta;
- review;
- submitted.

## 5. Feed components

### FeedGrid

Filters:

- recent;
- top day;
- top all;
- my/public.

### FeedCard

Fields:

- media;
- author;
- model;
- prompt visibility;
- likes;
- remix count;
- shares.

Actions:

- Like;
- Share;
- Remix;
- Use reference.

### FeedDetailDrawer

Sections:

- media;
- author;
- model;
- prompt policy;
- remix chain.

## 6. Billing components

### BalanceCard

Fields:

- credits;
- pending payment;
- last update;
- refresh.

### PricePlanCard

Fields:

- credits;
- price;
- price per credit;
- badge;
- payment CTA.

### PaymentMethodCard

Fields:

- provider;
- availability;
- fee/notes;
- CTA.

### TransactionRow

Fields:

- date;
- provider;
- amount;
- credits;
- status.

## 7. Profile/referral components

### ProfileCard

Fields:

- Telegram username;
- masked tg id;
- balance;
- language;
- connected status.

### ReferralLinkBox

Fields:

- link;
- copy button;
- QR optional.

### ReferralStats

Fields:

- L1;
- L2;
- L3;
- available;
- pending.

### WithdrawalForm

Fields:

- amount;
- details;
- validation;
- submit.

## 8. Admin components

### ModerationBoard

Columns:

- pending;
- approved;
- rejected.

### ModerationPromptCard

Fields:

- preview;
- title;
- prompt excerpt;
- author;
- tags;
- model.

Actions:

- approve;
- reject;
- deactivate;
- open detail.
