# APIX Current Surface Inventory

Дата: 2026-08-09

Этот документ фиксирует текущие production-поверхности. Источник истины — ветка `main`; legacy/experimental UI не считаются production, если они не являются фактическим entrypoint.

## Frontend surfaces

| Surface | Runtime path | Canonical code | Status |
|---|---|---|---|
| Standalone Web | `/` | `landing/index.html`, `landing/js/riot-site.js`, `landing/css/riot-site.css` | Production web surface |
| Telegram Mini App | `/app` | `webapp/index.html` → `src/main.tsx` → `src/app/App.tsx` | Production Mini App |
| Mini App generation UI | `/app` generation tabs | `webapp/src/features/generation-screen.tsx` | Canonical capability renderer |
| Legacy Mini App | `/app?legacy=1` | `webapp/src/main.jsx` | Rollback/debug only; no new feature work |
| Static legacy site pages | `/account.html`, `/features.html`, `/guide.html`, `/contact.html` | `landing/*.html`, `landing/js/main.js` | Compatibility/static pages |

## Generation source of truth

Backend `ModelInfo` returned by `/api/v1/models/image`, `/api/v1/models/video` and `/api/v1/models/music` is the capability source of truth for UI controls.

The contract currently describes, where applicable:

- modes and media inputs;
- aspect ratios and mode-dependent aspect availability;
- quality/resolution variants;
- output counts and reference limits;
- video durations and per-second pricing;
- model-specific mode options;
- video input support and trim;
- Audio IDs / Character IDs / seed;
- flat, per-second, resolution and duration price tables.

A new provider capability must be added to backend metadata first. Consumer surfaces should render it from metadata rather than add independent hardcoded model forms.

## Telegram Mini App

Canonical application shell:

```text
webapp/index.html
  -> src/main.tsx
  -> src/app/App.tsx
```

`App.tsx` owns application state, generation submission, realtime updates and high-level navigation. `GenerationScreen` renders image/video/motion controls from `ModelInfo` and submits a `GenerationDraft` through the app-level API client.

The legacy `src/main.jsx` surface is intentionally isolated behind `?legacy=1`. It may be used for rollback/debugging, but it is not a product architecture source of truth.

## Standalone Web

Primary SPA routes remain implemented by `landing/js/riot-site.js`, including home, studio, prompts, feed, works, billing and profile.

Standalone Web uses `/api/web/*` for web-authenticated adapters and compatible generation routes. Web generation must preserve the same model capability and payload semantics as the Mini App even when desktop layout differs.

## Generation API

Primary model/generation endpoints:

```text
GET  /api/v1/models/image
GET  /api/v1/models/video
GET  /api/v1/models/music
POST /api/v1/generate/image
POST /api/v1/generate/video
POST /api/v1/generate/music
GET  /api/v1/generations/{id}
GET  /api/v1/ws/generations
```

Web adapters in `api/web/` reuse Mini App generation handlers rather than maintaining a second generation backend.

## Realtime and result lifecycle

Generation lifecycle is represented as queued/pending → processing/running → done/completed or failed. Realtime WebSocket updates are preferred, with polling/reconciliation as fallback. UI must show human-readable status and must not fabricate percentage progress that providers do not supply.

## Verification baseline

Before production merge of generation UI changes:

```bash
cd artflow
python -m compileall api db main.py
pytest -q

cd webapp
npm ci
npm run build

cd ..
node --check landing/js/riot-site.js
```

Additional contract tests should assert that active backend capabilities have a representable UI/payload path on every supported surface.
