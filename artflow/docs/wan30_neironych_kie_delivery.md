# Wan 3.0 / Wan 3.0 Prime - APIX release

## Provider routing (checked 23 October 2026)

Neironych is primary, KIE is standby. The authenticated partner catalog now
advertises `wan-3` and `wan-3-prime`; these verified IDs are the configurable
defaults for `WAN30_NEIRONYCH_MODEL_ID` and `WAN30_PRIME_NEIRONYCH_MODEL_ID`.
An explicitly empty override disables that primary mapping. The production
container had neither environment override configured at preflight.
Availability is rechecked against `/v1/models` before a paid POST. Catalog
membership does not alone prove successful generation.

The native body uses documented fields only: the product's `mode` must not
be forwarded upstream. Real tests with that extra field failed downstream
with `argolink_400`; corrected bodies reached asynchronous generation.
All site, Mini App and Telegram checkout paths share this adapter. A new
Prime draft uses 16:9, 5s, 720p and sound enabled; saved explicit choices
remain intact.

Prime's native contract requires 4–30s, 16:9/1:1/9:16, sound enabled, no
seed or start/end frames; audio references require visual references.
Unsupported native options use the existing KIE standby with the original
model and settings. This includes file/link inputs, disabled safety,
fixed-ratio frame input, and edit operations: native Wan edit forbids a
fixed output duration, so it cannot preserve APIX's quoted duration.
Normal Wan retains 2–30s and silent output support. No unsupported option
is silently discarded or translated into a different paid operation.

Definite admission rejections may use KIE. 5xx, timeout, unknown acceptance
and an unavailable catalog may NOT create a second paid task. Already
accepted tasks are reconciled on their original provider. KIE createTask
is single-shot.

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

Migration 043 adds only missing rows and does not overwrite custom
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

## Legacy generic provider-operation gateway

Wan3 video tasks are available to customers through the quoted Studio video
checkout (web and Mini App) and through the Telegram video wizard. They are
not exposed as a separate paid operation in the older generic provider
contract gateway: its legacy duration-only pricing ignores input video
reference seconds. Wan3 contract entries remain in the audit inventory
and non-paid smoke manifest. A separate generic route can be enabled only
after its billing and durable provider identity match the quoted checkout.

## Public-feed repeat correction (19 October 2026)

The public-feed generic path previously omitted the typed quoted Wan request.
It now shares strict pre-charge pricing and canonical recipe restoration with
normal Wan checkout; Telegram also preserves source mode/settings before its
confirmation. See [Wan feed repeats](wan30_feed_repeat.md) for the incident,
input/privacy guarantees, regression evidence and live-verification boundaries.

## Runtime routing control and release validation (23 October)

Migration `048_wan_routing` carries effective native mappings into
`wan_routing_settings`: configured mappings retain `neironych_kie`, while an
explicitly empty or incompatible legacy mapping retains `kie_only`. Only
reviewed Wan3 family/variant aliases remain active. Verified defaults are retained
for later administrator enablement; bootstrap never re-enables a disabled
primary. Runtime reads this table for
new tasks; environment values are bootstrap defaults only if a row is absent.
The shared administrator page `/wan-routing-admin.html` is linked from the
site admin cabinet, Mini App settings and Telegram admin panel. Authenticated
GET/PUT `/api/web/admin/provider-routing/wan30/{standard|prime}` enforce admin
rights server-side. Operators can select Neironych with KIE standby, Neironych
only or KIE only, and update the corresponding Wan3 native mapping. Saving a
Neironych route checks the authenticated catalog; family/variant validation
prevents switching the logical product to Wan2, another family or the wrong
Prime variant. Every save compares the expected revision under a row lock
and commits the change with actor/source/before/after audit evidence. A stale
save returns 409. Credentials remain in the secret environment and never
enter settings/audit/GET responses; only configured/not configured is exposed.

A missing Neironych key bypasses its catalog and paid transport, selecting
KIE when the DB policy permits standby. `neironych_only` fails closed instead.
An unavailable DB/catalog or an unknown paid submission is never treated as
permission to create a second paid task. Native-incompatible options retain
KIE payload semantics when standby is enabled.

Two corrected synthetic 5s/720p requests completed via the real Neironych
adapter. Both authenticated MP4 downloads passed ffprobe: 1280x720, video and
audio streams, approximately 5.038s; provider usage reports 5 billed seconds.
Initial downstream-rejected test jobs were confirmed not chargeable. No APIX
customer wallet changes or paid KIE fallback were made during validation.

PR #293 initially passed all four required checks and merged, but its
post-merge credential/control-plane findings were discovered before deploy.
Main workflow `39921456846` was cancelled before production rollout. The
follow-up release must include both review fixes and migration 048; no manual
production checkout/build/configuration was used.
