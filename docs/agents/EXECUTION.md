# APIX execution ledger

## 2026-10-25 — production trend repeat recovery

- Baseline: `8e0384f5d6885153508a184fd33ea8464d809e5d` (`origin/main`).
- User outcome: public users can stay on the selected Mini App tab and repeat every published trend with an exact server price and a retry-safe launch.
- Confirmed production failures:
  - ordinary-user polling forces the active tab back to `feed` every five seconds;
  - nine public Seedance 2.5 trends store a pricing variant as the model key;
  - 10-second 720p trends quote the 7-credit per-second rate as a flat total instead of 70 credits;
  - launch rejects the pricing variant as an unknown runtime model, then rollback-expired ORM state masks the useful rejection as HTTP 500;
  - failed pre-submit attempts leave `running` trend claims without a generation, so retries return conflict.
- Safety: no provider submission or credit charge is needed to reproduce or verify the failures. Existing public prompt text and user media stay untouched.
- Configuration decision: canonical runtime model and resolution remain separate, typed settings. Prices continue to come from active database tariffs; no price is hardcoded.
- Surfaces:
  - `site`: shares the web application and API; verify navigation and trend API behavior.
  - `mini_app`: primary affected surface; verify mobile navigation, quote, upload, launch contract and friendly errors.
  - `telegram_bot`: shares trend records/admin publishing; verify model selection only offers canonical runtime models and existing trend entry remains compatible.
- Data rollout: add an idempotent migration that converts affected trend model keys to their canonical model and preserves the resolution in trend tags. Running orphan claims with no generation are released only for the affected invalid-model trends.
- Observability: keep structured trend id/user id/failure type logging while preserving the original HTTP error; never log prompt text, init data, or media contents.
- Test seams: FastAPI route tests with provider calls mocked below the submission boundary; Playwright navigation test with controlled `/me` polling; bot admin selector unit test; migration SQL assertions.
- Acceptance criteria:
  1. Seedance 2.5, 720p, 10-second trend checkout returns `70` credits.
  2. Launch uses canonical model `bytedance/seedance-2-5` and resolution `720p`.
  3. Any pre-submit rejection releases its claim and returns the intended 4xx response, not 500.
  4. Ordinary-user polling preserves the selected tab; permission revocation still exits restricted Studio modes.
  5. Admin web and Telegram selectors cannot persist pricing-variant keys as runtime models.
  6. Existing affected production trends and their orphan claims are repaired by migration.
  7. Required local checks, GitHub gates, production autodeploy, exact-SHA host state, health and live read-only smoke checks pass.
- Progress:
  1. [x] Production evidence and root causes captured.
  2. [x] Regression tests failed for all confirmed behaviors before implementation.
  3. [x] Minimal backend, frontend, bot-admin and migration fixes implemented.
  4. [ ] Focused and full maintained checks pass.
  5. [ ] Open code review has no unresolved high-severity findings.
  6. [ ] PR merged through required checks and auto-merge.
  7. [ ] Production exact-SHA and live behavior verified.

- Local verification completed:
  - focused backend/migration suite: 34 passed, 2 PostgreSQL-only skipped;
  - web unit suite: 126 passed;
  - production frontend build and TypeScript check: passed;
  - full Playwright Mini App smoke: 340 passed; strengthened tab-refresh regression: 4 passed;
  - Ruff application check, Python compileall and provider-contract inventory: passed.
- Independent code review: no remaining P0/P1/P2 findings after the 5xx
  idempotency guard and asynchronous tab-refresh test were strengthened.
- Local full pytest note: the Windows run completed but retains pre-existing POSIX,
  Docker/Nginx-fixture and generated-site contract failures. The required Linux
  `backend-quality` gate with disposable PostgreSQL remains authoritative and pending.
