# GPT Image 2 and 2.5 Neironych — 2026-11-04
Baseline: bfc52606c68c6b895d797e003e889d42a7ae691f (merged Pro primary #334).
User added GPT Image 2 and 2.5 to scope; explicitly selected initial 2.5 prices from current GPT Image 2 prices. Native /v1/models lists gpt-image-2 and gpt-image-2.5-sunburst. Upstream partner reference documents Images generations/edits, size and quality.
Existing GPT 2 has public T2I/I2I keys, Nexus reserve and price rows. GPT 2.5 is absent. Reuse typed catalog, shared launches, immutable snapshots, signed Nexus fallback and completion reconciliation. Preserve VIP GPT 2 separately.
Plan: red routing/model tests (observed), native adapter and DB controls, add 2.5 catalog/caps/labels and idempotent live-price bootstrap, all-surface authorization/billing/recovery tests, exact-head CI/review/release and live checks.
No schema changes; use existing routing/audit/models. 2.5 never substitutes GPT 2 on failure. Existing GPT 2 uses Nexus only for confirmed rejection or incompatible native parameters. Unknown acceptance never licenses fallback.
Matrix: provider contracts, models/caps, admin selection, no-overwrite seed, DB admission, authorization, all launch surfaces, signed callbacks, reconciliation, latency and deployment. Verification pending.

Progress: 51 GPT-focused tests pass, including all 15 surface/model launch combinations, HTTP generation/edit payloads, no duplicate billing/fallback, immutable replay/admission, admin authorization/audit, public site/Mini App catalogs, bootstrap prices and scheduler eligibility. Live GPT 2 and GPT 2.5 text returned 2048x1152 in 25.8s and 25.5s, request IDs 1f74c57f-b0ea-4669-8c1d-b6df33141c8b and 0c88b10c-6690-4f66-9b3e-470ae69b2a87. Full suite and 101-contract inventory passed before the final six tests; final check pending. No schema change; model price bootstrap is idempotent and does not overwrite existing prices. GPT 2.5 unavailable if no GPT 2 source price exists; no invented tariff. Rollback: set GPT 2 route to Nexus; disable GPT 2.5 through existing model admin availability.

Final local suite after all GPT tests: {'.': 4180, 's': 101}. Ruff passed. All 101 contracts valid. No known high-severity review finding; exact-head CI and deployed runtime verification pending.

Live edit checks also passed: GPT 2 32.2s (3bc3664c-19e4-41e7-9413-3a241d27c031), GPT 2.5 28.6s (d3d89162-0ad7-43f2-a863-525b8038952f), both decoded 2048x1152 images. No customer credit changes.

Final rejection-path review: GPT 2.5 has no same-model reserve; confirmed native not-accepted responses now settle immediately with task-guarded atomic refund across site/Mini App/bot/feed, rather than waiting for the unknown-outcome SLA. Five regressions reproduced pending-state behavior before the correction. Full local suite passes after correction (4185 passed, 101 skipped), Ruff clean. Ambiguous NeironychImageError still only reconciles; no speculative refund/fallback added.

Review corrections complete: GPT 2.5 is excluded from legacy square-4K downgrading; GPT 2 native contract links added beside Nexus reserve docs; GPT 2.5 live-smoke template now includes an image reference and exercises /edits. Regression tests failed before correction, pass after it. Final full suite: {'.': 4187, 's': 101}. Existing GPT 2 square 4K support comes from bot/keyboards bootstrap and remains intact.
