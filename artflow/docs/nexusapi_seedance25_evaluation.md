# NexusAPI Seedance 2.5 — admin evaluation

Status: admin-only provider lab. Production video routing is unchanged.

The lab follows the same live-schema pattern as the NexusAPI MCP example repository:

1. Read `/public/models` to confirm the exact model id and current catalog price.
2. Read `/openapi.json` and resolve `GenerateRequest.properties.params.discriminator.mapping["seedance-2.5"]`.
3. Build `POST /generate` with one `params` object.
4. Keep the returned `task_id` and poll `GET /tasks/{task_id}` to `completed` or `failed`.

Live schema observed during implementation: `Seedance25Params`.

## Curated controls

The Telegram admin lab exposes all currently published Seedance 2.5 fields:

- `prompt` (1–5000 chars in the lab);
- `duration` 4–30 seconds;
- `aspect_ratio`: `adaptive`, `1:1`, `3:4`, `4:3`, `9:16`, `16:9`, `21:9`;
- `resolution`: `480p`, `720p`;
- optional `seed`: -1..2147483647;
- `generate_audio`;
- `content_filter`;
- `image_urls` up to 30;
- `video_urls` up to 10;
- `audio_urls` up to 10;
- paired `start_image_url` + `end_image_url` first/last-frame mode;
- optional `webhook_url` through raw overrides or future curated control;
- raw overrides for any newly added live-schema field.

Telegram images, videos, audio and voice messages are mirrored to APIX public storage before being sent to Nexus. Public HTTP(S) URLs are accepted directly.

## Safety / billing

The UI is rendered only for admins and the router itself is protected by `IsAdmin`. APIX user credits are not debited. A paid run consumes only the configured NexusAPI balance. Request IDs are stable idempotency keys and rotate whenever the logical request changes.

Video polling uses `NEXUS_VIDEO_POLL_TIMEOUT` (default 600 seconds), which is intentionally longer than the image lab timeout.

## Migration boundary

This test does not replace the current production Seedance 2.5 provider. Provider migration must remain a separate decision after real quality, multimodal-reference fidelity, audio behavior, latency, error handling and cost are measured.
