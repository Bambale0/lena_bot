# Studio capability completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to execute this plan task by task.

**Goal:** Release all currently audited APIX backend capabilities through the approved admin-only lilac Mini App, with safe controls and complete user journeys.
**Architecture:** Keep the modular monolith and existing API/auth/checkout. Add focused lilac modules, typed clients and regression tests rather than rewriting App or old studios.
**Tech Stack:** React/TypeScript/Vite, FastAPI/SQLAlchemy, pytest, Playwright.
**Spec:** Approved conversation and `outputs/apix_backend_frontend_gaps_2026-10-25.md`; acceptance below is the repository-local binding scope.

## Global Constraints

- Preserve approved lilac style, central Create and admin-only launch; no expansion of access. Existing site, default Mini App and Telegram flows must continue working.
- User explicitly requests this new Mini App surface. Site/bot parity means reuse existing server rules, no contradictory copy; amend shared backend and affected existing clients if contracts change. Do not duplicate every admin panel into the text bot.
- No migrations, production financial/config changes, paid generations, payment submissions or secrets. Tests mock network at integration seams, not app components.
- Actual mounted DTOs are authoritative; no invented endpoints. Stars checkout is retired, prompt improvement is a no-op, provider_operations router is unmounted: none becomes a new advertised product.
- Use typed Russian forms, loading/error/empty/unauthorized states, accessible labels, minimum 44px targets and narrow-screen layouts. Destructive actions require explicit confirmation via existing accessible Sheet/alertdialog primitive.
- Admin mutation writes have finite timeout, same-actor lifetime guard, ref mutex, no automatic retries. On 401/403 discard privileged state and block writes. Financial uncertainty must survive reload with minimal owner/target/action marker in sessionStorage; unavailable storage blocks financial write. Never persist request bodies, private prompts or credentials. Reconcile from server before permitting another financial action.
- CAS mandatory where server provides revisions; other state-setting writes send changed fields only, fresh-read before confirmation, detect stale original fields and require reload rather than overwrite. Explain remaining non-CAS race honestly; do not invent revision fields.
- Tests first (record actual RED before implementation, then GREEN). Each worker stages/commits only its task files, no push/merge or subagents. Controller owns review/release and ledger.
- Local tools: Node `C:/Users/happy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe`; Python `D:/code/2026-10-24/promptx-ux-ui/work/apix-venv/Scripts/python.exe`. Playwright local config `D:/code/2026-10-24/promptx-ux-ui/work/playwright-studio-local.config.ts`; sequential runs, build first, workers=2. No dependency or CI weakening.

## Acceptance / spec

Consumer: advanced publication (real model, tags, cover upload with public consent), explicit image series creation/configuration without charge and safe previous-series replacement, graceful failed home-thumbnail fallback. Existing full generation/music/library/account functionality stays intact.
Admin: global generation queue/filter/search/pagination and safe manual fail/optional refund; model and package pricing editors; separate global/per-user ledger; Wan/Qwen/Nano routing; image auto-refund deadlines; image and Seedance supplier reconciliation; Tribute product mapping/catalog; Kling4 audience; feed identity instruction; inspect/deactivate another published prompt. Forms expose actual backend fields with validation and success confirmed from response/readback, not fabricated full histories or provider cancellation.

### Task 1: Consumer journey completion and media resilience

**Files:** Modify `artflow/webapp/src/features/lilac/{library-screen,image-series,home-screen}.tsx`, `src/lib/api.ts`, `src/App.tsx`, `src/styles/lilac.css` as needed; add focused typed helpers/modules and browser/unit tests under existing directories.
**Interfaces:** Consume actual web prompt, upload-media and image-session endpoints plus existing model catalog. Preserve existing component props; additive catalog/owner props allowed.

- [ ] Add real browser RED tests: advanced publish payload with model/tags/cover; no-public-consent and invalid/failed-upload blocks; create series configured from catalog without generation call; previous active replacement explicit; thumbnail load error fallback.
- [ ] Implement advanced publication through `POST /api/web/prompts` (model/tags/preview_url supported; v1 category-only form is insufficient). Infer/category per real server contract; no unsupported category payload. Validate safe cover URL and current model; explicit public consent; refresh own list. Guard actor/lifetime and errors.
- [ ] Add Projects create-series form through `POST /api/web/image-sessions`, real model/mode/aspect/quality/count and optional prompt/reference uploads supported by selected model. Validate against existing catalog caps. Explain no generation/charge; confirm replacing active series. Do not copy hidden recipe or overwrite draft implicitly.
- [ ] Make home card thumbnails recover from network/non-image failure with existing icon/background, no mutation loop or external placeholders. Preserve layout and style.
- [ ] Run focused browser GREEN, unit suite, typecheck/build. Record RED/GREEN exact commands/results and commit task.

### Task 2: Safe operational admin controls and atomic manual refund

**Files:** Add `src/features/lilac/admin/{workspace,operations,pricing,ledger,primitives}.tsx`, typed `src/lib/studio-admin.ts` and related focused helper/test files as appropriate; modify `owner-screen.tsx`, existing Sheet only additively if needed. Backend `artflow/api/web/admin.py`, existing repository helper, existing site admin copy and focused pytest tests as needed.
**Interfaces:** Produce `LilacAdminWorkspace({api,ownerId,systemPanel?:ReactNode})`, reusable typed admin request/lifetime/confirmation and mutation guard helpers for Task 3. Keep files focused by responsibility. Scope shared helper to new admin modules, not unrelated transport rewrite.

- [ ] Backend RED: fail+refund atomic rollback, completed-task race/final task conflict, one winner/no duplicate refund, auth. Replace split status/balance commits with existing `fail_generation_and_refund` while preserving admin ledger entry type/actor note; explicit conflict if transition lost. Return confirmed changed/refunded fields, preserve existing client compatibility; correct site claim (local failure marking is not provider cancellation).
- [ ] Browser RED then queue: `GET /admin/generations` real status/type/q/limit/offset filters; inspect task then reason + optional refund + confirmation. Durable uncertainty guard before financial send, reconcile on fresh status/ledger, never resend automatically or claim refund from generic 200. Stale/finished and double click covered.
- [ ] Pricing: `GET /admin/pricing`, PATCH `/admin/model-costs/{id}` and `/admin/price-plans/{id}` with actual writable fields. Model key/type and package key are read-only. Use numeric validation, changed-fields-only payload, fresh original-state check and clear diff confirmation. Never send null to NOT NULL fields. Changing economics may invalidate old Tribute checkout; explain new product mapping requirement. No automatic live writes.
- [ ] Ledger: `GET /admin/ledger?user_id=&limit=` global and account filter, show delta/balance/type/source/note/time; bounded result, no fake pagination/export.
- [ ] Moderation: real web prompt lookup by ID/public catalog, inspect selected target and confirm `POST /admin/prompts/{id}/deactivate`. Do not invent approved pending-queue filters.
- [ ] Integrate workspace into existing owner without removing overview/users/credit guard/payments/withdrawals/pending moderation. Keep admin UI inaccessible after auth loss; previous account responses suppressed. Add finite-timeout requests and shared guard interface, explain module interfaces in report for Task3.
- [ ] Run focused backend/browser GREEN, unit/typecheck/build, full Python if feasible in pinned env; record any platform-only limitation without weakening. Commit task with test evidence.

### Task 3: Typed provider, recovery, supplier and catalog settings

**Files:** Add focused modules under `src/features/lilac/admin/` e.g. `system-panel.tsx`, `provider-settings.tsx`, `recovery-settings.tsx`, `supplier-reviews.tsx`, `tribute-products.tsx`, `content-settings.tsx`; extend `src/lib/studio-admin.ts` types narrowly; integrate `systemPanel` in owner; add browser/unit tests. Additive backend tests if needed, no migrations/new endpoints.
**Interfaces:** Consume Task2 admin helpers/workspace; produce `LilacAdminSystemPanel({api,ownerId})` organized with friendly disclosure/navigation, not a wall of raw JSON forms.

- [ ] RED/GREEN tests per family: load real values, validated payload, confirmation, unauthorized/conflict/error handling and no replay; cover negative amounts/blank notes/stale revisions and mobile rendering.
- [ ] Wan routes `GET/PUT /admin/provider-routing/wan30/{standard|prime}`: policy neironych_kie|neironych_only|kie_only, validated native ID, expected_revision. Qwen `{text|image|video}` primary/backup neironych|kie|null (distinct). Nano `/admin/provider-routing/nano-banana-2.1` primary neironych|nexus. Source/credential readiness/revision displayed where actually returned. CAS409 reload requires explicit new confirmation, never auto overwrite.
- [ ] `/admin/image-recovery/{neironych|nexus}` validated integer seconds600..86400, display human duration; no live edits by tests.
- [ ] Image and Seedance `/admin/{images|seedance}/refund-supplier-reviews` and `/refund-supplier-review/{id}` PUT resolution confirmed_not_accepted|cost_reconciled, trimmed note12..500. Explicitly supplier-only, customer balance unchanged. Confirmation/uncertainty/lifetime safeguards; server409 final settlement protected.
- [ ] Tribute GET `/admin/payments/tribute-products`, PUT same `/{product_id}` real fields plan_key,payment_url,currency=usd,amount_minor,enabled,expected_revision. Use selected real plans and safe integer minor-unit conversion (no float cents loss), expected_revision0 for new product. CAS conflict and immutable price terms explained. Never expose credentials or call real provider in tests.
- [ ] Kling4 GET/PUT `/admin/kling4/access` audience admin|public|disabled; explicit public-exposure confirmation, distinct from admin-only Studio rollout. Feed identity GET/PUT `/admin/feed-recipe-identity` instruction100..3000; editable admin policy only, never persist instruction/request body in storage.
- [ ] Test all new modules plus existing admin/account/generation regression. Final release marker unique. Typecheck/build/unit; record exact RED/GREEN, screenshots and commit.

## Release gate (controller)

- [ ] Independent task review and fixes after each task; final broad standards/spec/security/financial review.
- [ ] Full maintained checks in Linux CI; local targeted backend+frontend checks and actual mocked browser journeys. No payment/generation/config mutation on production. Update OpenAPI snapshot if response schema requires it using existing exporter.
- [ ] Review whole diff, hygiene/secrets/parity, maintain execution ledger. Output report + real browser screenshots under task outputs.
- [ ] PR to main, attach to chat, native squash auto-merge only after required checks and resolved review conversations. Verify exact merge SHA main CI + Production Autodeploy + fresh public health, anonymous protected endpoints401, bundle marker and admin rollout guard. Report verified SHA; green PR CI alone is not deployment.
