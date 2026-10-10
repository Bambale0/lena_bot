# ADR-UX2-001: Owned media identity and URL renewal

**Status:** Proposed for APIX architecture review; no runtime or schema change in this ADR.
**Date:** 2026-10-10
**Issue:** #232 (E01.4.2), parent #226, epic #210, program #209.
**Verified source baseline:** `ef9b7ac4036dc6f649c333a9a8d6fb78d60cc01b`.
**Scope:** Ordinary user-authored Mini App photos. No silent conversion of hidden trend-author references, Pinterest assets, Telegram file IDs or existing public files to private objects.

## 1. Problem and security invariant

An upload URL is a **location**, not durable media identity or ownership evidence. Today the ordinary Mini App receives only `url/kind/content_type/size`. In contrast, Trends/Pinterest use short-lived user-bound signed receipts. Neither mechanism answers: who can refresh a changed URL tomorrow; has the object been revoked; does it still exist; can the user reuse it on another device? The E01.4.1 checker proves only existence of some configured public local paths; it does not establish ownership or vendor reachability.

**Invariant:** Every privileged lookup, renewal, export, delete and generation use MUST authorize the authenticated user against server-owned media identity (or a separately proven, server-owned generation lineage). Knowledge of a URL, SHA prefix, frontend local ID, signed receipt, Telegram file ID, or returned preview is insufficient.

**Physical reality:** revoking a database record does not revoke a previously shared public URL or an immutable CDN cache entry. Strong confidentiality/revocation for *new* media requires a separate private-object delivery path and CDN rules. Existing public media retain their current semantics until an independently verified migration.

## 2. Audited current implementation (not proposed fields)

| Evidence | Current fact | Consequence |
|---|---|---|
| `api/web/generations.py` `_save_uploaded_generation_media` | Authenticated upload writes via `save_public_file(..., subdir="miniapp")` and returns URL/type/bytes; no asset ID/owner record | Upload acknowledgement cannot support durable owner-scoped resolve |
| `api/public_files.py` `save_public_file` | File name defaults to the first 32 hex chars of SHA-256 with `unique=False` | Equal file bytes can map to the same physical path across users; path/hash is not identity |
| `api/reference_availability.py` | Admin-only existing-public-file check returns state; external URLs return unknown | Cannot reuse existence as authorization |
| `api/trend_assets.py` | `apixasset` is HMAC over base64 JSON including `uid/url/kind/iat`; 24h fixed token TTL; verification checks user, kind, signature and age | A time-limited receipt can authenticate an upload action, not grant durable refresh/revocation. Base64 is not encryption; no dedicated revocation registry |
| `api/trends_routes.py` and `api/pinterest_service_routes.py` | Separate upload endpoints issue signed receipts for their own generation flows | Keep them backwards compatible; do not conflate with ordinary Mini App |
| `db/models.py` | `Generation.user_id` and `ImageSession.user_id` exist. No `MediaAsset`/upload ownership table | Own Generation row MAY establish lineage for a generated result; not for arbitrary reference uploads |
| `db/models.py` | `ImageSession.reference_file_ids/reference_urls` and `Generation.input_params/result_urls` are stored text | Historic references are not guaranteed to be user-owned media |
| `docs/media_cdn_setup.md` | Proposed media CDN uses long-lived immutable public caching and legacy public URL compatibility | Even removal at origin cannot guarantee instant CDN revocation |
| `scripts/artflow_feed_retention.py` | Feed-only retention logic handles published generation media, with other-reference checks | Not a general ordinary-upload retention promise |
| `core/config.py` | Has storage root/public path settings; no dedicated owner-registry/asset-signing configuration was identified in this audit | New signing key or TTL must be introduced separately, with secure configuration and operator controls |

Verification limits: source inspection is authoritative for code behavior, not evidence that the *documented* CDN cache rule is enabled in Cloudflare or that historical uploads still exist on disk. No secret values, private database rows or customer files were read.

## 3. Options considered

### A. Reuse existing Generation/ImageSession rows as the only registry — rejected for uploads
Good: known user FK, no new table, usable for own finished generation outputs with additional provenance checks.
Fails: an ordinary upload exists before any Generation; an unlaunched draft has no generation row; historical image-session reference URL could have been third-party/author-supplied; one file may be uploaded multiple times. Cannot grant a file solely because its string is present in input_params or a session. Retain Generation lineage only as an *explicitly audited adoption path*.

### B. Extend `apixasset` signed receipts into long-lived IDs — rejected as source of truth
Good: existing owner-bound HMAC and upload flow, easy no-migration pilot and immediate validation of token age.
Fails: no object state, revoke, deletion metadata, stable device-independent identity, ownership transfer or lease tracking; 24h expiration prevents durable drafts. Existing secret fallback (webhook secret → KIE webhook secret → bot token) is not an independent media key. Payload contains URL in readable base64. Key rotation invalidates old receipts. Use only for bounded compatibility/handshake; never renew rights based solely on a legacy receipt or URL.

### C. Separate owned-media registry — **selected**
Store one durable opaque media ID and one explicit owner-state row for each *logical upload*. Keep opaque storage key, mutable link issuance and optional content hash separate. Evolve consumers through expand/dual-read/canary/contract without changing existing endpoints first. This supports revocation, auditing, cross-device lookup, proper retention and eventual private delivery.

Chosen tradeoff: database migration and reconciliation work are required later; they are **not authorized or executed by this ADR**.

## 4. Proposed resource contract (ALL identifiers/columns below are proposals)

A proposed `media_assets` record:

| Proposed field | Meaning/invariant |
|---|---|
| `id` UUIDv4/opaque random identifier | Stable public reference; not SHA, storage path or sequential business ID |
| `owner_user_id` FK to `users.id` | Principal authorized via existing authenticated web user; never client-supplied |
| `source` enum: `user_upload` / `adopted_generation` | Proven lineage, not inferred from a URL |
| `source_generation_id` nullable FK | Set only after verifying generation belongs to same owner and the result is an approved own asset |
| `kind` and `content_type` | Validated media class and detected MIME |
| `size_bytes`, `content_sha256` | Server-verified integrity/size; hash must never function as authorization or be exposed to telemetry |
| `storage_backend`, `storage_key` | Internal location; no absolute filesystem path in API, logs or browser |
| `state` | `pending` → `ready` → (`revoked` / `missing` / `deletion_pending`) → `deleted`; no reverse resurrection |
| `revision` positive monotonic integer | Compare-and-set for replacement/revoke/resolve; avoids stale response applying to new material |
| `created_at`, `updated_at`, `revoked_at`, `deleted_at` | Audit and retention; no assumed TTL |

Indexes proposed: primary key `id`, (`owner_user_id`, `created_at`), (`state`, `updated_at`). Strong FK and bounds/allowed MIME validation. Sensitive `storage_key` excluded from all public serializers. `content_sha256` is not a cross-user lookup key in this first slice. An optional future `media_asset_generation_uses` relation (asset ID, generation ID, purpose, stage) would pin objects during asynchronous provider work; do not fabricate implicit ref-counts.

**Isolation:** one logical upload per row, even when bytes are identical. New registered uploads must not use a shared, content-addressed *writable/deletable* path without separate blob lifetime management; prefer per-asset random opaque object keys. Keep legacy content-addressed files untouched.

**Auth:** use `get_web_user_or_none` or the equivalent existing authenticated identity; validate `is_banned`; make owner equality/explicit ACL check in the server repository lookup. Public admin-preview capability is unrelated to asset ownership. Admin support privileges, public-feed publication or a trend-author relationship cannot silently transfer media ownership.

## 5. Proposed operations and response semantics (NOT existing routes)

### Upload acknowledgement (expand-only)
Keep `POST /api/web/upload-media` request and legacy `url/kind/content_type/size` response unchanged. In a future version/flag, optionally add:
`data.asset = { id: "<opaque>", revision: 1 }`.
Persist registry row only after bytes exist and are validated. If registry write fails, **do not return a durable asset ID**; reconcile orphaned bytes. Old clients continue using the legacy URL until their separate migration.

### Lookup
`GET /api/web/media-assets/{asset_id}` returns owner-authorized *metadata only*: `id/kind/state/revision/size_bytes`; no raw key, signed URL, previous URL or filename. Unknown/foreign IDs return indistinguishable 404 to prevent enumeration; errors are audited internally with reason codes.

### Resolve / refresh
`POST /api/web/media-assets/{asset_id}/resolve` request:
`{ "purpose": "preview|generation", "expected_revision": 3, "request_id": "<uuid>" }`.
The server authenticates, checks owner, state, size/hash if required, object existence and backend health **before** it mints any access URL. Only a successful owner-scoped response may contain `url`, `expires_at`, `asset_id`, `revision` and provider-compatible media metadata. Metadata lookup may report `refreshable` (owner verified and object exists, old access link expired); resolve then returns a renewed *access capability*, not a new right.

Repeated identical `request_id` for the same actor/asset/version/purpose must be safe and must not create additional objects, charges or privilege. Idempotency may reuse a previously issued response only while owner entitlement, row revision, revocation state and access-link validity remain unchanged; revocation always wins over replay. Conflict in request body under the same key is 409. Concurrent replacement/revocation increments `revision`; stale expected revisions yield 409, and delayed frontend responses are ignored based on (owner, draft kind, local material ID, revision, operation ID). Never change `included`, list order or prompt during a URL refresh.

No generation is started by lookup or resolve; generation initiation is a separate authorized/billable boundary. Provider fetch timing must be accounted for; issuing a URL which expires before the provider downloads media is NOT success.

### Revocation and deletion
A future authenticated revoke marks the row non-resolvable immediately and creates an audited tombstone. Physical delete is deferred until server-proven in-flight uses are released. Revocation cannot remove a previously cached *public legacy URL* from external clients; do not advertise it as such. Deletion/failed object lookup must never be interpreted as a reason to create a replacement on behalf of an unauthorized actor.

### Failures (externally observable)
- 401: no authenticated user.
- 404: unknown ID / foreign owner (no existence oracle).
- 409: stale revision, duplicate request-key mismatch or state conflict.
- 410: known-to-owner permanently deleted item (only after authorization); avoid confirming foreign objects.
- 422: malformed identity/purpose/unsupported media.
- 429: configured rate/concurrency limit.
- 503: temporary store/signing service issue; bounded retry/backoff, never charge.
Success payload status: `available` or `refreshable` (as appropriate to lookup), `missing` for own deleted bytes without terminal tombstone, `forbidden` only after owner auth where meaningful, `unknown` for unproven legacy sources, `temporary_error` for transient network/storage failures. Do not persist transient `available` as permanent launch permission.

## 6. Threat model, failure and concurrency handling

1. **IDOR:** foreign user guesses asset UUID or submits someone else's `asset_id`: lookup/resolve/revoke return the same 404 as unknown ID.
2. **Forged/expired receipt:** legacy `apixasset` cannot be exchanged for a durable record solely by decoding or verifying it; any adoption must prove authoritative server lineage.
3. **Same bytes, different user:** distinct registry ownership and independently managed deletion; dedupe is a future blob-layer concern.
4. **Hidden author references:** trend-author files/prompts cannot be adopted into the remixing user's registry. They remain server-controlled, with no client URL leakage.
5. **Revoked access:** a previously issued URL may stay public/cached in the legacy path; new private delivery only may provide enforceable revocation.
6. **TOCTOU:** check→provider fetch race. Future generation uses should pin the object/lease until provider ingestion, with idempotent reconciliation on lost webhook/outage. File-existence check alone does not solve this.
7. **Race:** two refreshes and replacement, deletion, owner switch, delayed AJAX. All compare `revision` and UI operation identity; late responses cannot resurrect old refs.
8. **SSRF:** never network-fetch arbitrary user URLs on this route. Any future external importer requires DNS/IP validation including redirect/rebinding/pinned socket, no private/link-local/metadata addresses, body/timeout caps and no forwarded Telegram auth headers.
9. **Signed-link leakage:** URL and signature never logged or sent to analytics. Avoid long-lived cache headers on private access responses. Ensure no query-referrer leakage; URL purpose narrowly scoped.
10. **Secret management:** separate versioned media-signing credential stored as a secret (not pricing/admin config), with key rotation/grace contract. Do not piggyback permanently on `BOT_TOKEN` or webhook credentials.

## 7. Configuration, CDN and provider boundary

Current `STATIC_UPLOAD_*` settings describe *public* mount/base URLs only. Do not overload them with private signing or TTL semantics. A future typed control plane must validate retention/TTL, maximum asset bytes/count/age, active-generation lease period, rate limits and supported private delivery backends. Sensitive signing keys remain in managed secret storage; audit a key identifier, never the key. No TTL is introduced in source in this ADR.

Future provider adapters must obtain a scoped URL from the media service and decide whether that vendor accepts auth-less, time-limited HTTPS URLs, whether redirects work, and how long ingestion may be delayed. Provider and Telegram consumers should share the asset identity/authorization service, **not** the raw-media HTML UX. Support rollback to legacy URL-only behavior while the feature remains disabled.

The repository's `docs/media_cdn_setup.md` describes immutable 1-year caching for public paths. This is a **documented rollout design**, not independently verified live Cloudflare configuration. A private delivery path must not inherit that cache policy.

## 8. Migration and rollback (future, separately approved)

1. **Expand migration (new ticket):** add table/index/constraints behind additive Alembic revision. No old column deleted; run schema test on empty and populated snapshot. Exact migration and backout need independent approval.
2. **Dual-write gated upload:** for a small consenting admin cohort, atomically allocate random storage key, write validated bytes, create owner row, return optional `asset` while preserving old response. Failure reconciliation cleans only proven orphaned new files.
3. **Dual-read UI:** prefer asset ID only when provided; old URL-only drafts stay functional under legacy rules. Store local stable material ID, owner, asset ID, revision, inclusion separately; never auto-grant ownership on reload.
4. **Own-generation adoption:** optional explicit API may import a completed result only if `Generation.user_id` matches and the selected result belongs to that task. Never bulk-link historic `input_params`/`reference_urls` by string matching.
5. **Private origin canary:** verify provider ingestion and Telegram delivery, cache-control, URL renewal, replay/race, revocation and cleanup with test/production-like data before moving any real user media. Public legacy links remain public; no silent privacy claim.
6. **Retain/reconcile:** task-reference leases, deletion tombstones, duplicate job-safe background cleanup, metrics for orphaned rows/files, dry-run reconciliation, alert on unexpected missing bytes.
7. **Contract later:** remove legacy fallback only after all clients and reference flows have migrated and the documented rollback horizon has passed.

**Rollback:** disable new asset issuance/resolve and route new requests through proven legacy flow; retain registry rows and private files, never drop or repurpose data as an emergency rollback. Once private-only objects exist, old clients cannot safely consume them by switching flags alone: maintain compatible read bridge until migration complete. Destructive cleanup and DB downgrade require separate approval and backup verification.

## 9. Acceptance matrix / test seams

Primary seam: server owner-scoped `MediaAssetRepository.resolve_for_actor` (proposed name, not currently present). HTTP contract tests use existing authentication overrides; frontend uses `referenceMaterials`/`draft-storage` with local material IDs, and a single request wrapper. Future tests MUST verify the real DB authorization predicate and **not just UI hiding**.

| Test | Expected |
|---|---|
| New own ready object | Lookup and resolve available; a new access URL is minted only after owner check |
| Unknown/other-owner ID | Indistinguishable 404; no URL/path leak |
| Same-byte uploads by two owners | Distinct asset identities; one revoke cannot remove the other's bytes |
| Unsubmitted draft | Upload still owned and resolvable; no Generation row required |
| Expired URL, valid object/owner | Refreshable then new URL; keeps stable ID/revision |
| Expired signed receipt alone | Cannot create/extend durable rights |
| Physically missing own file | Missing, no billing or fake replacement; prompt/order preserved |
| Revoked/deleted object | Resolve fails; no automatic ownership reassignment |
| Two concurrent refreshes, replay request | Idempotent response, no duplicate writes/charges |
| Replace/delete/owner-switch mid-flight | Ignore stale response; no generation POST |
| Unauthorized provider/result claim | Reject unless own generation lineage proven |
| Malicious external URL/redirect/private DNS | No server fetch in this phase |
| Signed link in logs/referrer/cache | Must not appear; private response cache disabled |
| Database/storage outage | Temporary error; safe retry, no charged generation |
| Provider ingestion delayed past URL expiry | Correctly surface/retry ingestion with lease; no silent loss |
| Legacy no-ID draft | Continues old explicit behavior, not silently upgraded |
| Admin preview vs ordinary account | Auth required, server flag only gates UX; ownership always enforced |

Future tests are **specified**, not passing code at the time of this ADR. In the implementation tickets: write RED at the HTTP/DB seam, then code, then full smoke, Playwright, financial/privacy regressions and exact-SHA CI.

## 10. Observability and scope impact

Structured, bounded events: `actor_id` (authorized internal only), `asset_id`, `operation`, `asset_revision`, `storage_backend` (enum), `status/reason_code`, `latency_ms`, `request_id`, retry count and failure stage. No filename, path, SHA, raw URL/query, prompt, hidden author input, auth token or secret. Audit change of owner/state; metrics for 401/404/409/503, expired accesses, orphaned objects, outstanding leases and failed provider fetches.

Parity: `mini_app` will gain visible owner-aware recovery later; `site` shares backend authorization and older clients via additive response; `telegram_bot` retains existing behavior until it consumes the new identity service via its own adapter. All three surfaces require parity/regression review at each implementation step. No tariff, credit ledger, provider routing, subscription or real user entitlement change in this document.

## 11. Decision gates

This ADR does **not** authorize:
- schema migration, backfill, deletion of legacy file, key rotation or modification of Cloudflare rules;
- granting old URL-only media a new owner;
- changing Trend/Pinterest receipt behavior;
- paid generation as a testing shortcut;
- enabling UX2 for non-admin users.

Before an implementation PR: confirm actual DB migration head/schema, owner-auth edge cases, object-store choice, private CDN cache configuration, supported provider URL ingestion window, retention policy and rollback; then implement through the reviewed tracer-bullet tickets. A design review is not a successful production delivery.
