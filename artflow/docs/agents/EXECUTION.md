# Execution ledger — history pagination hardening (follow-up to 54507df)

Baseline: c2eb7ac (main, clean tree). Target of prior review: 54507df.
Scope approved by user: Fix everything (H+M+L).

## Current state
- `GET /api/v1/history` supports `limit`+`offset`; repo orders
  `desc(created_at), desc(id)`; mini-app `getHistory()` pages to completion.
- `docs/miniapp_api.md` updated; `docs/openapi.*` stale (no `offset`).
- `GET /api/web/history` has `limit` only, no `offset` (site parity gap).
- `/me/feed` capped at `le=1000`, client fetches 500 (intentional heavy-card cap).
- Telegram bot history capped at 10/message (intended UX cap, undocumented).
- No composite index for `(user_id, created_at DESC, id DESC)`.
- `_reconcile_user_active_generations` runs on every `/history` page.
- `getHistory()` has no page ceiling and no zero-new-ids break; one failed
  page rejects the whole bootstrap history to `[]`.
- `refreshCore` returns an abort cleanup nobody consumes (dead code).
- `.gitignore` has blanket `*happyfox*` / `*happy-fox*` globs that would hide
  future source files (verified via `git check-ignore -v`).
- Surface test only asserts substrings; no behavioral pagination tests.

## Acceptance criteria
1. H1: bounded paging loop (page ceiling + zero-new-ids break).
2. H2: partial history preserved on mid-stream page failure (error logged).
3. M1: reconcile provider polling only for `offset == 0`.
4. M2: composite index in model + guarded Alembic migration 033.
5. M3: `docs/openapi.json` + `docs/openapi.md` regenerated.
6. M4: site parity — `offset` on `api/web/history.py`; explicit documented
   exceptions for `/me/feed` cap and Telegram 10-item cap.
7. M5: behavioral tests (statement shape, stable order, offset pass-through,
   reconcile gating, 422 on bad limit, web offset).
8. L1/L2/L3/L4: bounded merge + abort-ref fix, template-literal + exported
   constants, narrowed `.gitignore`.
9. `py_compile` + focused `pytest` green; `tsc --noEmit` green (if available).

## No-hardcode / control-plane
- `HISTORY_PAGE_SIZE` / `MAX_HISTORY_PAGES` / `MAX_HISTORY_ITEMS` stay
  client-side fetch tuning constants, not business rules. No new env vars.
- No prices, tariffs, prompts, routing, or permissions changed.

## Observability
- Per-page history failure logs via `console.warn` with page offset; partial
  results preserved. Reconcile path unchanged apart from gating.

## Test seams
- `tests/test_history_pagination.py` uses `AsyncMock` session + statement
  capture (no DB needed, following `test_repository_feed.py` pattern) plus
  direct handler invocation and `httpx.ASGITransport` client tests.

## Steps
1. [x] Preflight audit + skill search (code-reviewer agent doc applied).
2. [x] Frontend `api.ts` hardening (H1/H2/L3).
3. [x] `App.tsx` merge cap + abort fix (L1/L2).
4. [x] Backend reconcile gating (M1) + web offset (M4-site).
5. [x] Model index + migration 033 (M2).
6. [x] `.gitignore` narrowing (L4) + doc comments (M4 exceptions).
7. [x] Regenerate OpenAPI (M3) — surgical patch; full regen abandoned
   (committed file has 49 paths vs live 175; full regen would be a 14k-line
   unrelated diff, so only /api/v1/history + /api/web/history +
   /api/v1/me/feed entries were synced via build_markdown on the 51-path file).
8. [x] Tests: update surface asserts + new behavioral file (M5).
9. [x] Verify: py_compile OK; 7 new + 49 related + 84 extended green;
   tsc --noEmit exit 0; test_webapp_routes 12 failures proven pre-existing
   via clean-HEAD worktree (12 failed / 78 passed both before and after).
10. [ ] Final report with per-contour parity table.

