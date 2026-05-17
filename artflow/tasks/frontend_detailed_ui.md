# Codex Task — Frontend Detailed UI

## Scope

Work only in:

```text
landing/index.html
landing/js/riot-site.js
landing/css/riot-site.css
```

Do not touch Mini App `webapp/`.

## Implement

### 1. Router and state

- route registry;
- safe render wrapper;
- auth-aware routes;
- mobile detection;
- drawer manager;
- toast manager.

### 2. Screens

Implement or refine:

- home;
- auth;
- studio;
- prompts;
- prompt detail drawer;
- add prompt;
- feed;
- feed detail drawer;
- works;
- billing;
- profile;
- referrals;
- admin moderation.

### 3. Studio stepper

Implement:

```text
mode -> idea -> media -> model -> settings -> review -> run
```

### 4. Components

Implement reusable render functions:

- renderButton;
- renderStickerTab;
- renderEmptyState;
- renderSkeletonCard;
- renderPromptCard;
- renderFeedCard;
- renderResultCard;
- renderDrawer;
- renderQueueItem;
- renderPricePlanCard.

### 5. Mobile

Test widths:

- 360;
- 390;
- 768;
- desktop.

## Checks

```bash
node --check landing/js/riot-site.js
```

## Acceptance

- no horizontal scroll mobile;
- visible labels/errors;
- run disabled until valid;
- no card-in-card overload;
- app-mode is not marketing-heavy.
