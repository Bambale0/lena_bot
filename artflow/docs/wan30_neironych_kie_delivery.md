# Wan 3.0 / Wan 3.0 Prime - APIX release

## Provider routing (checked 15 October 2026)

Neironych is primary, KIE is standby. The real APIX Neironych key
GET /v1/models returned 13 models, none Wan3/Prime. Therefore today
all Wan3 jobs will use KIE. Do not claim Neironych completed them
until the partner grants access and WAN30_NEIRONYCH_MODEL_ID and
WAN30_PRIME_NEIRONYCH_MODEL_ID are configured from verified model IDs.
No paid probe to guessed IDs. 5xx, timeout, unknown acceptance may NOT
create a second paid task. KIE createTask is single-shot.

Official KIE documentation:
https://docs.kie.ai/market/wan/3-0-video
https://docs.kie.ai/market/wan/3-0-video-prime

## Simple user workflow

1. Select Wan 3.0 or Wan 3.0 Prime.
2. Select Text, Animate photo, or Edit video.
3. Choose 480p / 720p / 1080p and 2-30 output seconds (maximum total,
   including all input video ref durations: 30 seconds).
4. Upload input media and type the instruction. Two photos in basic
   photo mode are treated as first and last frame. The optional
   sound, seed, extra references, safety and file/link fields are
   available in collapsed Advanced section in the modern Studio.
5. Inspect exact credits. APIX measures input-video lengths using
   ffprobe on owned uploads, adds output seconds and rounds total
   up to the next full second. Remote video URLs cannot bypass billing.
6. Telegram requires a one-time price confirmation. After submission,
   tasks appear in History and result MP4 is delivered to Telegram.
   On restart the provider poll worker and signed callback recover jobs.

## APIX retail prices - credits per billable second

| Model | 480p | 720p | 1080p |
|---|---:|---:|---:|
| Wan 3.0 | 6 | 12 | 24 |
| Wan 3.0 Prime | 9 | 18 | 36 |

Migration 042 adds only missing rows and does not overwrite custom
admin tariffs. Exact active resolution row is mandatory; there is no
silent fallback to an inactive or cheaper base tariff.

## Safety

- Prompt limit 4500 characters, seed=0 valid, and false audio preserved.
- Photo/video/audio reference order and counts validated before POST.
- Input videos total 15s max, output+input 30s max.
- Neironych durable before-submit journal with client request identity.
- KIE signed callback, no retries for paid createTask POST.
- Only completed MP4 mirrored to local permanent APIX storage counts
  as done. No expiring CDN URLs used as completed output.
- Transient canonical GET errors do not fail or refund accepted tasks.
- Scheduler owns 1-hour expiration and guarded refund/provider review.
- KIE callback and worker share durable Telegram notice outbox and
  atomic DB transitions; duplicate completions have no side effects.
- Repeating a Wan result uses the same quoted-price route, never
  the old output-only regeneration charger.

## Known deliberate limit

KIE supports automatic duration=-1 in the lower-level validated
contract. It is NOT offered as a paid UI choice yet: charging a
30-second reserve without an exactly-once actual-duration refund
would overcharge shorter outputs. Ordinary fixed durations 2-30 sec
are fully supported; automatic duration needs separate settlement work.

## Release / rollback

Run backend and UI tests, code review, and GitHub CI. Main autodeploy
migrates DB before updating containers. Verify live API and both model
variants. No live paid smoke until user explicitly authorizes that
particular test. Rollback by reverting PR and disabling model base rows
via existing admin UI; do not delete historical financial data.
