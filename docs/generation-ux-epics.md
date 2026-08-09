# Generation UX parity — implementation record

Branch: `agent/generation-ux-parity`  
Parent epic: #76

## #77 — P0 Mini App advanced video parity

Status: implemented on the production-derived branch.

- canonical TypeScript `GenerationScreen` renders image/video/motion from backend capabilities;
- Gemini Omni exposes text/image/video modes, source video + trim, Audio ID, Character IDs and seed;
- client validation covers required media, model ref limits, seed range, 10-second video trim and Gemini media-slot quota;
- pricing uses `quality_prices`, `price_table`, `video_input_prices` and per-second metadata;
- Motion Control requires both character image and motion video;
- backend compatibility normalization preserves both Motion Control media inputs for the Kling provider contract.

## #78 — P0/P1 Canonical capability renderer

Status: implemented.

Canonical Mini App path:

```text
artflow/webapp/index.html
  -> src/main.tsx
  -> src/app/App.tsx
  -> src/features/generation-screen.tsx
```

Decisions:

- backend `ModelInfo` is the UI capability source of truth;
- one `GenerationScreen` renders image, video and motion variants with progressive disclosure;
- media inputs, pricing and validation are capability-driven;
- `src/main.jsx` is legacy-only behind `?legacy=1` and receives no new generation work;
- the old V4 production document is archived and current surface inventory names the TypeScript surface explicitly.

Trend execution remains intentionally locked to its backend-curated recipe: users upload the required input and do not override model/provider settings. This avoids a second independent trend parameter form and keeps the trend contract server-owned.

## #79 — P1 Standalone Web parity

Implementation target:

- multi-reference images;
- advanced video inputs (`video_start`, `video_end`, Audio IDs, Character IDs, seed, model mode);
- music model/title/style/voice fields and voice lifecycle;
- capability-driven controls from the same model metadata;
- consistent status/result actions.

## #80 — P1/P2 Result and accessibility

Implementation target:

- queued / processing / done / failed states;
- result detail and continuation actions;
- Telegram `BackButton` for nested surfaces;
- keyboard/focus/dialog accessibility;
- controlled guest/offline states.

## Guardrails

- No backend generation rewrite.
- No new independent Studio implementation.
- Progressive disclosure remains the default UX.
- Rare model-specific controls appear only when capability metadata requires them.
- `main` remains untouched until the branch is reviewed and merged.
