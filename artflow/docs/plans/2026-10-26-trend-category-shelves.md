# Trend Category Shelves Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hardcoded trend category chips with database-backed category shelves, full-folder browsing, and complete administrator management across APIX web/Mini App and Telegram bot, delivered through a backward-safe two-phase production rollout.

**Architecture:** Phase A expands the schema and deploys dynamic compatible readers, bounded read APIs, visibility enforcement, indexes, and legacy fallback without enabling custom category writes. Phase B adds audited admin mutations, the restored black/lilac shelf and folder UX, and Telegram folder navigation; every surface reads one category catalog while legacy tags remain mirrored during the compatibility window.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, PostgreSQL/SQLite test fixtures, aiogram, React 19, TypeScript, Vite, Vitest, Playwright, GitHub Actions.

---

## Delivery rules

- Follow @test-driven-development for every behavioral slice: create the focused failing test, run and record the expected failure, add the minimum implementation, then rerun focused and relevant regression suites.
- Follow @subagent-driven-development in this session: one writer at a time; spec review before quality review; resolve every Important finding before advancing.
- Do not make paid provider requests, alter prices/models/provider routing, or mutate production category data during testing.
- Phase A and Phase B are separate protected pull requests. Phase B starts only after Phase A exact-SHA CI, production autodeploy, migration/read smoke, and public health verification succeed.
- Never downgrade the Phase A schema during the compatibility release. Rollback means deploying the verified Phase A reader.

### Task 1: Phase A schema, migration, and category domain

**Files:**
- Create: `artflow/db/migrations/versions/052_trend_categories.py`
- Modify: `artflow/db/models.py`
- Modify: `artflow/core/trends.py`
- Test: `artflow/tests/test_trend_categories_migration.py`
- Test: `artflow/tests/test_trend_category_home.py`

**Step 1: Write failing schema and migration tests**

Add tests that require:

- `TrendCategory`, singleton catalog revision state, and immutable `TrendCategoryAudit` models;
- nullable `UserPrompt.trend_category_id` foreign key plus a composite public-folder index on `(trend_category_id, is_public, created_at, id)`;
- seven seeded keys in existing order;
- idempotent legacy-tag backfill;
- unknown tags preserved verbatim while the fallback relation is assigned and flagged in audit/report metadata;
- rerunning upgrade/backfill creates no duplicate categories/audits and changes no resolved assignment.

**Step 2: Run RED**

Run: `python -m pytest tests/test_trend_categories_migration.py tests/test_trend_category_home.py -q`

Expected: FAIL because migration 052/models/dynamic category resolution do not exist.

**Step 3: Implement the minimum expand-only schema**

Use immutable ASCII `key` (`String(32)`, unique), `title` (`String(80)`), contiguous `sort_order`, `is_visible`, timestamps, and a catalog revision row. Store audit actor/source/action plus before/after JSON without prompt/private content. Keep `TREND_CATEGORIES` only as seed/legacy constants; resolution must prefer the relation and preserve unknown legacy keys rather than normalize them to `featured`.

**Step 4: Run GREEN and migration smoke**

Run: `python -m pytest tests/test_trend_categories_migration.py tests/test_trend_category_home.py tests/test_trend_animals_category.py -q`

Run: `python -m alembic -c alembic.ini upgrade head`

Expected: PASS; migration reaches revision `052` on the isolated test database.

**Step 5: Commit**

Commit message: `feat(trends): add category catalog schema`

### Task 2: Phase A repository and bounded public catalog reads

**Files:**
- Create: `artflow/db/trend_category_repository.py`
- Modify: `artflow/core/trends.py`
- Modify: `artflow/api/trends_routes.py`
- Test: `artflow/tests/test_trend_category_api.py`
- Test: `artflow/tests/test_admin_curated_trends.py`

**Step 1: Write failing repository/API tests**

Cover a paginated shelf response (`<=24` categories, `<=5` previews each), `(created_at,id)` folder cursor (`<=48` items), visible/non-empty filtering, long/invalid cursor rejection, deterministic ordering, query-count guard against N+1, dynamic category titles, and compatibility of the existing `/trends` payload.

**Step 2: Run RED**

Run: `python -m pytest tests/test_trend_category_api.py tests/test_admin_curated_trends.py -q`

Expected: FAIL because catalog repository and shelf/folder routes do not exist.

**Step 3: Implement bounded readers**

Add grouped-count and window/batched preview queries, opaque validated cursors, response DTOs, and routes:

- `GET /api/v1/trend-categories?limit<=24&cursor=...`
- `GET /api/v1/trend-categories/{key}/trends?limit<=48&cursor=...`

Return `next_cursor` and `has_more`. Preserve `/api/v1/trends` during Phase A and enrich each item from the database category relation/fallback without speculative pricing.

**Step 4: Run GREEN**

Run: `python -m pytest tests/test_trend_category_api.py tests/test_admin_curated_trends.py tests/test_trend_category_home.py -q`

Expected: PASS with bounded query counts.

**Step 5: Commit**

Commit message: `feat(trends): add bounded category catalog reads`

### Task 3: Phase A visibility enforcement and compatible surface readers

**Files:**
- Modify: `artflow/api/trends_routes.py`
- Modify: `artflow/bot/handlers/trends.py`
- Modify: `artflow/bot/services/trend_admin_flow.py`
- Modify: `artflow/webapp/src/lib/types.ts`
- Modify: `artflow/webapp/src/lib/api.ts`
- Test: `artflow/tests/test_trend_category_visibility.py`
- Test: `artflow/tests/test_trend_admin_flow.py`
- Test: `artflow/webapp/src/lib/api.test.ts`

**Step 1: Write failing behavior tests**

Require hidden categories to return `404` from public list/detail/prepare/link/checkout/run, and require run to recheck visibility immediately before the durable financial claim. Prove an already claimed idempotent generation can still be retrieved after hide. Require bot/admin category readers to accept dynamic keys without collapsing them to `featured`, while category-creation mutations remain disabled in Phase A.

**Step 2: Run RED**

Run: `python -m pytest tests/test_trend_category_visibility.py tests/test_trend_admin_flow.py tests/test_trend_run_reliability.py -q`

Expected: FAIL on hidden direct routes, pre-claim race, and hardcoded bot validation.

**Step 3: Implement minimum compatible behavior**

Centralize the public-category join/check, call it from every public trend entry point, and re-read under the claim transaction before generation creation. Convert bot and client parsing to server-provided category metadata while keeping the existing visible UI behavior in Phase A. Do not add admin category writes yet.

**Step 4: Run GREEN and Phase A regression set**

Run: `python -m pytest tests/test_trend_category_visibility.py tests/test_trend_admin_flow.py tests/test_trend_run_reliability.py tests/test_webapp_routes.py -q`

Run from `artflow/webapp`: `npm test -- --run && npm run typecheck && npm run build`

Expected: PASS; existing repeat/payment paths remain unchanged.

**Step 5: Commit**

Commit message: `fix(trends): enforce category visibility safely`

### Task 4: Review and release Phase A

**Files:**
- Modify: `artflow/docs/agents/EXECUTION.md`
- Modify: `artflow/docs/plans/2026-10-26-trend-category-shelves.md`

**Step 1: Run full local gates**

Run repository-maintained backend, Ruff, provider-contract, bot-navigation, frontend unit/type/build, and focused Playwright suites. Record exact pass/fail/skip evidence without weakening tests.

**Step 2: Independent reviews**

Run spec-compliance review, code-quality review, migration/rollback review, and final whole-diff review. Resolve and re-review every Critical/Important issue.

**Step 3: Protected PR A**

Push the feature branch, open Phase A PR, attach it to the task, enable native `--auto --squash`, and wait for required `backend-quality`, `webapp`, `provider-contracts`, and `bot-navigation` checks on the exact head.

**Step 4: Verify production Phase A**

After merge, verify exact merge SHA, Production Autodeploy success, health, migration head `052`, seeded category count/order, bounded read endpoints, dynamic legacy payloads, and zero enabled category-write endpoints. No paid runs.

**Step 5: Record release evidence**

Update the execution ledger with PR URL, merge SHA, CI/deploy runs, and live read-only results.

### Task 5: Phase B audited admin category mutations

**Files:**
- Modify: `artflow/api/trends_routes.py`
- Modify: `artflow/db/trend_category_repository.py`
- Modify: `artflow/core/trends.py`
- Test: `artflow/tests/test_trend_category_admin.py`
- Test: `artflow/tests/test_trend_category_visibility.py`

**Step 1: Write failing admin tests**

Cover admin-only create/rename/hide/publish/reorder/reassign; opaque key generation; 100-category and 80-character limits; duplicate title/key defense; full-set reorder; stale revision `409`; atomic contiguous order/revision/audit; grouped counts; unresolved legacy-tag preservation; dual-write of resolved stable tags; and no public trend leakage after hide.

**Step 2: Run RED**

Run: `python -m pytest tests/test_trend_category_admin.py tests/test_trend_category_visibility.py -q`

Expected: FAIL because Phase B mutation routes are absent.

**Step 3: Implement minimal mutation contract**

Add typed request/response models and admin routes under `/api/v1/admin/trend-categories`. Lock the catalog state row, validate expected revision, mutate and audit in one transaction, return the new revision, and leave client form recovery to the frontend on `409`.

**Step 4: Run GREEN**

Run: `python -m pytest tests/test_trend_category_admin.py tests/test_trend_category_visibility.py tests/test_admin_curated_trends.py -q`

Expected: PASS, including non-admin `403` and rollback-on-audit-failure cases.

**Step 5: Commit**

Commit message: `feat(admin): manage trend categories safely`

### Task 6: Phase B web/Mini App shelves, folder, and admin manager

**Files:**
- Modify: `artflow/webapp/src/lib/types.ts`
- Modify: `artflow/webapp/src/lib/api.ts`
- Modify: `artflow/webapp/src/app/App.tsx`
- Modify: `artflow/webapp/src/features/trends-screen.tsx`
- Modify: relevant existing Studio CSS files discovered beside `trends-screen.tsx`
- Test: `artflow/webapp/tests/ux2/trend-category-shelves.spec.ts`
- Test: `artflow/webapp/tests/ux2/consumer-completion.spec.ts`
- Test: `artflow/tests/test_apix_production_trends_surface.py`

**Step 1: Write failing browser tests**

At 320/390/768/1280 widths, require black/lilac vertical shelves, 3–5 live tiles, two-line titles, visible **Смотреть все** and **Повторить**, folder deep-link/back/scroll restoration, explicit **Показать ещё**, whole-catalog and folder empty states, later-page retry without losing loaded content, broken-preview-but-actionable cards, reduced-motion, viewport-only video playback, and admin create/rename/reorder/hide/publish/reassign with stale `409` form preservation.

**Step 2: Run RED**

Run from `artflow/webapp`: `npx playwright test tests/ux2/trend-category-shelves.spec.ts --project=chromium`

Expected: FAIL because shelves, folders, pagination, and category manager are absent.

**Step 3: Implement user slices**

Replace icon/chip filters with shelf sections, reuse the existing viewport-aware preview component, make the whole card and explicit CTA open repeat, and add resilient skeleton/error/empty/page states. Use route/query state compatible with refresh and back/forward. Add typed API methods; do not compute price on tiles.

**Step 4: Implement admin slices**

Add a clear category manager inside the existing admin-only Trends surface. Keep saved data visible during writes, disable duplicate submission, require hide confirmation for populated categories, and present stale revision recovery without discarding input.

**Step 5: Run GREEN**

Run from `artflow/webapp`: `npx playwright test tests/ux2/trend-category-shelves.spec.ts --project=chromium`

Run: `npm test -- --run && npm run typecheck && npm run build`

Run from `artflow`: `python -m pytest tests/test_apix_production_trends_surface.py -q`

Expected: PASS; inspect screenshots and browser console/network for all target widths.

**Step 6: Commit**

Commit message: `feat(studio): add live trend category shelves`

### Task 7: Phase B Telegram folder browsing and shared admin picker

**Files:**
- Modify: `artflow/bot/handlers/trends.py`
- Modify: `artflow/bot/services/trend_admin_flow.py`
- Test: `artflow/tests/test_trend_category_bot_navigation.py`
- Test: `artflow/tests/test_trend_admin_flow.py`

**Step 1: Write failing bot tests**

Cover eight-category pages, previous/next boundaries, open folder, category-scoped carousel, **Назад к категориям**, restoration of category page/index, empty/hidden category handling, dynamic admin picker, and rejection of stale/unknown callbacks without state corruption.

**Step 2: Run RED**

Run: `python -m pytest tests/test_trend_category_bot_navigation.py tests/test_trend_admin_flow.py -q`

Expected: FAIL because the bot still uses a global carousel and hardcoded category buttons.

**Step 3: Implement minimal bot parity**

Read the shared category repository, keep callback payloads under Telegram's byte limit, store page/category/carousel state in FSM data, and retain the existing trend-run and admin-create flows after selection.

**Step 4: Run GREEN and navigation regression**

Run: `python -m pytest tests/test_trend_category_bot_navigation.py tests/test_trend_admin_flow.py tests/test_bot_navigation.py -q`

Expected: PASS without hardcoded category UI sources.

**Step 5: Commit**

Commit message: `feat(bot): browse trends by category folders`

### Task 8: Integrated verification, review, and Phase B production release

**Files:**
- Modify: `artflow/docs/agents/EXECUTION.md`
- Modify: `artflow/docs/agents/trend-category-shelves-20261026.md` only if implementation evidence requires a truthful clarification

**Step 1: Full local verification**

Run full maintained Python/PostgreSQL-compatible tests, Ruff, migration upgrade, provider contracts, bot navigation, web unit/type/build, maintained browser suites, and focused four-viewport category journeys. Use isolated Playwright output directories to avoid artifact collisions.

**Step 2: Real-user audit pass**

Exercise zero/one/many categories, long Cyrillic/emoji titles, broken media, slow/error/retry pages, refresh/deep-link/back, reduced motion, touch, keyboard/focus, admin stale conflict, hide/run boundary, and non-admin write rejection. Inspect console, network, request counts, and off-screen media lifecycle.

**Step 3: Independent final reviews**

Run final spec review and @code-review-and-quality over the complete Phase B diff. Resolve every Critical/Important issue and rerun affected plus full gates.

**Step 4: Protected PR B and exact-head CI**

Push, open and attach the Phase B PR, enable native auto-merge with squash, and wait for all required exact-head checks and conversations to resolve. Do not use admin merge or direct main push.

**Step 5: Production proof**

Verify merge SHA equals deployed container/application revision, Production Autodeploy and public health succeed, shelf/category APIs and Mini App assets serve the new revision, ordinary users cannot mutate categories, administrators can access the manager, live tiles load/stop correctly, and Telegram folders navigate correctly. Use read-only/synthetic checks and no paid generation.

**Step 6: Final record**

Record PRs, merge SHAs, CI/deploy runs, migration state, surface parity (`site`, `mini_app`, `telegram_bot`), tests, live smokes, and any remaining non-blocking risk in `artflow/docs/agents/EXECUTION.md`.
