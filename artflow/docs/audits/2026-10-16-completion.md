# Completion of the APIX audit remediation

Baseline: `0da8798d42dafbe2ba721bebcb85fe186605026b` (released PR #278). Work is on `fix/audit-completion-20261016`. This report supersedes the open code items in [the first remediation](2026-10-16-remediation.md); release evidence is recorded in the PR after exact-commit CI and production verification.

## Finding resolution

| Original finding | Implementation and verification |
| --- | --- |
| Non-atomic T-Bank/Tribute refund | One transaction for status, wallet, credit ledger, original percentage-referral reversals and immutable refund event; signed HTTP + real disposable PostgreSQL tests reproduce storage failures and concurrent duplicates. |
| Partial refunds and late statuses | Distinct authorization release/captured refund handling; cumulative partial refunds, stale suppression, monotonic failure transitions, retained early full-refund notices. Status-check paths use atomic confirmation/refund. |
| Static Tribute product mapping | Typed versioned DB catalog, immutable retained offer terms, actor audit, authenticated API and browser editor, shared site/Mini App/bot projection. Read-only supplier verification and price mismatch rejection. |
| Full historical pytest | Every original failure classified against current product/provider behavior; real regressions repaired and stale fixtures/contracts updated without disabling tests. Full pytest replaces the selected-file backend gate. |
| Previous PR #278 fixes | Trend runner, callback privacy, OpenAPI security and provider exposure remain intact and included in the full regression gate. |

## Historical test classification

**Real defects found during completion:** the legacy bot menu omitted app/trend/admin entries; it now delegates to the canonical builder. Seedance reference support changed `VIDEO_SPECS` but not the `MODEL_SPECS` read by the payload builder; both now reference the same patched specification, preserving the documented `reference_video_urls`. Lowercased legacy trend quality tags (`4k`) failed whitelist/pricing resolution; known quality values are canonicalized before lookup. Receipt parsers truncated fractional integers and accepted Boolean IDs/amounts; they now reject malformed values.

**Superseded UI contracts:** production is `main.tsx`/native App, not the older V4 entry or Vite source-transform snippets. Tests now cover explicit legacy gating, feed-first navigation, bounded pagination, category filters and shared trend runner. The bot is task-first with a unified model-family selector; reference input selects the edit provider behind that family. Help text and model labels follow current shipped guidance. Share links use the configured public app route. No production UI was reverted to an obsolete snapshot to satisfy tests.

**Provider contracts:** current Gemini Omni durations, Veo provider-managed duration/material-reference metadata and GPT Image square-4K behavior are verified at the present adapter seams. Wan's intentional no-model-substitution fallback and Seedance's no-ambiguous-paid-replay rule remain enforced. The Seedance reference assertion was kept against official plural-field documentation; the registry bug was fixed rather than accepting a lost video reference.

**Privacy/ownership contracts:** public feed output uses bound WebP previews rather than raw URLs, and prompts remain hidden. Library/trend IDs select the canonical server recipe, not the visible placeholder. Recipe repeats use reader references, not the creator's finished face. Own-work Blend tests explicitly provide two reader inputs and preserve parent attribution; they do not grant another reader access to a private recipe.

**Test isolation:** async SQL execution fakes now return synchronous Result methods, preventing fake truthy unlimited entitlements; new referral ledger reads have explicit mocks; rate-limit Redis is per-test while the actual throttling decision remains exercised. Migration tests use the dedicated loopback DB and current single Alembic head. Missing `aiosqlite` was an environment dependency, restored from pinned dev requirements.

## Checks recorded during implementation

- Full suite after initial remediation: **3414 passed, 2 skipped** (only the optional local Nginx image tests at that point), with existing dependency/mock warnings. Later strict-parser tests and final release checks are additional; use final PR evidence for the final count.
- Financial/referral/catalog/migration subset after hardening: **114 passed**.
- Actual migrations 045/046: upgrade, guarded downgrade and re-upgrade preserve original monetary/plan values and administrative/refund evidence.
- Browser catalog tests: **3 Desktop scenarios passed**; frontend units **114 passed**, typecheck/build passed.
- Full Ruff, compileall and JS syntax checks passed.

The repository has no new real provider payment/refund fixture. No paid AI generation, external refund request, manual customer compensation or direct production source/config change was performed. Existing legacy refund inconsistencies, if any, are not guessed or silently backfilled. Release is complete only when the exact merge SHA passes CI/autodeploy and running-source/health checks.


## Final local pre-PR verification

- Full release gate with disposable PostgreSQL and official Nginx image: **3454 passed, no skips**, 3 warnings (one dependency deprecation and two existing AsyncMock lifecycle warnings). Log/JUnit recorded outside the repository; no production data included.
- Full Desktop Playwright suite: **58 passed**, including the 3 new catalog scenarios; frontend unit: **114 passed**. Production-mode build and TypeScript check passed in the browser runner.
- Fresh-process provider inventory/readiness/dry smoke: **98 contracts**, no paid execution.
- OpenAPI: **195 paths**; two independent JSON and Markdown exports matched byte-for-byte.
- Full Ruff, compileall, JS syntax, deploy shell syntax and whitespace checks passed.

Protected PR review, exact-head GitHub checks and merge-SHA production verification remain required. No completion statement is based solely on the local green gate.


## Independent PR #279 review follow-up

The first independent code review on `4c28376` identified five P2 issues; the security review had no findings. All five were reproduced and corrected before merge: Lava event-only success reconciliation; net revenue after partial refunds across every reporting surface; actionable safe rejection diagnostics; ledger-proven legacy partial refunds; and refund-aware bot status text. Seven new regression cases exercise these boundaries, including real PostgreSQL-backed web/Mini App/referral revenue reports. The assistant report fixture now explicitly marks its already-paid transactions as paid, preserving the original 400-RUB assertion.

After the amendments: **3461 pytest passed, zero skips**, with the same three dependency/mock warnings; full Ruff, compileall, JavaScript/deploy-shell syntax and whitespace checks passed. Schema remains `046_tribute_catalog`; no new migration or public request contract was introduced. Exact amended-head CI and independent re-review remain the release gate.
