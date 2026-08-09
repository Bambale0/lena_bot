# Generation UX parity — implementation record

Branch: `agent/generation-ux-parity`  
Parent epic: #76

## #77 — P0 Mini App advanced video parity

Status: implemented and closed.

- canonical TypeScript `GenerationScreen` renders image/video/motion from backend capabilities;
- Gemini Omni exposes text/image/video modes, source video + trim, Audio ID, Character IDs and seed;
- client validation covers required media, model ref limits, seed range, 10-second video trim and Gemini media-slot quota;
- pricing uses `quality_prices`, `price_table`, `video_input_prices` and per-second metadata;
- Motion Control requires both character image and motion video;
- backend compatibility normalization preserves both Motion Control media inputs for the Kling provider contract.

## #78 — P0/P1 Canonical capability renderer

Status: implemented and closed.

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

Status: implemented and closed.

- production Studio remains `prototype-premium.js`; no second web Studio was introduced;
- `generation-parity.js` extends existing normalized `ModelInfo` data with advanced controls;
- multi-reference image behavior is retained;
- video requests gain trim, Audio IDs, Character IDs, seed, model modes, Motion Control validation and Gemini media-slot validation;
- existing exact quality/price-table/video-input/per-second pricing stays in the core web runtime;
- music requests now carry model/title/style/voice selection;
- Suno custom voices can be listed, created, refreshed and verified through the existing web adapters;
- `studio.html` loads the parity extension after the existing model-specific enhancers.

## #80 — P1/P2 Result and accessibility

Status: implemented and closed.

- generation status remains provider-state based (`queued/pending`, `processing/running`, `done`, `failed`) with realtime + polling fallback;
- existing result detail, download, publish, repeat/variant/animate actions are retained on production surfaces;
- native Telegram `BackButton` now closes an open sheet first and otherwise returns nested tabs to Feed;
- shared `Sheet` now sets initial focus, traps Tab/Shift+Tab, closes on Escape and restores previous focus;
- dialogs expose `aria-modal`, labelled title/description and accessible close controls;
- Mini App locked/error state continues to avoid invented balances/tasks/demo state;
- regression coverage added for BackButton wiring, dialog focus behavior, human status labels and controlled locked state.

## #82 — P1 Interaction performance / button latency

Status: implemented and closed.

Root causes found in the canonical Mini App:

- `visualViewport.scroll` caused AppShell viewport state work while the user scrolled;
- BackButton synchronization observed body-wide DOM/class mutations and used computed-style reads;
- H3, Seedance and Suno source-audio enhancer code was eagerly installed for every session, including broad MutationObservers and Seedance's periodic DOM scan;
- mobile glass surfaces used backdrop blur and relatively expensive shadow/filter effects during interaction.

Changes:

- navigation uses an optimistic local selected state and React `startTransition` for the heavier screen update;
- Telegram haptics are deferred outside the synchronous click task;
- viewport state is updated only when dimensions/classification actually change and no longer listens to visual-viewport scroll;
- BackButton synchronization is rAF-throttled and observes only nav aria state plus actual dialog additions/removals;
- advanced H3, Seedance and Suno source-audio enhancers are code-split and lazy-loaded when their model/surface is entered;
- mobile/coarse-pointer performance CSS disables backdrop blur, reduces layered shadows and shortens feed-card animation;
- the shared button component uses short color-only transitions rather than a broad transition;
- static regression coverage guards these interaction-performance decisions.

Verification on the performance head:

- APIX CI/CD: backend-quality passed;
- Mini App TypeScript/Vite production build passed;
- Playwright Mini App smoke: 24/24 passed;
- Provider Contract Compliance passed;
- main Mini App JS decreased from about 436.44 kB / 128.45 kB gzip to 417.60 kB / 123.42 kB gzip, while provider-specific enhancer code moved into lazy chunks.

## Guardrails

- No backend generation rewrite.
- No new independent Studio implementation.
- Progressive disclosure remains the default UX.
- Rare model-specific controls appear only when capability metadata requires them.
- Performance changes preserve model capabilities rather than deleting advanced features.
- `main` remains untouched until the branch is reviewed and merged.
