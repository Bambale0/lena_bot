# Nano Banana 2 — primary provider

Product key remains `nano-banana-2`; Nano Banana 2.1, Pro, prices and available
controls are unchanged. Site, Mini App, feed repeat and Telegram share this route.

## Routing

Neironych is primary for fixed ratios 1:1, 16:9, 9:16, 4:3 and 3:4 with up to
three HTTPS references. Existing APIX 2K/4K choices map to native 2k/4k.
Auto/unspecified framing, other existing ratios, four references and reference
formats outside this contract continue through Nexus with the original inputs.
A definitive no-work rejection can also fall back to Nexus. Network loss,
timeouts, malformed results and ambiguous errors never launch a second provider.

The database override is edited through Telegram admin → Banana 2 provider or
authenticated GET/PUT `/api/web/admin/provider-routing/nano-banana-2`. Changes
are audited. `NANO_BANANA_2_PRIMARY_PROVIDER=neironych|nexus` supplies the initial
default only. `NANO_BANANA_2_IMAGE_TIMEOUT_SECONDS=100` is limited to 110 seconds
and remains below the production proxy deadline.

## Native contract and recovery

Verified against the running Neironych registry and API on 4 November 2026:
`POST /v1/images/generations` for text, `/v1/images/edits` for references;
model `nano-banana-2`, n=1, resolution, aspect_ratio, response_format=b64_json,
and optional images=[{image_url:...}]. Raster bytes are decoded, checked and
stored by APIX before completion.

Before the paid POST, persist the generation UUID and immutable original body,
body hash, endpoint and credential-scope hash under a row lock. Admission is
single-use. Both Idempotency-Key and X-Client-Request-Id use that UUID.
Never rebuild a recovery request from mutable session settings.

After a timeout, read-only status lookup verifies the exact model. Only an
authenticated completed status without media permits replay of the exact saved
request and key in the same credential scope. The current Neironych implementation
permanently fences tenant/idempotency keys before provider work and retains the
original response transactionally. This reads cached bytes, with no new provider
attempt. Missing snapshots, changed scope/body, pending/unknown status and
expired responses fail closed. Completion/refund and delivery retain the
generation task guard and single-winner transition. The existing customer refund
SLA still applies when media cannot be recovered. This recovery is Nano Banana 2
specific; it does not change Seedream's legacy recovery.

Nexus fallback freezes its own submission before POST. Lost submit responses use
a signed callback plus canonical provider GET; they are never retried blindly.
When no shared KIE webhook secret is configured, the existing dedicated
KIE_WEBHOOK_HMAC_KEY signs the per-submission UUID. The signing key is never
included in callbacks or stored snapshots.

## Checks and rollback

Contract, fallback, snapshot, recovery, audit, authorization and all launch
surfaces: `tests/test_nano_banana2_neironych.py`.
Existing Nexus and shared image tests remain in force. Change the audited
database selector to `nexus` to roll back launches; existing Neironych jobs
continue reconciling under their original identity.
