# CODEX MASTER TASK — APIX Prompt Riot Full Detail Implementation

Work in repository `Bambale0/lena_bot`.

Primary zones:

```text
landing/
api/web/
api/realtime.py
api/miniapp_routes.py only when shared generation API needs compatible extension
```

Do not modify Telegram bot flows unless a task explicitly requires it.

## Read first

- `docs/APIX_PROMPT_RIOT_MASTER_SPEC.md`
- `docs/SCREEN_BY_SCREEN_SPEC.md`
- `docs/FEATURE_MATRIX.md`
- `docs/COMPONENT_INVENTORY.md`
- `docs/API_STATE_CONTRACT.md`

## Mission

Implement a detailed standalone web-studio for APIX using existing backend contracts.

The web product must support:

- public landing;
- Telegram auth;
- Studio image/video/music flow;
- review before generation;
- realtime queue;
- result cards;
- result detail drawer;
- multi-result gallery;
- feed;
- prompt library;
- prompt submit;
- works/history;
- billing;
- profile/referrals;
- admin moderation if admin endpoints exist.

## Implementation phase 1 — Inventory and safety

1. Map existing routes in `landing/js/riot-site.js`.
2. Map existing endpoints in `api/web/` and `/api/v1/*`.
3. Confirm `/api/web/health`.
4. Confirm `/` is current SPA.
5. Confirm `/api/v1/ws/generations`.
6. Identify broken media URL behavior.
7. Do not change UI yet.

Output:

- `docs/current_surface_inventory.md`

## Implementation phase 2 — UX shell

Add or update:

- route registry;
- app state;
- safe render wrapper;
- drawer manager;
- toast manager;
- empty states;
- skeleton states.

Quality gate:

```bash
node --check landing/js/riot-site.js
```

## Implementation phase 3 — Studio flow

Implement flow:

```text
mode -> idea -> media -> model -> settings -> review -> run
```

Required:

- inline field errors;
- disabled run;
- review panel;
- model/cost before run;
- mobile layout.

## Implementation phase 4 — Queue/realtime

Implement:

- WebSocket first auth message;
- snapshot handling;
- done/failed handling;
- no reconnect storm;
- polling fallback;
- one toast per result.

## Implementation phase 5 — Result experience

Implement:

- unified result card;
- detail drawer;
- image actions;
- video actions;
- music actions;
- multi-result gallery;
- broken media fallback.

## Implementation phase 6 — Feed/prompts growth loop

Implement:

- feed filters;
- feed detail drawer;
- prompt library filters;
- prompt detail drawer;
- use prompt -> studio prefill;
- remix -> studio prefill;
- double-click protection.

## Implementation phase 7 — Billing/profile/referrals

Implement:

- balance;
- plans;
- payment methods only when enabled;
- payment pending/paid/failed/refunded states;
- profile identity;
- referral link copy fallback;
- withdrawal validation.

## Implementation phase 8 — SEO and QA

Implement:

- public FAQ;
- OG/Twitter meta with absolute URLs;
- sitemap/robots if routes finalized;
- Playwright smoke if tooling exists;
- accessibility checklist.

## Checks

Run:

```bash
node --check landing/js/riot-site.js
python -m compileall api db main.py
tools/codex_static_checks.sh || true
```

If Playwright is available:

```bash
npx playwright test
```

## Final response

Return:

- files changed;
- routes/endpoints affected;
- user flows completed;
- tests/checks run;
- blockers;
- next tasks.
