# APIX V4 Production Mini App — archived

> [!IMPORTANT]
> This document is **historical**. It described the retired V4 production candidate and is no longer a deployment or implementation source of truth.

## Canonical production surface

As of August 2026 the production Mini App entrypoint is:

```text
artflow/webapp/index.html
  -> /src/main.tsx
  -> src/app/App.tsx
```

`src/main.jsx` is retained only behind `?legacy=1` for rollback/debugging. New feature work must not be added there.

Generation UI is implemented in:

```text
src/features/generation-screen.tsx
```

The UI is capability-driven from backend `ModelInfo` returned by:

```text
GET /api/v1/models/image
GET /api/v1/models/video
GET /api/v1/models/music
```

The backend model contract is the source of truth for modes, aspect ratios, quality, counts, durations, resolutions, reference limits, advanced video inputs, pricing and validation. A provider/model capability change must not require a parallel hardcoded V4 implementation.

## Current verification

Use the current production checks rather than the V4 marker checks in the archived document:

```bash
cd artflow/webapp
npm ci
npm run build

cd ..
pytest -q
```

For deployment and current surface ownership, see `docs/current_surface_inventory.md` and the production branch state in `main`.
