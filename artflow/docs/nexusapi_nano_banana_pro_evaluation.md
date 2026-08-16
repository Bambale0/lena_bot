# NexusAPI Nano Banana Pro — provider evaluation runbook

Status: evaluation only. Production routing remains unchanged.

## Why the lab is live-schema driven

Nexus currently exposes two overlapping descriptions of Nano Banana Pro:

- the dedicated model page documents `prompt`, `aspect_ratio`, `seed`, a single `image_url` and `webhook_url`;
- the generic API docs expose `image_urls`, and the public catalog advertises Nano Banana Pro with up to four references.

Nexus's own open-source MCP example resolves this kind of drift by reading `/openapi.json`, following `GenerateRequest.properties.params.discriminator.mapping[model_name]`, and showing the live schema before a billable generation.

APIX's admin lab follows the same principle: curated controls cover the published stable fields, while `Live OpenAPI` + `Raw overrides` let an admin test every field that the provider actually exposes at test time.

## Native provider contract

Endpoint: `POST https://nexusapi.dev/generate`

Authentication:

```http
Authorization: Bearer <NEXUS_API_KEY>
Content-Type: application/json
Idempotency-Key: <uuid-v4>
```

Canonical request shape:

```json
{
  "params": {
    "model_name": "nano-banana-pro",
    "prompt": "required text",
    "aspect_ratio": "1:1",
    "seed": 12345,
    "image_url": "https://.../reference.jpg",
    "webhook_url": "https://.../callback"
  }
}
```

Published dedicated-model aspect ratios:

- `1:1`
- `16:9`
- `9:16`
- `4:3`
- `3:4`

`seed` is documented as integer without a public numeric range, so the lab does not invent one.

### Reference transport

For one reference the curated lab sends `image_url`, matching the dedicated Nano Banana page.

For two to four references it sends `image_urls`, matching the generic Nexus API contract and the public catalog's “up to 4 ref” capability claim. This is intentionally part of provider evaluation because the public docs are not perfectly aligned.

If live OpenAPI disagrees with either static description, use `Raw overrides` to send the exact live-schema form and record the provider response.

### Tasks

Native `/generate` is treated as asynchronous and expected to return `202 Accepted` plus `task_id`. The lab polls `GET /tasks/{task_id}` until `completed` or `failed`, retaining the observed status history and latency. Result extraction accepts URL and base64 task-result shapes.

`webhook_url` is optional. Polling remains active even when a webhook is supplied so webhook delivery cannot hide a broken task-status API.

### Idempotency

Each logical request gets one UUID-v4 `Idempotency-Key`. Changing prompt/settings/refs/overrides rotates the key. Re-pressing Run without changing the request reuses the same key, allowing Nexus to de-duplicate accidental repeat POSTs. `Новый Request ID` intentionally rotates the key when the admin wants a new paid run with identical parameters.

## Admin-only Telegram lab

The main menu renders `🧪 Тест` only when `MainMenuContext.is_admin` is true. The test router is also protected with the existing `IsAdmin` filter for both messages and callbacks, so hidden UI is not the authorization boundary.

The lab supports:

1. Text-to-image and image-edit/reference modes.
2. Prompt editing.
3. All dedicated-model aspect-ratio controls plus Auto/omit.
4. Optional integer seed.
5. Up to four references from Telegram photos, Telegram image documents, or public HTTP(S) URLs.
6. Automatic `image_url` vs `image_urls` reference transport for parity testing.
7. Optional webhook URL.
8. `Live OpenAPI`: fetch and display the exact current NanoBananaPro schema.
9. `Live каталог`: inspect provider metadata/current pricing instead of hardcoding price.
10. `Raw overrides`: merge arbitrary JSON fields into `params` after reading live schema; `model_name` and `prompt` remain protected.
11. Exact final `/generate` payload preview before a paid request.
12. A stable Request ID / `Idempotency-Key` with explicit manual rotation.
13. Paid launch against Nexus only; APIX user credits are not debited.
14. Polling status history and manual last-task inspection.
15. Friendly diagnostics for 401, 402, 422, 429, network failures and timeouts.
16. Result delivery back into Telegram.
17. Diagnostic report with task id, POST latency, total provider time, status history, request id, request payload and final task payload.

The production `api/image_service.py` provider path is intentionally untouched.

## Server configuration

Store the real key only in `artflow/.env` on the test server:

```env
NEXUS_API_KEY=...
NEXUS_BASE_URL=https://nexusapi.dev
NEXUS_HTTP_TIMEOUT=30
NEXUS_POLL_INTERVAL=1
NEXUS_POLL_TIMEOUT=120
```

Do not commit a real API key.

## Acceptance matrix before provider migration

| Case | Mode | Settings / input | Expected evidence |
|---|---|---|---|
| A | schema | Live OpenAPI | NanoBananaPro schema is visible and recorded |
| B | catalog | Live catalog | model metadata and current price are visible |
| C | T2I | Auto ratio, auto seed | completes and returns image |
| D | T2I | fixed seed | repeat behavior can be compared manually |
| E | T2I | 1:1 | valid square result |
| F | T2I | 16:9 | valid landscape result |
| G | T2I | 9:16 | valid portrait result |
| H | T2I | 4:3 | completes |
| I | T2I | 3:4 | completes |
| J | Edit | one Telegram photo | `image_url` path works and edit follows source |
| K | Edit | one image document | upload/mirroring path works |
| L | Edit | one public URL | Nexus can fetch APIX/public media |
| M | Multi-ref | two refs | `image_urls` is accepted or provider returns actionable 422 |
| N | Multi-ref | four refs | advertised maximum is actually accepted |
| O | live-schema extra | Raw overrides | any OpenAPI-only field can be exercised without code change |
| P | idempotency | press Run twice unchanged | no duplicate logical task/charge |
| Q | idempotency | New Request ID | identical params can intentionally create a fresh task |
| R | failures | invalid override | provider 422 is surfaced with raw diagnostic context |
| S | task lifecycle | paid run | queue/processing/final states and timings are visible |

Optional webhook tests should use a controlled callback endpoint. The model page itself does not document a signing scheme, so the lab does not invent webhook-authentication behavior.

## Production migration gate

Do not replace the existing Nano Banana Pro route solely because one T2I request succeeds.

Before switching production routing, establish:

- acceptable quality on real APIX prompts;
- acceptable edit/reference fidelity;
- verified multi-reference behavior and actual max refs;
- required aspect-ratio parity;
- current live cost and commercial margin;
- median and tail latency;
- 402/422/429/5xx behavior;
- correct idempotency under retries/double taps;
- sufficient result-URL lifetime or immediate mirroring strategy;
- provider stability over repeated tests.

Only after that should NexusAPI be added to production `image_service` behind an explicit provider selector/feature flag with a rollback/fallback path.
