# Generation UX parity — implementation plan

Branch: `agent/generation-ux-parity`
Parent epic: #76

## #77 — P0 Mini App advanced video parity

- Gemini Omni: text/image/video modes
- video source + trim controls
- Audio IDs / Character IDs / seed
- Motion Control discovery and scenario
- exact variant pricing
- inline validation

## #78 — P0/P1 Canonical capability renderer

- backend `ModelInfo` is the UI source of truth
- one capability renderer for model controls
- reusable media input slots
- reuse controls in Trends admin
- remove stale frontend source-of-truth claims

## #79 — P1 Standalone Web parity

- multi-reference images
- advanced video inputs
- Music parity with Mini App
- same status/result actions

## #80 — P1/P2 Result and accessibility

- queued / processing / done / failed states
- result detail and chaining
- Telegram BackButton
- keyboard/focus/dialog accessibility
- controlled guest/offline states

## Implementation order

1. Land shared pure capability helpers.
2. Wire Mini App Studio to helpers and expose advanced video controls.
3. Add payload/validation regression coverage.
4. Migrate Trends controls.
5. Reuse the contract in standalone Web.
6. Finish result/navigation/accessibility polish.

## Guardrails

- No backend generation rewrite.
- No new independent Studio implementation.
- Progressive disclosure remains the default UX.
- Rare model-specific controls live under Advanced or appear only when capability metadata requires them.
