# NexusAPI Nano Banana Pro — provider evaluation runbook

Status: evaluation only. Production routing remains unchanged.

## Public provider contract used by APIX

Native endpoint: `POST https://nexusapi.dev/generate`

Authentication:

```http
Authorization: Bearer <NEXUS_API_KEY>
Content-Type: application/json
Idempotency-Key: <uuid-v4>
```

Request body:

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

Only `model_name` and `prompt` are required. Optional fields are omitted rather than filled with invented defaults.

Published `aspect_ratio` values for Nano Banana Pro:

- `1:1`
- `16:9`
- `9:16`
- `4:3`
- `3:4`

`seed` is published as an integer but the public model page does not state a numeric range, so the evaluation client does not invent one.

`image_url` activates image-edit behavior. The dedicated public model schema currently documents one `image_url`, not an `image_urls` array.

`webhook_url` is optional. The provider documentation recommends polling for image tasks, so APIX continues polling even when a webhook URL is supplied.

Create response is expected to return a `task_id`. Task state is inspected with `GET /tasks/{task_id}` until a terminal `completed` or `failed` status. The evaluation UI records intermediate statuses and latency.

## Admin flow

The Telegram main menu contains `🧪 Тест` only when `MainMenuContext.is_admin` is true. The callback is additionally protected by the existing `IsAdmin` router filter, so hiding the button is not the authorization boundary.

The test console supports:

1. `Text → Image` and `Image edit`.
2. Prompt editing.
3. Every published Nano Banana Pro aspect ratio plus `Auto`, which omits the field.
4. Optional integer seed.
5. Reference image from Telegram photo, Telegram image document, or public HTTP(S) URL.
6. Optional webhook URL.
7. Exact raw `/generate` payload preview before spending provider balance.
8. Live `/public/models` inspection for provider-side model metadata/pricing.
9. Paid test launch with a fresh `Idempotency-Key`.
10. Polling lifecycle and last-task inspection.
11. Friendly diagnostics for 401, 402, 422, 429, network failures and timeouts.
12. Result delivery from provider URL or base64 payload shapes.
13. Full diagnostic summary: task ID, create latency, total latency, status history, idempotency key, request payload and final task payload.

The test flow never debits an APIX user's credits and never calls the production `image_service` routing path.

## Server configuration

Store the real key only in `artflow/.env` on the server:

```env
NEXUS_API_KEY=...
NEXUS_BASE_URL=https://nexusapi.dev
NEXUS_HTTP_TIMEOUT=30
NEXUS_POLL_INTERVAL=1
NEXUS_POLL_TIMEOUT=120
```

Do not commit a real API key.

## Acceptance test matrix before production migration

Run at least the following from `🧪 Тест`:

| Case | Mode | Ratio | Seed | Reference | Expected |
|---|---|---|---|---|---|
| A | T2I | Auto | Auto | none | completes and returns image |
| B | T2I | 1:1 | fixed | none | completes; same seed can be compared manually |
| C | T2I | 16:9 | Auto | none | landscape result |
| D | T2I | 9:16 | Auto | none | portrait result |
| E | T2I | 4:3 | Auto | none | completes |
| F | T2I | 3:4 | Auto | none | completes |
| G | Edit | Auto | Auto | Telegram photo | edit follows prompt and source |
| H | Edit | 1:1 | fixed | image document | completes without upload/reference errors |
| I | Edit | Auto | Auto | public URL | provider can fetch APIX/public media |
| J | any | any | any | any | raw payload matches selected controls |
| K | any | any | any | any | `/public/models` returns the intended model and current price metadata |
| L | any | any | any | any | task transitions and final payload are visible; no duplicate task from one button press |

Optional webhook should be tested only against a controlled callback endpoint because the public Nano Banana documentation does not publish a webhook signing scheme on the model page.

## Production migration gate

Do not replace the current Nano Banana Pro provider solely because a basic T2I smoke passes.

Current APIX product behavior has historically exposed a broader Nano Banana Pro contract (more aspect ratios and multiple reference images) than the public Nexus Nano Banana Pro schema currently documents. Before switching production routing, compare the live `/public/models` metadata and real admin smoke results against the capabilities users already have.

Recommended migration gate:

- image quality is acceptable across representative prompts;
- edit/reference fidelity is acceptable;
- median and tail latency are acceptable;
- 402/429/provider-failure behavior is understood;
- current price is commercially acceptable;
- required ratios and reference count have parity, or the product deliberately narrows them;
- idempotency behaves correctly under repeat clicks/retries;
- provider result URLs remain usable long enough for APIX to mirror them;
- only then add NexusAPI to production `image_service` behind an explicit feature flag/provider selector and retain rollback/fallback.
