# Owned media identity and renewal — implementation plan

> **For agentic workers:** use repository `.clinerules/skills/executing-plans` and `test-driven-development`. Execute one reviewed tracer bullet per PR; do not implement schema, secrets or rollout during E01.4.2.

**Goal:** Give each ordinary Mini App upload a durable user-owned identity so its access URL can be checked/renewed without transferring another user's rights or losing draft input.
**Architecture:** Add a server-owned media registry and scoped resolver behind existing authentication. Keep legacy URL-only flows during expand/dual-write/dual-read, with no automatic historic ownership backfill. New private object delivery and retention require a later scoped rollout.
**Tech stack:** FastAPI, SQLAlchemy/Alembic/PostgreSQL, Python pytest, React/TypeScript, Playwright, GitHub Actions.
**Spec:** `artflow/docs/ux2/E01-4-2.md`; `artflow/docs/adr/ADR-UX2-001-owned-media.md`.
**Baseline:** `ef9b7ac4036dc6f649c333a9a8d6fb78d60cc01b`, Oct 10 2026.

## Global constraints

- Keep `main` protected; one isolated branch and one PR per independently verifiable slice.
- Existing `POST /api/web/upload-media` must work unchanged for all clients throughout expansion.
- No owner assignment from raw URL, SHA, local ID, signed `apixasset` receipt, filename or historic input_param reference.
- Parent #226 remains open until end-to-end renewal/retention is verified.
- No new business limits, provider prices, signing keys or TTL hardcoded into UI or code. Dedicated media secrets live outside database admin settings.
- Physical blob revocation and Cloudflare public-cache invalidation are separate problems; never promise one through a DB row.
- Frontend local material IDs/order/included/prompt survive refresh and owner changes must be guarded.
- Every task: RED → GREEN → source freeze → focused pytest+unit+Playwright → maintained 148 smoke/300 journeys where relevant → code review → exact-head CI → auto-merge → exact-merge deploy health/assets/startup.
- No live paid vendor task, irreversible prod migration, manual SQL, deletion or CDN mutation without separately approved operation and rollback.

---

## Task A — Accepted architecture and risk map (current #232; documentation only)

**Files:** `docs/adr/ADR-UX2-001-owned-media.md`, `docs/ux2/E01-4-2.md`, `docs/agents/UX2_E01_4_2.md`, this plan and UX2 README.
**Consumes:** current `api/trend_assets.py` receipt mechanics, `api/public_files.py`, `db/models.py`, `api/web/generations.py`.
**Produces:** reviewed data/authorization contract, explicit migration gate, failures/edge cases and vertical ticket boundaries.

- [x] Examine live main source/permissions, schema history, owner links, upload and public paths.
- [x] Compare generation lineage / signed receipt / owned-asset registry; choose with constraints.
- [x] Specify candidate model, GET/resolve semantics, ownership checks, state transitions, idempotency, SSRF and privacy.
- [x] Specify test names and migration/rollback design without promising deployed behavior.
- [ ] Verify docs and existing baseline tests; review standards + spec.
- [ ] PR/CI and issue state: contract accepted via review, no deployment behavior claimed.

**Acceptance:** no proposed API presented as existing; no secret values or user media; all #232 acceptance rows trace to ADR and test plan; no runtime source/migration diff.

## Task B — Expand schema and owner-scoped repository (separate, gated)

**Planned files:** `db/models.py`, new `db/migrations/versions/<next>_media_assets.py` (number/version must be selected against current head), new `db/media_assets.py` repository module, `tests/test_media_assets_repository.py`.
**Consumes:** ADR proposal. **Produces:** owner-bound `MediaAsset` CRUD/lookup and auditable state transitions. No HTTP endpoint/public URL yet.

- [ ] Obtain explicit migration authorization and confirm Alembic heads, Postgres version, backup/restore plan.
- [ ] Write RED integration tests: owner/foreign/unknown IDs, duplicate bytes, missing rows, revocation and version race. On baseline missing module/field tests must fail for the stated reason.
- [ ] Implement additive table constraints/indexes and repository owner predicate in a transaction; never accept caller-selected owner.
- [ ] Build separate physical storage key policy; do NOT change or delete legacy files.
- [ ] Add optimistic revision CAS, tombstones and idempotent state mutation; test concurrent commits/retries.
- [ ] Migration up/down against snapshot and rollback dry-run; ensure old production code is compatible with expanded DB.
- [ ] CI+review before toggling any feature.

**Gate:** 0 cross-tenant disclosures; 0 legacy upload changes; no production migration without exact approval.

## Task C — Controlled dual-write upload with reconciliation

**Planned files:** `api/web/generations.py` upload service extraction, `api/public_files.py` new opt-in private writer or adapter, `core/config.py` typed feature policy, `tests/test_ux2_upload_policy.py` and new upload transaction tests.
**Consumes:** B's registry. **Produces:** admin-cohort `asset_id` and legacy URL acknowledgement with recoverable failures.

- [ ] RED authenticated upload returns no owner asset identity today.
- [ ] Upload bytes validated by current rules, create unique logical owner record, and write under an opaque per-asset key atomically as far as filesystem+DB allow.
- [ ] Never respond with an asset ID before durable bytes/owner row. Reconcile commit/rename orphans and missing file records after crash.
- [ ] Keep response `url/kind/content_type/size`, add optional nested `asset` only when enabled; unknown clients unaffected.
- [ ] Compare same SHA under two users; each has independent row and deletion lifetime.
- [ ] Metrics: upload/write/commit/orphan reason and times, no raw URL/bytes/filename.
- [ ] Smoke auth/multipart/malformed, retries, concurrent upload, storage full, DB outage; check both clients.

**Gate:** legacy upload parity, no duplicate/incorrect charges (upload itself unbilled), no new public visibility.

## Task D — Owner-aware lookup and finite access link resolution

**Planned files:** new `api/web/media_assets.py` router/service, `db/media_assets.py`, `tests/test_web_media_asset_resolve.py`, configuration tests, API docs.
**Consumes:** B/C. **Produces:** authorized lookup/resolve on new registered objects.

- [ ] RED `GET /api/web/media-assets/{id}` and `POST .../{id}/resolve` missing today.
- [ ] Add auth + owner-scoped lookup; test same-shape 404 for unknown/foreign and 401 for unauthenticated. No admin-preview bypass.
- [ ] Resolve only ready/owned/physically present, unrevoked objects; return state with finite link after a dedicated key and delivery policy are configured.
- [ ] Duplicate same request ID produces same authorization outcome; conflicting request body=409; version CAS defeats revoke/replace race.
- [ ] Disk unavailable ≠ deleted; rate/timeout configured and bounded; no billing or automatic generation.
- [ ] Reject arbitrary URL/filepath in resolve; no server-side external network on this API.
- [ ] Test key rotation and zero secret leakage in logs/responses; reject stale/forged receipts.
- [ ] Separate provider upload lease contract must be signed off before short URL is used for paid tasks.

**Gate:** endpoint available for proven new objects only; old URL cannot be adopted.

## Task E — Drafts and multi-device UX

**Planned files:** `webapp/src/lib/types.ts`, `draft-storage.ts`, `reference-selection.ts`, `App.tsx`, `reference-availability.tsx` plus focused unit/browser tests.
**Consumes:** D. **Produces:** owner-backed explicit refresh preserving current material semantics.

- [ ] RED: expiring URL with valid asset identity leaves user with failed preview; no safe refresh.
- [ ] Extend canonical material with optional server `assetId/revision` (keep local `id` stable). No secret or URL-signature persistence.
- [ ] Existing V1/V2/V3 drafts stay unowned; never infer assetId from URL or SHA. Supported rows restore across same-owner sessions; cross-device sync only after real backend draft ownership API.
- [ ] Explicit refresh per item, optimistic UI generation guard; out-of-order/duplicate network responses ignored by owner/draft/material/operation/revision.
- [ ] Preserve inclusion, order, prompt and uploaded other assets; prompt never sent to media lookup.
- [ ] Implement user-visible missing/unknown/forbidden/temporary; safe retry/replace/exclude/delete.
- [ ] Test 320/375/390/430/mobile keyboard, accessibility, light/dark and real Telegram WebView later.
- [ ] Confirm frontend cannot self-award access by editing sessionStorage.

**Gate:** exact media payload only from verified included owned items; no hidden author or legacy leaks.

## Task F — Generation ingestion leases, cleanup and private-media pilot

**Planned files:** repository use relation (if approved), generation adapters, retention/reconciliation service, runtime config and deployment docs.
**Consumes:** B–E. **Produces:** safe medium-lived media availability through asynchronous vendor ingestion, revocation and deterministic cleanup.

- [ ] RED: a provider fetching after signed URL expiry cannot retrieve photo; generation must not charge and silently hang.
- [ ] Gather measured provider fetch latencies and result TTL; derive configurable lease/handoff semantics per adapter.
- [ ] Tie generation task ID to owner asset under transaction; pin while pending/reconciling and reconcile late/duplicate webhook releases.
- [ ] Separate cache policy for private URLs, verify effective Cloudflare origin config (documentation is not live evidence).
- [ ] Test revoke while in-flight, provider outage, reissued URL, queue retry, cleanup crash, duplicate scheduled delete.
- [ ] Shadow metrics and opt-in pilot before broad release. 24h monitoring/alerts and tested rollback.
- [ ] Only after access contracts are satisfied consider historic migration or public URL deprecation as explicit operations.

**Gate:** no unauthorized fetch, broken delivery, billing drift or orphaned storage; no change to normal users until tested.

## Verification template for every PR

1. `git diff --check`, secret/path scan, updated AGENTS/local ADR and exact commit pin.
2. Run scoped tests first; do not alter old assertions merely to pass. Record explicit RED failure and GREEN result.
3. Build/typecheck and maintained python/frontend checks. Capture actual Playwright screenshots and review instead of using generated mockups.
4. Rebase or merge latest main only after frozen-tree suites; run exact-head GitHub Actions.
5. Native GitHub PR auto-merge only after review/readiness; no direct main push.
6. Verify main-push CI and Production Autodeploy on **merge SHA**, public health, app, JS/CSS SHA and bounded startup logs; report existing unrelated warnings.
7. Update only the completed child issue; parent stays open until its own functional acceptance.

## Decisions still requiring external proof before Task B/F

- Database backup/restore and migration approval.
- Actual effective CDN caching, new private-origin path and media secret storage/rotation.
- Provider URL access method and measurable asynchronous retrieval delay.
- Storage retention policy (ordinary miniapp uploads are not feed generation media).
- Whether cross-device draft sync and user deletion rights are in the same product-release batch.
- Operational thresholds/config owners for TTL, rate limiting, and reconciliation.

The plan intentionally prefers blocked tasks with explicit evidence over guessing values.
