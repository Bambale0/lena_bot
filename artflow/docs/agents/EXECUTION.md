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
- Image model prices are database-backed in `model_costs` and editable through the Telegram admin panel and web admin API.
- User balances are stored on `users.credits`; all generation charges must flow through repository credit helpers.
- Text-bot image generation, Mini App/site image generation, and Midjourney image flows have separate charge entry points.
- There is no existing per-user model entitlement table or unlimited billing override.

## Intended outcome
- Admin enters a target Telegram ID and selects one or more image models.
- Selected models become unlimited only for that user: effective generation cost is 0, no credits are deducted, and generated records store `credits_spent=0`.
- All non-selected models keep the configured price.
- Video and music billing are unchanged.
- The rule applies consistently to Telegram bot, Mini App, and site image generation paths.

## Acceptance criteria
1. Persist per-user unlimited image-model entitlements in the database with a unique user/model constraint.
2. Admin can enable/disable an entitlement by Telegram ID and image model from the Telegram admin panel.
3. Admin APIs can list/update the same entitlements for web control-plane parity.
4. Entitled image generations bypass balance checks and credit deduction.
5. `Generation.credits_spent` is 0 for entitled runs, preventing accidental refunds/royalties from paid amounts that were never charged.
6. Repeat/remix paths use the same entitlement rule.
7. Non-image generations and non-entitled users retain existing billing.
8. Migration, repository tests, admin tests, bot tests, web/Mini App tests, CI and production smoke pass before completion.

## No-hardcode / observability
- Entitlements are database-backed; no user IDs or model IDs are hardcoded.
- Admin selects only base `GenerationType.image` model keys; quality variants inherit the entitlement through the base generation model key.
- Repository logs entitlement changes and unlimited billing decisions without secrets.

## Steps
1. [x] Read repository instructions and backend-integration skill; audited model pricing, admin control plane, user model, charge paths and migration head.
2. [ ] Add entitlement model + Alembic migration.
3. [ ] Add repository entitlement and effective-credit helpers.
4. [ ] Add Telegram admin management flow and admin API parity.
5. [ ] Apply effective image credits across bot, Mini App/site and Midjourney image flows.
6. [ ] Add regressions and run focused checks.
7. [ ] Review, CI, merge, autodeploy and production smoke.

