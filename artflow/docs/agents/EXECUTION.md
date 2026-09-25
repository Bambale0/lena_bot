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
