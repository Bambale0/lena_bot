# Execution ledger — video to prompt integration

Baseline: commit `31a91c6`; working tree had no tracked changes at task start.
Date: 2026-09-16.

## Current state
- Photo to prompt exists in `api/photo_prompt_service.py`, `/api/v1/photo-prompt`,
  `/api/web/photo-prompt`, text bot flow, and Mini App/Web services UI.
- Photo to prompt is free and has no `ModelCost` billing row.
- Model costs are database-backed through `model_costs`, seeded in `db/seed.py`,
  and editable through `/admin -> Стоимость моделей`.
- Comet config already exists in `core.config.settings` through
  `COMET_API_KEY`, `COMET_BASE_URL`, assistant model fields, and related
  photo-prompt fallback wiring.
- Video to prompt is implemented through Comet/Qwen3.8-Max for web, Mini App,
  and the text bot. Uploaded source videos use unique temporary public files
  and are removed after the synchronous provider response.
- `docs/agents/AGENT_CHANGELOG.md` is registered but missing from the repo.

## Intended outcome
- Add a user-facing "Видео -> промпт" feature beside "Фото -> промпт".
- Default function cost is 3 credits, controlled by the existing admin model
  cost editor via a `ModelCost` row.
- All applicable surfaces are covered:
  site/web: services UI and web route;
  mini_app: `/api/v1/video-prompt` and services UI;
  telegram_bot: text bot upload flow from the same prompt tools area.

## Acceptance criteria
1. Provider service sends video URL to Comet/Qwen3.8-Max and extracts text.
2. Backend validates file kind/size before provider call.
3. Backend spends the configured credits before provider call and refunds once
   on provider failure.
4. Seed creates `llm.video-prompt` at 3 credits and admin model editor can see it.
5. Web/Mini App UI exposes the feature next to photo prompt.
6. Text bot exposes the feature next to photo prompt and returns the ready prompt.
7. Focused tests cover service payload, endpoint validation/billing/refund, seed,
   and bot/UI wiring where practical.

## No-hardcode / control plane
- `llm.video-prompt` default cost is seeded as 3 credits.
- Runtime cost is read from `model_costs`, so admins can update it without code.
- Provider credentials stay in existing settings; no secrets are added.

## Observability
- Provider success logs provider/model metadata only.
- Provider failure logs user id and error without file body or secrets.
- Credit spend/refund operations are recorded in `credit_ledger` with a short
  source identifier that fits the database column.

## Test seams
- Service tests monkeypatch `httpx.AsyncClient`.
- Route tests monkeypatch provider call, repository cost/spend/refund methods,
  and public file saving.
- Seed test inspects `DEFAULT_MODEL_COSTS`.
- Frontend surface test checks API client and services UI strings.

## Steps
1. [x] Preflight: tool repos updated; relevant skills/instructions read.
2. [x] Repository/photo-prompt/admin-cost audit.
3. [x] Added tests for service payload, file validation, billing/refund,
   temporary-file cleanup, seed/admin wiring, menus, and frontend surfaces.
4. [x] Implemented backend service, routes, billing, refund, and seed.
5. [x] Implemented text bot flow; Bot API download limit is 20 MB, while web
   and Mini App retain the 100 MB product limit.
6. [x] Implemented Web/Mini App UI in the current TS app and legacy/V4 apps.
7. [x] Verification: 14 focused tests passed; Python compilation passed;
   frontend typecheck/build passed; focused Ruff checks passed. The broader
   touched-module run exposed 15 pre-existing failures unrelated to this diff.
8. [x] Open-code-review attempted; external LLM configuration was missing.
   Delegate review then covered 23/23 reviewable files and prompted fixes for
   temporary-file retention, unpaid storage, file-signature validation,
   Telegram's 20 MB download limit, and blocking filesystem I/O.
9. [x] Parity verified for `site`, `mini_app`, and `telegram_bot`.

## Final verification and follow-ups
- No migration is required: startup seed inserts the missing `ModelCost` row.
- No live Comet request was made because no acceptance-test credential/video
  was provided. The provider-specific `video_url` contract remains the main
  rollout risk and should be smoke-tested before production enablement.
- `docs/agents/AGENT_CHANGELOG.md` remains registered but absent.
- Repository-wide tests are not green at baseline; unrelated failures remain
  in older menu/feed/model/video normalization expectations.
- The exact maintained backend PR gate plus the new tests passed locally:
  204 tests. CI was updated to include the new service, bot handler, public-file
  helper, and focused tests in its Ruff/pytest gates.
- Local Playwright could not launch Chromium because the host lacks
  `libatk-1.0.so.0`; GitHub Actions remains the authoritative E2E check.

---

# Execution ledger — video result publishing to feed

Baseline: commit `cad3c5b8`.
Date: 2026-09-20.

## Current state
- Public feed already renders both image and video cards.
- Modern web/Mini App feed publish endpoint already allows publishing own ready image/video media while keeping remix prompts hidden.
- Text-bot video completion UI coupled feed publication to prompt/library visibility, so feed-derived videos lost the `📤 В ленту` action.
- Repository `share_to_feed` also rejected all feed derivatives, so adding the button alone would fail.

## Intended outcome
- Every completed own video can be added to the public feed.
- A video derived from another feed post may be published as new media.
- The source post's prompt remains private and cannot be copied or saved to the user's prompt library through this flow.

## Acceptance criteria
1. Completed video result keyboard includes `📤 В ленту`.
2. Feed-derived video keeps `📤 В ленту` but hides copy-prompt and library actions.
3. Bot callback publishes the user's own video and returns the feed deep link.
4. Repository allows video derivatives while retaining the source guard for images.
5. Legacy Mini App `/generations/{id}/share` follows the same video rule.
6. Feed rendering remains unchanged and supports video.
7. Focused regression tests and CI pass before merge.

## No-hardcode / security
- No model/provider-specific whitelist was added; the rule is based on `GenerationType.video`.
- Ownership, done status, and result URL checks remain enforced server-side.
- Prompt/library protections remain unchanged for hidden source prompts.

## Steps
1. [x] Audited bot result keyboard, KIE/webhook completion, share callback, repository guard, feed renderer, and web/Mini App publish paths.
2. [x] Split feed publish permission from prompt-library/copy permission in result keyboard.
3. [x] Enabled video derivative publication in bot and repository.
4. [x] Added legacy Mini App parity for video `/share`.
5. [x] Added focused regressions for keyboard, bot callback, repository SQL guard, and Mini App route.
6. [x] PR #153 CI: APIX backend-quality, frontend build + Playwright Mini App smoke, Feed Security Contracts, Provider Contract Compliance, Pinterest Backend Contract, and Photo Prompt Integration all passed on the implementation SHA.
7. [ ] Merge / production autodeploy / production smoke.

---

# Execution ledger — per-user unlimited image models

Baseline: commit `9773b96e`.
Date: 2026-09-23.

## Current state
- Image model prices are database-backed through `model_costs` and editable in Telegram `/admin`.
- Image charging existed independently in text-bot image sessions, Midjourney image flows, and Mini App/Web image/remix handlers.
- Early balance checks existed before the final spend in several text-bot image flows.
- Generation failure/refund logic uses `Generation.credits_spent`, so unlimited generations must persist zero charged credits to avoid phantom refunds.
- Video, music and analysis tools have separate billing paths and are out of scope.

## Intended outcome
- Admin can enter a Telegram ID or internal user ID and toggle unlimited access for selected active image models.
- Entitled users can generate with the selected image models even with zero balance.
- Unlimited applies only to the selected image model roots, including their pricing-quality variants.
- All other models and media types retain normal billing.

## Data model and control plane
- New table `user_image_model_unlimited` with unique `(user_id, model_key)`.
- Foreign keys use cascade semantics; admin actor and creation timestamp are recorded.
- Admin callbacks use numeric `model_cost_id` to stay under Telegram callback limits, while persistence stores normalized base `model_key`.
- Only active `GenerationType.image` base rows are selectable in the admin keyboard.
- No user IDs or model allowlists are hardcoded.

## Billing contract
- `charge_image_generation()` is the shared image-only charge boundary.
- Entitled generation: `allowed=True`, `charged_credits=0`, no credit ledger spend.
- Regular generation: existing atomic `spend_credits()` path is preserved.
- Every migrated generation path writes the actual charged amount into `Generation.credits_spent`.
- Existing failure/refund paths therefore refund zero for unlimited work.
- Video/music billing is unchanged.

## Surfaces
- `telegram_bot`: image session, default/advanced image wizard, Nano Banana flows, Midjourney image/imagine/action/blend/describe.
- `mini_app` and `site/web`: primary image generation and image remix/feed-repeat paths share `miniapp_routes` billing.
- Admin: Telegram `/admin -> ♾ Фото-безлимит`.

## Observability
- Entitlement enable/disable/clear logs include user id, normalized model key and admin Telegram id.
- Unlimited billing bypass logs user id, model key and nominal credits without secrets or prompt/media content.

## Verification evidence so far
- TDD schema RED: `UserImageModelUnlimited` missing test failed before implementation.
- Schema test GREEN after model/migration implementation.
- Admin selector RED: missing `bot.keyboards.admin_unlimited` failed before implementation.
- Admin selector GREEN: 2/2.
- Python compile succeeded for all touched Python modules.
- Focused integration run: 35/35 passed, covering Midjourney, admin entry/FSM, repository charge contract, selector contract, schema contract, and zero-credit generation record.
- A broader local `test_image_gen_references.py` run has one pre-existing unrelated signature mismatch (`cb_image_model` test omits current `db_user` argument); the new unlimited node itself passes.
- Local isolated repository tests can hit a pre-existing circular-import collection issue; exact-head GitHub CI remains the authoritative full gate.

## Steps
1. [x] Preflight: repository instructions, local project skills, tool repos and billing/admin architecture audited.
2. [x] Implementation plan written before production changes.
3. [x] RED/GREEN tests for schema and admin selector.
4. [x] Schema, migration and repository entitlement/charge helpers implemented.
5. [x] Telegram admin control plane implemented.
6. [x] Text-bot image billing and early balance checks migrated.
7. [x] Mini App/Web primary image and remix billing migrated.
8. [x] Focused tests added to the maintained PR CI gate.
9. [ ] Diff review and exact-head CI.
10. [ ] Merge, Alembic production upgrade, autodeploy, health and log smoke.

---

# Execution ledger — Seedance 2.5 video-reference transport and preflight

Baseline: commit `b83aac15`.
Date: 2026-09-24.

## Production evidence
- Video references are not being lost. Production runtime recorded Seedance requests with `videos=1`, and KIE task records contain `reference_video_urls` after APIX uploads them to KIE storage.
- Successful example: generation `49967`, KIE task `ea78d8083b86fc88ea153bee7d26b899`, one image + one MOV video reference, provider state `success`.
- Failed edit example: generation `50328`, KIE task `9b51ee472ce0e0a8d14a334d426d40d2`; KIE received all three image refs plus the MP4 video ref, classified the prompt as video editing, and required `aspect_ratio=adaptive` plus `duration=-1`.
- Failed media examples showed missing local preflight: videos longer than 30 seconds and low-pixel media reached the provider before being rejected.

## Root cause
The transport path was correct. The failures came from two separate gaps:
1. Seedance 2.5 reference videos were accepted without provider-specific media validation.
2. Prompts explicitly asking to replace/edit people in the supplied video were still sent with manually selected output ratio/duration, while KIE's edit scenario requires adaptive ratio and automatic duration.

## Fix
- Preserve and regression-test `reference_video_urls` in the final KIE payload.
- Web uploads accept MP4/MOV video refs and ffprobe them before persistence.
- Telegram validates its video metadata before mirroring.
- Runtime validates local video refs before KIE upload.
- Provider-safe limits enforced from live provider behavior: duration 2–30s for references, 4–30s for explicit edit source video, width 300–6000, pixel count 407696–8295044, aspect ratio 0.4–2.5.
- Explicit video-edit prompts with one reference video use KIE-required `aspect_ratio=adaptive` and provider `duration=-1`.
- Billing for a local edit source is calculated from the probed source duration before credits are spent; multiple edit-source videos and unprobeable external edit URLs are rejected before charge to avoid ambiguous/incorrect billing.
- Small local image refs can be safely upscaled without cropping to Seedance's minimum provider dimensions/pixel count.
- Mini App file picker no longer advertises MKV for Seedance reference video.

## Verification
- TDD confirmed the old upload path lacked metadata validation and accepted MKV.
- TDD confirmed the old edit request sent `9:16` instead of `adaptive`.
- Focused Seedance/video suite: 43/43 passed.
- Python compile passed for touched backend/bot modules.
- Ruff passed for touched provider/runtime/bot/test files and import ordering in Mini App routes.
- Provider Contract workflow now explicitly gates the new video-ref payload test and small-image upscaling regression.

## Pending delivery
1. [ ] PR review and exact-head CI.
2. [ ] Merge to main.
3. [ ] Production autodeploy and health/log smoke.


## Follow-up — dedicated Genjutsu create-hub entry

Date: 2026-09-25.
Baseline: `664f6f92baf897d80be304502a54895a23f0bfd6`.
Branch: `feat/genjutsu-create-hub-entry`.

### User outcome
- Telegram create hub gets a full-width `🥷 Genjutsu` shortcut in the location requested by the operator.
- The shortcut opens a dedicated two-choice screen: Motion Transfer or Object Swap.
- Choosing either configured model enters the existing Genjutsu reference → source video → params → prompt flow.
- Regular users only see the entry when Higgsfield credentials are configured.
- Admins can preview the screen before credentials exist, but launch buttons fail closed with a clear provider-not-configured alert.

### Scope / parity
- `telegram_bot`: updated because the request is specifically for this Telegram menu.
- `mini_app`: no change; Genjutsu model flow already exists there.
- `site/web`: no change; Genjutsu model flow already exists there.
- This is a navigation shortcut, not a capability or pricing change.

### Verification
1. [x] Added create-hub contract coverage for the Genjutsu entry.
2. [x] Added handler coverage for configured flow and admin preview fail-closed behavior.
3. [x] Python compilation and focused Ruff checks passed for all touched Python files on an isolated branch checkout.
4. [x] Focused regression tests passed locally: 3/3.
5. [x] Exact-head PR CI passed: APIX CI/CD #941 and Provider Contract Compliance #882.
6. [x] Diff review completed with no unresolved high-severity finding.
7. [ ] Merge / production autodeploy / production smoke.




---

# Execution ledger — Higgsfield Genjutsu integration

Baseline: commit `5399541afeeb530eafded3f2e353518870d5c6e4`.
Date: 2026-09-25.
Branch: `feat/genjutsu-integration`.

## Current state / audit
- APIX video generation is capability-driven: runtime `VideoModel`, `VIDEO_CAPS`, DB-backed `model_costs`, Telegram FSM, Mini App/Web model metadata, provider contract catalog, operation registry, smoke manifest and reconciliation.
- Local APIX uploads are stored under the public upload surface and can be probed with ffprobe through `api.media_gateway`.
- Provider results can be mirrored into APIX storage with SSRF-safe `public_files.mirror_url`.
- No Higgsfield/Genjutsu provider code existed at baseline.

## Verified provider contract
- Motion Transfer endpoint: `higgsfield/genjutsu/motion-transfer/v1.0`.
- Inputs: `prompt`, `video_url`, `image_urls`, `resolution`.
- API-safe surface implemented: source video 1–30 seconds, up to 8 image references, 480p/720p.
- Higgsfield V2 auth: `Authorization: Key KEY_ID:KEY_SECRET`.
- Async lifecycle uses `request_id` and authenticated `GET /requests/{request_id}/status`.
- Object Swap endpoint remains config-backed because current Higgsfield pages have published inconsistent `higgsfield` / `higgsfiled` spelling.

## Intended outcome
- Add Motion Transfer and Object Swap as first-class video models.
- Keep source video + reference images intact on Telegram, Mini App and site/web.
- Measure source-video duration server-side before spend; client duration is UX-only.
- Keep prices editable through existing `model_costs` admin control plane.
- Persist completed provider video to APIX storage rather than treating Higgsfield CDN as canonical.
- Do not trust unsigned provider webhook payloads; use authenticated polling/reconciliation.

## Acceptance criteria
1. Both models appear in text bot and shared Web/Mini App model metadata.
2. Both require one source video and at least one reference image; max 8 refs.
3. Source duration is verified from APIX-owned upload and limited to 1–30 seconds.
4. Resolution supports 480p/720p and price is resolved by DB-backed per-second variants.
5. Provider create returns `request_id`; terminal statuses and failures map into normal APIX finish/refund paths.
6. Completed videos are mirrored to `provider-results`.
7. Provider catalog, operation registry and smoke manifest remain structurally complete.
8. Relevant backend tests, provider contract checks, frontend build and CI pass before merge.

## No-hardcode / control plane
- Credential, base URL, retry policy and both endpoint paths are environment settings.
- Default pricing rows are seeds only; runtime pricing remains `ModelCost` and admin-editable.
- No secrets are committed or logged.

## Observability / failure semantics
- Submit log: model, request_id, reference count, resolution.
- Retry log: method/path/attempt/backoff; credentials and media payloads are excluded.
- Reconciliation is idempotent through existing generation terminal-state checks/refund helpers.
- `failed`, `nsfw`, `canceled/cancelled`, auth/credit/validation errors are terminal failures and use normal refund semantics.
- Missed callbacks are irrelevant to correctness because completion is reconciled through authenticated status polling.

## Progress evidence
1. [x] Repository instructions and relevant backend/Mini App/frontend/release skills reviewed.
2. [x] Official Genjutsu and Higgsfield V2 SDK contracts verified.
3. [x] Dedicated Higgsfield HTTP client and Genjutsu provider adapter added.
4. [x] Dynamic video models, capability metadata, DB pricing seeds and canonical labels added.
5. [x] Mini App/Web validation and authoritative source-duration billing added.
6. [x] Telegram reference-images → source-video workflow added.
7. [x] Provider catalog, operation registry and smoke templates added.
8. [x] Focused regression run: 68/68 passed after correcting one test-only variant-key assumption.
9. [x] Release audit found production has no `HIGGSFIELD_CREDENTIALS`; added a credential feature gate so Genjutsu is hidden from user surfaces until server credentials are configured.
10. [x] Re-verified current official provider pages: Motion Transfer publishes `higgsfield/genjutsu/motion-transfer/v1.0`; Object Swap currently publishes `higgsfiled/genjutsu/object-swap/v1.0`. Both remain env-configurable.
11. [ ] Exact-head provider/backend/frontend/E2E CI after rollout-safety fixes.
12. [ ] Merge/autodeploy, production credential configuration and paid-provider smoke.


## Follow-up — Genjutsu admin pricing control

Date: 2026-09-25.
Branch: `feat/genjutsu-admin-pricing`.

### User outcome
- Telegram `/admin` gets a dedicated `🥷 Genjutsu цены` control.
- Admin can edit Motion Transfer and Object Swap independently for 480p and 720p.
- Values are credits per source-video second.
- 480p updates its base fallback atomically with the explicit 480p variant.
- Runtime source of truth remains `model_costs`; changes apply without redeploy across Telegram, Mini App and site/web.

### Control plane / parity
- Telegram admin: dedicated Genjutsu pricing screen.
- Web admin: existing `/admin/pricing` / `/admin/model-costs/{id}` already exposes the same ModelCost rows; no parallel pricing store is introduced.
- End-user Telegram / Mini App / web resolve prices from the same DB-backed video pricing keys.

### Verification
1. [x] Added dedicated admin pricing regression coverage.
2. [x] Added atomic repository helper for resolution tariff updates.
3. [x] Ruff and Python compilation passed for touched Python files.
4. [x] Focused tests passed: 8/8, including non-finite input rejection and rollback on incomplete tariff rows.
5. [ ] Exact-head CI / review / merge / production smoke.


## Follow-up — Genjutsu provider poll budget (false 10-minute timeouts)

Date: 2026-09-25.
Baseline: `512e86f` (`feat(admin): manage Genjutsu prices (#163)`).

### Incident
- `16:19 UTC` — user 6 (`@Chillcreative`) launched Genjutsu Motion Transfer (#51015, «повтори все четко», 14.7s source, 2 refs, 480p, 240 credits).
- `16:30 UTC` — Telegram bot sent `❌ Ошибка: Время ожидания истекло. Попробуй снова.` and refunded 240 credits.
- Root cause: `bot/handlers/video_gen.py` calls `api/polling.py:poll_until_done` without a timeout, so every provider shared `POLLING_TIMEOUT=600` (10 min). At 16:32 the Higgsfield task (`request_id 243b2eac-ee0f-4e47-9ff9-2ee017db6047`) was still legitimately `in_progress` on the provider side — the render simply outlived the shared budget. Debugging confirmed the failure is not provider- or credential-related; the key is valid (a status probe returns HTTP 200, an invalid key returns HTTP 401).
- Later provider status: `nsfw` — the exact render would have failed anyway, but with the true reason (rejected content) instead of a false timeout.

### Scope / parity
- `telegram_bot`: both launch paths (`_launch_video_generation_from_state`, `_regenerate_video_from_previous`) now start polling through `_start_video_polling`, which forwards `result.provider` so the provider-scoped budget applies.
- `mini_app` / `site`: reconcile (`api/genjutsu_adapter.py` wrapping `miniapp_routes._reconcile_generation_status`) keeps long renders alive via the Genjutsu stale guard instead of failing them at the shared 20-minute mark.
- Web frontend has no own generation timeout (checked `webapp/src`); it follows backend status.

### Change
- `core/config.py`: `HIGGSFIELD_POLL_INTERVAL_SECONDS=5.0`, `HIGGSFIELD_POLL_TIMEOUT_SECONDS=1800` (30 min), `HIGGSFIELD_STALE_TIMEOUT_SECONDS=2400` (40 min, strictly above the poll timeout so reconcile never refunds a task that is still being polled).
- `api/polling.py`: `poll_budget(provider)` resolves per-provider (interval, timeout) from settings at call time with clamps; `poll_until_done(..., interval=None, timeout=None, provider=None)` honors explicit values and adds a timeout warning log with task/provider/duration context.
- `bot/handlers/video_gen.py`: one helper `_start_video_polling`; 4 call sites use it, passing `provider=result.provider`.
- `api/genjutsu_adapter.py`: `genjutsu_stale_timeout(routes)` = `max(STALE_GENERATION_TIMEOUT, HIGGSFIELD_STALE_TIMEOUT_SECONDS)`.
- `.env.example`, `README.md`: documented the new settings.

### No-hardcode / control plane
- All budgets are env settings with in-code defaults; admin can tune intervals/timeouts without redeploy-code changes (only a container restart to pick up `.env`).

### Observability / failure semantics
- Polling timeouts log `task/provider/timeout/interval` before failing.
- Terminal provider failures (`failed`, `nsfw`, `cancelled/canceled`, auth/credit/validation) keep existing refund semantics.
- The previously failed generation #51015 stays failed+refunded (terminal provider state `nsfw`); no un-billing recovery is possible or needed — the user just retries.

### Verification
1. [x] Focused tests: `tests/test_genjutsu_integration.py` + `tests/test_video_gen.py` → 54 passed (5 new: provider budget map, stale-guard ordering, reconcile keeps 25-min render alive, reconcile refunds 45-min render with `reconcile:higgsfield_timeout`, bot forwards provider into polling).
2. [x] Runtime wiring check: `poll_budget("higgsfield") == (5.0, 1800)` on real settings; `poll_until_done(provider="higgsfield")` provably routes through `poll_budget("higgsfield")`.
3. [x] Ruff clean on all touched files (repo baseline list included).
4. [x] Full-suite comparison vs pristine HEAD worktree: failure sets identical except one order-dependent rate-limit test that failed in the pristine run and passed in the fixed tree (flake; all 43 remaining failures are pre-existing at HEAD, unrelated: image caps, veo, feed).
5. [x] Production container rebuild/recreate + health + live Genjutsu budget verification.
6. [ ] Commit/push (needs operator decision: push to `main` triggers CI autodeploy).

## Follow-up — Suno music generation reconciliation

Date: 2026-09-25. Baseline: `541dd6e59c48df1d2af1b910aa4dfcd443264616`.

### Incident and outcome
- Three Suno v5.5 music generations (#40721, #40719, #37933) remained active for 28–41 days after missed KIE webhooks. Operator polled KIE `jobs/recordInfo`, found terminal `fail` with `413 This audio matches an existing recording in our catalog`, and manually failed/refunded them (30 credits total).
- Ensure active Suno music generations can finish or fail from authenticated KIE polling without a callback. Terminal failure must use the atomic, idempotent `fail_generation_and_refund`; nonterminal/provider transport errors must not be treated as content failures.

### Current state and scope
- `scripts/reconcile_stuck_generations.py` already scans active generations, but `api/miniapp_routes.py:_reconcile_generation_status` returns unchanged for music. User-triggered history reconciliation uses the same function. Webhook has separate Suno result parsing and refund handling.
- `site`, `mini_app`, `telegram_bot`: all use the same generation record and webhook; no surface-specific text, price, or parameter change is intended. Check status behavior on all three.
- No schema, migration, permission, or pricing changes. KIE credentials and finite retry policy already live in the existing client. Provider response fields are verified from current client/webhook code and the incident report.

### Plan and verification
1. [x] Red regression tests reproduced terminal failure and successful audio staying unprocessed; later tests cover in-progress, poll error, ambiguous response, and final-state no-op.
2. [x] Music polling uses authenticated KIE status and Suno record-info, with an in-process periodic scan. Existing repo transitions handle completion and refunds; refund row refreshes under lock to honor concurrent webhooks.
3. [x] Focused tests: 19 passed (`test_music_reconciliation.py`, `test_music_webhook.py`, `test_generation_refund.py`, web stale-task test). Ruff passed for new scheduler/config/main/repository/tests and import order in the touched API module; Python compilation and `git diff --check` passed. Open review checked provider ambiguity, transient errors, refund race, scheduler lifecycle, and shared surface state. CI exists but cannot verify an uncommitted working tree; the broader local `test_webapp_routes.py` run has 13 unrelated failures in feed, image caps, text, and pricing expectations. Full Ruff on `miniapp_routes.py` reports pre-existing `_anonymous_user` F821 at line 2027.

### Observability and risks
- Record generation/task/model and provider state/error without payloads or credentials. Refund only on terminal KIE failure and timeout after a valid nonterminal response. Poll errors and malformed/ambiguous responses remain active for later retry. Scheduler runs in the single-worker FastAPI container; it must be deployed to become active.
- No migration or admin change. Interval/minimum age are validated operational settings in `.env.example`; existing price and model configuration is unchanged. Site and Mini App read the same backend status; the text bot receives a webhook notification when one arrives, while scheduler recovery currently updates shared DB state without a proactive bot message. Existing user-owned `nginx.conf` changes were left untouched.

## Follow-up — retire APIX-hosted HappyFox reverse proxy

Date: 2026-09-25. Baseline: `c84a9515208991df5fce52934558c8a7f4c859e3`.

### Outcome and current state
- HappyFox has moved to its own server. Remove the obsolete reverse proxy from APIX so the APIX Nginx container no longer depends on the Fox Docker network or presents the HappyFox TLS/webhook relay.
- `nginx.conf` had a `happyfox_backend` upstream, a `/happyfox/telegram/webhook` relay, `api.happy-fox.online` HTTP/TLS hosts, and HappyFox-backed paths under `tanyapp.chillcreative.ru` and `alena.xn--e1aikcel5c5a.online`. `docker-compose.yml` attaches Nginx to the external `foxgen_backend` network, which is also needed for the separate `banano-miniapp` frontend. No application DB/schema or auth change is involved.
- Two pre-existing uncommitted IP edits in `nginx.conf` and an untracked Nginx backup are present. Backups were copied outside the repository before editing. Scope of Tanya/Alena host removal is being confirmed because those hostnames differ from the HappyFox domain.

### Acceptance and verification plan
1. [x] Remove HappyFox proxy paths, host blocks, and upstream while preserving the separate Banano frontend and its required Compose network. The Tanya/Alena virtual hosts remain, but no longer route APIs/webhooks to HappyFox.
2. [x] Move the untracked Nginx backup out of the workspace; ensure only intended project changes appear in source control.
3. [x] `docker compose config --quiet`, `docker compose exec -T nginx nginx -t`, `git diff --check`, and a scan for stale HappyFox upstream/domain/relay references passed. Diff review confirms other virtual hosts and Banano frontend routes remain. Production certificates, DNS, and containers were not deleted.

### Risks and rollout
- Removing the relay stops HappyFox traffic on the APIX host; user reports HappyFox has moved and no longer needs it. Keep unrelated model `HappyHorse` and Banano frontend routes intact. Because Banano still uses the `foxgen_backend` Docker network, that external network remains in Compose. Production config changes take effect only after deployment/reload; no prices, admin settings, or migrations.

## Follow-up — Genjutsu face identity investigation

Date: 2026-09-26. Baseline: `5e4a9b66160c0d64eaec09d15f81911eaaaea08f`.

### State and acceptance
- User requires the face from photo references to appear in the output video. Recent bot Object Swap generation #51189 completed with both photo and source video in persisted inputs, but output kept the source face while adopting the reference hair color.
- Existing bot → video service → Higgsfield adapter forwards `image_urls`, `video_url`, prompt, and resolution according to the published Genjutsu API contract. The reference is a single collage containing multiple views. A 29.2-second source produced a 480p output.
- Read-only comparison found prior successful KIE Seedance 2.5 generations for the same user with the exact same reference image and a different source video (#50728/#50729/#50732); their prompts explicitly request replacement of the person/face. The recent Genjutsu generations used Object Swap with the same image, a second video, 480p, and explicit face-replacement prompts. This rules out a missing prompt or missing image transport as the primary defect; neither provider's completed status proves face fidelity.
- Read-only contact sheets from local result files for Seedance #50732 and Genjutsu #51189 (same reference and visually similar source scene) show red hair transfer in both outputs. At the clearest sampled facial frame, neither is sufficient visual evidence of the reference person's facial identity. No new provider task was submitted for this comparison; temporary sheets stayed under `/tmp`.
- Official Higgsfield Genjutsu documentation explicitly supports recasting characters from photo references; the user's stated goal is within its advertised scope. The completed Object Swap result is therefore a quality failure of this input/workflow, not proof that Genjutsu lacks face replacement. Higgsfield's separate consumer Video Face Swap has no documented route found in the API catalog. The MCP endpoint requires OAuth and is not connected here.
- The user has only the customer's API key, not account sign-in. Higgsfield documents MCP as account/OAuth based and separate from the API; the API key cannot authenticate that connector. The official API also publishes Seedance 2.5 Video Edit (`bytedance/seedance-2.5/video-edit`) with `video_url` and optional `image_urls`; this is a possible separately metered workflow, not the route the bot currently calls. APIX already has a separate KIE Seedance 2.5 edit path: explicit edit prompt + one reference video + image references, adaptive aspect ratio, duration `-1`, source-duration billing. This existing path can be reused for an authorized comparison, but has not been visually proven on this identity-transfer case.
- Acceptance: establish by a short controlled render whether a single clear portrait and Motion Transfer provide materially better facial identity than the existing Object Swap result; only then choose a safe product change. Do not claim fidelity without visual evidence.

### Dependencies, controls, and test seams
- No migration or admin change is currently planned. Provider credentials/endpoints and DB pricing remain the existing control plane. Any new model would need typed provider contract, admin pricing, all three user surfaces, billing/refund, and audit coverage.
- Paid provider calls must be bounded to a short clip and logged by request ID without media URLs or credentials. Existing `tests/test_genjutsu_integration.py` and `tests/test_video_gen.py` cover transport; a qualitative identity check needs real output inspection.
- Site, Mini App, and text bot share the Genjutsu adapter; any model/UX change must be checked across all three.
- Diagnostic derivatives were removed from the public upload directory after both provider tasks terminated; original user uploads were preserved.

### Steps
1. [x] Audited current runtime generation, provider contract, code path, tests, pricing, and official API/MCP documentation.
2. [x] Prepared a 1.97-second source clip and a single frontal portrait crop from the existing test assets; both public URLs returned HTTP 200 with expected media types.
3. [x] The 2-second Motion Transfer diagnostic `ea4e2909-d304-458a-bde4-4d4ab200f118` failed with the provider's explicit minimum-4-second error. A 4.17-second follow-up `f6447b11-5e56-4b83-a9d5-b2300239efa2` was accepted but ended `nsfw`; no output video exists to compare. No further reruns on this source are planned.
4. [x] Red tests reproduced the accepted-too-short bug in server duration probing and Telegram upload; the server, bot, and shared site/Mini App UX now enforce/show 4–30 seconds before billing. Product face-fidelity changes remain dependent on an accessible, documented provider face-swap API or a successful allowed evaluation of a suitable model. No identity guarantee has been added to the UI.
5. [x] Focused Genjutsu/bot tests: 56 passed. Ruff, Python compilation, `git diff --check`, webapp TypeScript/build, and the provider-contract inventory check passed. OCR automated review remained unavailable due to provider HTTP 402; manual diff review found no high-severity issue. CI for this uncommitted tree is unavailable.
6. [ ] Determine why Genjutsu character recasting fails on the user's original collage/30-second/480p case; compare an allowed short clip with a single clear portrait and explicit character-replacement prompt. A Motion Transfer test on the existing source was rejected by provider moderation, so use only a permitted independent sample rather than retrying that source through another route.
7. [ ] If Genjutsu remains inadequate, evaluate the already integrated KIE Seedance 2.5 video-edit route on a permitted independent sample before recommending it for this use case. A separate direct Higgsfield Seedance route would require a provider contract, per-token pricing/admin settings, bot/site/Mini App parity, and visual acceptance.

## Follow-up — text bot top-up entry on main menu

Date: 2026-09-26. Baseline: `98d96bb`; local `main` is one commit ahead of `origin/main`, working tree clean. User requested to push to `main` and change the text bot's main button from balance to top-up.

- Scope: Telegram text bot only, as explicitly requested. Site and Mini App payment entrypoints are separate screens and need no change. All three bot home keyboard builders exposed the old balance callback, though `bot/keyboards/main.py` currently has no callers; `bot/handlers/payment.py` already handles `menu:topup` and loads active price plans.
- Acceptance: the Russian/English home menu and legacy builder offer a top-up button that opens the existing top-up flow. The balance details screen remains accessible through its existing callback for other callers. No schema, auth, pricing, integration, or admin change; no new observability needed for a static navigation change.
- Plan: (1) add/adjust contract assertions and observe red; (2) change both home builders and observe green; (3) run focused and required checks, review diff, commit and push the branch; (4) inspect CI for the exact commit and report status.
- Progress: red tests confirmed the old callback/labels in all three builders. Updated active Russian/English home, legacy-compatible builder, and unused older builder to `menu:topup`. Focused menu and balance tests: 25 passed. Maintained CI pytest gate: 260 passed; maintained Ruff gate, provider inventory, Python compilation, webapp build, and `git diff --check` passed. The broader local pytest collection still has 42 failures outside the changed menu contract, largely stale tests; this repository's GitHub CI intentionally runs a maintained subset. Automated OCR review failed before any analysis with provider HTTP 402; manual diff review found no high-severity issue. No DB migration or config/admin change.

6. [ ] Merge/deploy only after green review; production Seedance routing remains unchanged.

## Follow-up — Higgsfield Seedance 2.5 Video Edit identity lab

Date: 2026-09-26.
Baseline: `8f3aa98d4f2b1a8397d4b87ac5d39a6d3b156b9e`.
Branch: `feat/higgsfield-seedance25-edit-lab`.

### Evidence / root cause
- Production KIE Seedance 2.5 reference transport is intact: completed edit jobs persisted both image and video references, including #51012 with an explicit character/face replacement prompt.
- Visual evidence from prior comparisons showed appearance traits transferring more reliably than facial identity. This is therefore not a missing-reference transport bug.
- Mesh/noise/style transforms intended to evade provider safety detection are out of scope. The evaluation uses ordinary permitted reference media only.

### Provider contract under evaluation
- Higgsfield endpoint: `bytedance/seedance-2.5/video-edit`.
- Required: `prompt`, `video_url`.
- Optional published controls used by the lab: up to 30 `image_urls`, up to 10 `video_urls`, up to 10 `audio_urls`, `resolution` 480p/720p, `bitrate_mode` standard/high, `generate_audio`.
- The lab reuses existing server-side Higgsfield Key auth and authenticated status polling.
- No production model key, user pricing row, routing rule, or APIX billing path is changed.

### Intended outcome
- Add an admin-only Telegram lab entry under the existing Test Lab.
- Default to 720p/high bitrate and an identity-preservation prompt.
- Require one source video and at least one identity photo before a paid test.
- Let admins upload separate identity images (front portrait first, then optional extra angles), plus optional extra video/audio references.
- Provider result is polled through the existing Higgsfield budget and mirrored into APIX result storage.
- APIX user credits are never charged by this lab; only Higgsfield provider balance is consumed.

### TDD / verification
1. [x] RED contract added to maintained CI.
2. [x] Exact-head RED observed: 4 expected failures for missing adapter, missing selector entry and missing admin router.
3. [x] Minimal provider payload adapter and admin lab flow implemented.
4. [ ] Exact-head GREEN CI.
5. [ ] Open code review.
6. [ ] Merge/deploy only after green review; production Seedance routing remains unchanged.

## Follow-up — promptless Genjutsu diagnostic and face-swap path

Date: 2026-09-26. Baseline: `8f3aa98` (`main`, clean). User explicitly requests resubmitting the latest Higgsfield task without a prompt and implementing video face swap.

- Existing state: Genjutsu Object Swap #51189 completed using one multi-view collage and a source video; face identity remained unreliable. The adapter currently rejects an empty prompt before calling Higgsfield. The live Higgsfield API key is available server-side, while the account/OAuth-backed MCP is not. Earlier Motion Transfer diagnostic on a short derivative was rejected by provider moderation; do not retry that mode/source. A separate KIE Seedance 2.5 edit path already exists but prior same-reference outputs did not demonstrate identity preservation.
- Outcome/acceptance: submit one exact-media Object Swap comparison with no user prompt, record request ID/status and inspect output if completed. For product work, identify an official usable API contract and visually verify identity transfer before exposing a named face-swap operation. Preserve ownership, billing/refund, admin price configuration and parity across site, Mini App, and Telegram bot. No private media URLs or credentials in logs/commits.
- Plan: (1) verify official prompt optionality and existing task inputs; (2) submit the single authorized comparison through the authenticated Higgsfield client and poll to a terminal state; (3) inventory face-swap provider API and current application seams; (4) implement only a verified route with red/green tests and all user surfaces; (5) run relevant checks, review, and report deployment status.
- Diagnostic result: a direct Object Swap request with the exact saved photo/video inputs and no `prompt` field was accepted as Higgsfield task `86652201-fe36-4396-be8d-6815dd959a1c`, then failed immediately: API credit balance too low. No output exists to inspect. No further paid task was submitted.
- Seedance 2.5 audit: production generation #51012 contained one photo and one source video, an explicit replacement prompt, `adaptive` aspect ratio, and source-duration editing. The bot and KIE adapter forwarded both media references. The observed problem is therefore identity fidelity, not loss of the photo in transport. KIE's published multimodal reference contract offers no face-identity guarantee; treating it as an exact face swap would mislabel the product. User confirmed it takes only broad appearance from photos.
- Implemented promptless Genjutsu transport across shared API, site/Mini App, and text bot: blank prompt omits the provider field; non-Genjutsu video models still reject blank prompts; bot accepts `-` and explains it. Focused regression tests and web build pass. Dedicated Face Swap remains blocked by an accessible, documented, visually verified provider route; Higgsfield has insufficient API balance, and the available KIE Seedance route demonstrably lacks exact facial fidelity. No new model or billing was exposed.
- Verification: 83 focused Genjutsu, video bot, Seedance runtime/reference tests passed; webapp TypeScript and Vite build passed; Python compilation and focused Ruff passed; `git diff --check` passed. Repository-wide pytest remains red on unrelated existing tests (including legacy V4 entrypoint assertions and coroutine mocks); the changed-route-specific failure inspected is an outdated mock returning a coroutine for active-generation count. Full Ruff for `miniapp_routes.py` reports the pre-existing `_anonymous_user` undefined reference, present at baseline. CI for this uncommitted change was not run. No commit, push, or deploy yet.

## Follow-up — payment button advertises rails, not the acquirer

Date: 2026-09-26. Baseline: `a587206` (`main`, clean). Branch: `fix/payment-button-card-sbp-20260926`.

- Problem: the RUB payment method button named the acquirer (`💳 T-Bank / СБП` in the bot, `T-Bank / банковская карта` in the Mini App, `💳 Т-Банк` on the legacy site). User report: people read the brand name as "payment is only possible through T-Bank" and abandon checkout.
- Scope: user-visible payment copy only, in RU and EN. The acquirer stays the processing provider — no provider, routing, pricing, billing, webhook, or feature-flag change. `bot/legal_offer.py` bank details (`АО «ТБанк»`, the merchant's own bank) are legally required and intentionally unchanged, as are internal logs/identifiers and the `tbank` provider key.
- Reuse audit: the RUB acquirer is already exposed as rails — `topup_tbank_desc` and `rub_methods_kb` already offered "картой или через СБП". This change only removes the brand name from the surfaces that still showed it, so no new affordance is introduced.
- No hardcode note: payment-method copy remains in the existing i18n/keyboard/component surfaces with the existing pattern. Moving these labels to an admin-editable control plane is a larger, separate change and was not requested; `api/web/billing.py` labels stay the single API-side source consumed by the site/Mini App.
- Plan: (1) locate every user-visible acquirer mention with a repo-wide search; (2) update bot keyboards, i18n (RU/EN), bot payment screens, API label, and both frontend payment surfaces to `Карта | СБП` / `Card | SBP`; (3) add regression tests asserting the copy advertises rails and no acquirer brand; (4) run the maintained CI subset, Ruff, and the webapp build; (5) commit, push, and open a PR since `main` is protected.
- Steps: 1. [x] Located all mentions — bot keyboard (2), i18n RU+EN (4), bot payment screens (2), API label (1), Mini App balance sheet (1), legacy site (1). 2. [x] Applied the copy change on all ten surfaces; the RUB button now reads `💳 Карта | СБП` (RU) and `💳 Card | SBP` (EN). 3. [x] Added four regression tests in `tests/test_plan_payment_method_choice.py` (bot buttons RU/EN, i18n copy, API label, frontend sources) and updated the API label expectation in `tests/test_web_api_contract.py`.
- Verification: maintained CI pytest subset — 270 passed. Payment-focused sweep (`test_plan_payment_method_choice`, `test_stars_payment`, `test_tribute`, `test_payment_webhooks`, `test_apix_legacy_concept_runtime`, `test_web_generation_parity`, `test_public_offer`) — 53 passed. Ruff on changed files clean except the pre-existing `bot/i18n.py` W292 (no trailing newline at baseline; file is outside the maintained Ruff list). `npm run build` (tsc + Vite) passed. `git diff --check` clean. Pre-existing unrelated red: `tests/test_web_api_contract.py` contact-auth rate-limit tests fail identically with the change stashed.
- Follow-up: `webapp/src/components/balance-sheet.tsx` also labels Lava as `СБП / Lava`, which now overlaps the RUB method's `Карта | СБП`; consider disambiguating copy if both providers are enabled for the same user.

### Follow-up — public landing payment button parity

Date: 2026-09-26. Baseline: `63d9334` (`main`, clean). Branch: `fix/landing-payment-label-card-sbp-20260926`.

- Gap found while verifying the deployed release: the production marketing site (`/`) is served from `artflow/landing/`, not the Vite bundle. `landing/js/prototype-premium.js` keeps its own payment-method label map and renders the provider buttons from it, so the merged bot/Mini App change did not cover this surface.
- Reuse audit: `/billing/payment-methods` returns provider keys only, so the landing fallback map is what decides the visible button text. The landing map already said `Карта` (no acquirer brand), so the original complaint was not reproducible there, but the wording did not match the requested `Карта | СБП`.
- Steps: 1. [x] Changed the landing label map entry to `tbank: "Карта | СБП"`. 2. [x] Bumped the cache-busting query on all nine `landing/*.html` pages from `v=20260907_dual_prices` to `v=20260926_card_sbp_label`, otherwise returning visitors keep the cached script. 3. [x] Updated `tests/test_web_generation_parity.py` to assert the new cache-bust token and extended the CI-covered regression test to cover the landing source.
- Verification: maintained CI pytest subset plus `test_web_generation_parity` — green. `node --check landing/js/prototype-premium.js` passed. Ruff clean; `git diff --check` clean.
