# Prompt, Pinterest and Telegram media repair — 2026-10-21

Baseline `7b037621a3c418b3b1add1a5e523fcc8ef5ef230`; branch
`fix/prompt-reference-media-20261021`; isolated worktree. User explicitly requests
root-cause diagnosis, a plan, implementation and verification of four selected
production failures. No Qwen routing, Nexus moderation bypass, paid smoke,
customer credit adjustment or unrelated refactor is authorized.

## Preflight and causes

Read root/app AGENTS, README/runtime inventory, Compose/CI, provider adapters,
Pinterest routes/FSM/UI, prompt privacy/ownership, billing/settlement seams,
media helpers, models and focused tests. Schema/migrations need no change.
Existing diagnostics/error.log remain untouched; production queries are read-only.

1. Show Prompt sends a whole escaped prompt as one Telegram message. No size
   guard/chunking exists at that callback; ownership/hidden-prompt guards exist.
   Reuse split_text_chunks, splitting raw text before escaping with a safe budget
   for astral Unicode. Keep every character and markup, keyboard only at the end.
2. Pinterest route/FSM/UI advertise five optional angles (seven total), but the
   selected Nano Banana Pro route accepts four total. Derive optional slots from
   the actual shared model capability, expose that in metadata and enforce before
   upload/charge/launch. Keep scene -> identity -> evidence ordering. Do not
   enlarge provider caps or silently discard already selected photos.
3. Seedream 5 Pro has no prompt-length admission validation. Provider's current
   playground advertises 5000 chars for both modes. Stored recent prompts reach
   6366 chars. Validate the complete rendered prompt before charge and before
   any reference staging/provider call; preserve all user text and return an
   actionable rejection. Reuse the same validator in bot and shared web/Mini App
   API, with an adapter backstop. No silent truncation or model substitution.
4. Feed video sends only URL even when the exact local output survives (verified
   generation 46718 is done and has an MP4 on disk). Prefer bounded local file
   multipart upload to bypass public URL-fetch failures. Marketplace has an old
   preview URL and incomplete URL-failure recovery; reuse safe media delivery and
   explicitly handle a truly missing preview. Never guess a different user's
   file, fabricate lost media, or fetch arbitrary private-network URLs.

## Acceptance / scope

site and mini_app: same server-side Seedream admission and Pinterest metadata /
reference budget. telegram_bot: same limits plus safe long-prompt/media delivery.
Every rejected over-limit request performs no charge or provider POST; historical
stored invalid refs remain editable rather than launching or silently truncating.
Prompt access stays owner-only and hidden recipes stay hidden. Model/provider
selection, prices and mutable admin settings unchanged; limits reflect intrinsic
provider/Telegram contracts, not new business policy. No migrations/new secrets.

Observability: log entity ID, delivery mode, safe error class and counts/lengths;
never full prompts, signed URLs, credentials or customer media. Finite I/O/size
limits and local path containment for uploads. Preserve idempotent settlement.

## Plan / progress

1. [x] Fresh audit and read-only production diagnosis; record causes and plan.
2. [x] RED long-prompt callback regression; minimal chunked send; focused checks.
3. [x] RED Pinterest metadata/upload/launch limit regression; shared budget and UI/FSM parity.
4. [x] RED Seedream service/API/bot pre-charge regression; shared admission checks.
5. [x] RED media-card local-file/recovery regression; bounded safe delivery fixes.
6. [x] Full applicable backend/frontend/provider/privacy/financial checks and
   independent Standards/Spec + Open Code Review; no unresolved high findings.
7. [ ] Protected PR, four exact-head CI checks, native auto-merge; exact merge-SHA
   Production Autodeploy and public health/runtime verification.

Test seams: actual handler calls with fake Telegram transport; Pinterest service
metadata and authenticated run boundary; image generation API/provider boundary;
real synthetic local media and mocked URL failures; UI browser selection. Use a
disposable PostgreSQL for integration; never test writes against production.

Sources: https://kie.ai/seedream-5-0-pro and
https://docs.kie.ai/market/seedream/5-pro-image-to-image;
https://core.telegram.org/bots/api#sendmessage and #sendvideo.

Progress evidence: RED tests reproduced oversized Telegram HTML/astral messages,
Pinterest advertised 5 extras while model allows 4 total, invalid service calls
reaching asset processing, Seedream >5000 reaching staging/provider submission,
and local-video URL delivery plus invalid placeholder/old-photo reuse. Minimal
repairs pass 20 focused new admission/media tests plus prompt/privacy/provider
and existing flow checks (185-case selection passed before final additions).
New data: the original Seedream failure is 6366 chars; original MP4 is 21,160,426
bytes and public HTTP200 (above Telegram's 20 MB URL fetch limit). Missing preview
returns a 67-byte one-pixel placeholder and fallback JPEG is also 1x1. No original
file exists locally; truthful text fallback is implemented, original reupload is
needed to restore that preview. No generated/customer substitute was invented.
Frontend typecheck/build, 114 units, and 5 Desktop Pinterest browser scenarios
passed, including rejecting three extras before uploads with budget two.
Full Ruff and diff checks pass. Full PostgreSQL-backed backend suite is running.

First full local run: five failures isolated. Three migration tests correctly
refused the disposable database's nonstandard name; create the required
`apix_session_migration_test` in that same disposable container (no production DB).
Two legacy marketplace assertions expected the rejected 1x1 file; updated them to
assert the intentional text-card contract, with new handler regressions proving
buttons and truthful missing-preview text. No tests removed or gate weakened.
Provider inventory initially lacked synthetic DATABASE_URL; rerun with test-only
DSN. Full rerun follows these environment/expected-behavior corrections.

Independent review: Standards found zero issues across 21 files and independently
ran 28 focused tests. Spec reproduced one P2 gap: shared web/Mini App feed remix
charged before the image adapter rejected a long rendered recipe. RED handler
regression reproduces it on both surfaces; the final fully rendered feed prompt
now uses the same pre-charge HTTP422 validator (including the read-only quote).
Full-suite corrected-environment run passed before this amendment; repeat focused
and full checks plus amended review are required before queueing merge.

Final local verification at code SHA `6a4c50a42e7416597d916ada1a491c71a04b8c70`:
3645 backend tests passed with disposable PostgreSQL and nginx:alpine (37.61s);
114 frontend unit tests and 5 Desktop Pinterest browser scenarios passed;
frontend build/typecheck, Ruff, compileall, provider inventory and diff checks passed.
Three existing warnings remain (multipart deprecation / old AsyncMock fixtures).
Standards and Spec independently reviewed the amendment: zero remaining findings;
Spec reran 11 admission tests, Standards reran four feed-admission regressions.
Open Code Review delegate selection/rules informed the independent manual review;
all changed production files, tests and documentation were included in review.

Delivery PR: https://github.com/Bambale0/lena_bot/pull/288 . Required exact-head
checks, native squash auto-merge and merge-SHA Production Autodeploy are pending.
Final delivery evidence will be attached to this PR after runtime verification.
No migration, secret, price or mutable business configuration change is required.

GitHub automated review subsequently identified two P2 delivery regressions:
external-URL video cards skipped the existing in-place edit, and aiogram method
shortcut kwargs did not set transport timeout. Three RED assertions reproduced
both defects (including real aiogram Message objects with fake transport).
Restore external-video edits while preserving local-file guards; call the Bot
transport with request_timeout=90 for video/document sends. Both independent
reviewers found zero remaining amendment issues (34 / 7 tests independently).
Full amended backend suite: 3646 passed, same three existing warnings (36.99s).
Ruff and diff checks pass. Exact-head CI must rerun after this amendment.
