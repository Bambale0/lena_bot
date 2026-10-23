# Kling 4 admin preview

The integration is available only to Telegram administrators listed in server-side `ADMIN_IDS`. Website and Mini App discovery, direct quote/launch and asset uploads enforce the same DB rollout policy. No public enablement is part of this release.

## Operations

- `/kling4` and the single **Kling 4** Telegram catalog entry open the reference collector directly. Text becomes the prompt; photos, videos and audio become references automatically, including files sent as documents. A file caption sets the prompt. Send materials in any order, then calculate and confirm the price. Character/voice bindings are optional advanced controls. Old keyframe start buttons open a new reference draft. Existing keyframe orders restored from history retain their model, tariff and explicit frame controls; unassigned uploads ask the user to select a frame role. The website/Mini App retain both studio models; this Telegram simplification does not change provider contracts or tariffs.
- `/kling4_access admin` retains the administrator preview. `/kling4_access public` opens it to everyone; run only after the owner explicitly requests public rollout. `/kling4_access disabled` stops new admissions while existing tasks continue recovery/delivery.
- Authenticated web administrators can GET/PUT `/api/web/admin/kling4/access` with `{ "audience": "admin" | "public" | "disabled" }`. Changes record actor, time and source.
- Existing `/admin/pricing` and bot model pricing controls manage the six resolution/input tariffs. Migration 047 seeds provider-credit-equivalent retail defaults (no conversion or markup inferred). Review retail prices before public release. Base rows are catalog entries; checkout requires the exact active tariff row and never silently falls back.

## Contracts and checkout

`kling-4.0/reference-to-video` accepts text, images, ordinary videos, image/video elements and independent or bound voices. `kling-4.0/keyframe-to-video` accepts first, ordered middle and last frames. Both support integer durations 3–30 seconds and 720p/1080p. No 4K/HDR, seed, negative prompt, Omni IDs or upstream cancellation is promised.

The existing `/api/v1/generate/video/quote` and `/api/web/generate/video/quote` accept the typed `kling4` options alongside normal prompt/duration/resolution/aspect_ratio fields. Launch additionally requires the exact `quoted_credits` and UUID `intent_id`. One user intent creates one job, wallet debit and ledger entry in the same transaction. A changed payload under an existing intent returns 409; an unchanged transport retry returns the original job. Explicit new orders need a new intent.

Files use the authenticated `/api/web/kling4/assets` multipart endpoint, including Telegram init-data authentication. Storage paths bind sources to the authenticated database user. Kling checkout rejects another user’s upload or an arbitrary remote media URL. Sources are measured before price confirmation; staging refreshes their provider URLs without changing frame order or resizing the first frame. APIX upload limits: 100 MiB per asset, 40 megapixels per image. These are product limits, not claims about provider maxima. Voice references must be 5–30 seconds, confirmed by the real KIE rejection and corrected successful smoke.

Live billing differs from the initial guide’s conservative hypothesis: only ordinary `video_urls` enter the video-input tariff/duration. Video elements consume shared media/video quotas but do not themselves select the video-input tariff. With ordinary videos, billable seconds = output + ceil(max(sum(ordinary input seconds), output)); otherwise output seconds only. Element-only, mixed and fractional cases were verified below. Prompt, full typed inputs, tariff key, measured input, billable seconds and rate are snapshotted in the existing generation history.

Callbacks use persisted per-generation signed correlation and read authoritative `recordInfo`, checking task and model and extracting only result JSON. Callback bodies cannot authorize final status. Provider GET failures, missing URLs and failed result download remain recoverable. Paid createTask is sent once. Timeout, malformed success or missing identity retains the reserve as an unknown submission; there is no automatic replacement POST or timeout refund. Definite provider refusal uses the existing atomic refund reducer.

The bounded, fairly paginated recovery worker survives restarts, uses existing configured video recovery batch/concurrency/timeouts, validates and copies MP4 to APIX storage before completion, and retries the existing durable Telegram delivery outbox independently of generation. Site and Mini App share the same status/history records. An original source must still exist to rerun a saved order.

The bot’s result actions restore the complete typed Kling recipe into an editor and require a fresh quote/intent. Generic cross-user feed recipe remix is deliberately not advertised for Kling 4: the existing recipe format cannot safely preserve its extra roles/voices and source ownership. The feed API rejects that unsupported route explicitly; use the dedicated editor with your own uploaded materials.

## Migration and rollback

`047_kling4_preview` adds policy/audit and durable intent tables plus editable tariff rows. Fresh full Alembic upgrade through 047 was tested on disposable loopback PostgreSQL. Production uses the normal main CI autodeploy migration. Application rollback retains financial intents, tariff edits and audit records; the migration downgrade deliberately preserves them. No secret or existing customer balance migration is required.

## Live smoke evidence — 2026-10-22

All successful cases used 3-second outputs. Results were downloaded, ffprobe validated, and preview frames visually reviewed. Provider task-level credits below are authoritative; total 1073 KIE credits. The initial two rejected capability fixtures cost zero credits and remain documented. A second bounded run and two billing edge probes increased the cumulative smoke ceiling from 900 to 1200 credits; actual spend remained 1073.

| Case | Provider task ID | Status | Credits | Verified output |
|---|---|---|---:|---|
| kling-4.0/keyframe-to-video:720p | `3e3d2d354cffc53107cd55b28de3064b` | success | 85.5 | 1280×720, 3.041995 s |
| kling-4.0/keyframe-to-video:1080p | `4694eb5cb6f9e3f7e531ce4cecb71c69` | success | 127.5 | 1920×1080, 3.041995 s |
| kling-4.0/reference-to-video:720p | `aa1cfbe82750308c43df04dac5cd8f28` | success | 85.5 | 1280×720, 3.041995 s |
| kling-4.0/reference-to-video:1080p | `c513b7705daefb730adbb503223ca283` | success | 127.5 | 1920×1080, 3.041995 s |
| reference-video:720p | `02953a6748dc1403d8d462b31883e4a2` | success | 102.0 | 1280×720, 3.041995 s |
| reference-video:1080p | `777b6279dbfe92591a155d9bc2bfb460` | success | 153.0 | 1920×1080, 3.041995 s |
| video-element-only | `4bd959002712697356c05579ff4bb287` | fail | 0.0 | Rejected before output |
| image-element-bound-and-standalone-voice | `101f3bb489ba7efcfcf145ba7daa7505` | fail | 0.0 | Rejected before output |
| video-element-only | `22ea9c8dc1a5e411bc1880815fbf1a34` | success | 85.5 | 1280×720, 3.041995 s |
| image-element-bound-and-standalone-voice | `709b923681e7017e991e4b061dd18b84` | success | 85.5 | 1280×720, 3.041995 s |
| mixed-video-element | `f1214db1d0f1e79b1c57fe5bf9912a23` | success | 102.0 | 1280×720, 3.041995 s |
| fractional-video | `c627ca664d824c2e91f8ecb8b3f84e3f` | success | 119.0 | 940×940, 3.041995 s |

The rejected video-element fixture had a ball instead of a detectable character; KIE rejected it. The rejected voice fixture was shorter than five seconds; KIE rejected it. Corrected public portrait/video and spoken WAV fixtures completed successfully. Reference fixture source: https://github.com/opencv/opencv/blob/master/samples/data/lena.jpg. No customer media was used.

To reproduce with explicit paid-call authorization: `python scripts/smoke_kling4_live.py --execute --budget-credits 900`. Optional `--case`, `--portrait`, `--prior-spend-credits` and `--output` permit bounded capability runs. Never rerun an unknown paid POST. This tool submits directly to KIE and does not debit APIX customer balances.

## Incident checks

Locate the existing generation and its intent; read `kie_video_callback`, `kie_video_submission`, typed `kling4`, tariff/billing snapshots and provider task ID in protected diagnostics. For `kie-submit:<id>`, a task identity is unknown: do not submit again. A delayed signed callback may bind it. Reconcile the KIE console/recordInfo before a financial decision. For a bound success with missing local MP4, repair download/storage; for a stored result with pending notice, retry delivery only. An unavailable Telegram chat never changes provider generation status. Rollout disabling never stops these recovery paths.
