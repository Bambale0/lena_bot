# Restore repeat personalization

Baseline: e849b812.

Existing UI/draft/change_request contract is reusable. Creator video replay hides the editor and rejects edits since 1ae900fa2. Restore the editor and carry changes as a server-side suffix, without exposing or mutating the author prompt, changing media provenance, model or accounting. Shared web/Mini App runner is affected; Telegram feed cards already link to the same prelaunch editor, and the native Seedance result editor remains available.

1. Reproduce with quote/launch API regressions and browser draft/price regression. In progress.
2. Minimal UI/API restoration; no configuration or migrations.
3. Focused regressions, build, PR checks and auto-deploy verification.

Acceptance: visible personalization before launch; clothes, hair and digits survive reload/checkout and reach provider; private author inputs remain private; plain repeats remain unchanged.

Verified: API regression red on both v1/web (422), browser regression red (editor absent); after fix 283 focused Python tests, 44 Desktop e2e scenarios and personalized replay on all four browser profiles pass. Build/typecheck run by Playwright webServer; Ruff and diff whitespace clean. Native Telegram feed card WebApp entry test passes; dedicated native result editor unchanged. No migrations/configuration changes. Provider I/O is synthetic in tests; no paid generations.

Review: preserve author recipe/model/input videos, suffix user changes server-side only, preserve existing 800-character validation and scoped draft/payment guards; no private prompt returned. Root cause is 1ae900fa2 creator-replay guard in API and corresponding UI suppression/reset.

PR #337 review follow-up: native text-bot feed repeat now collects reader changes before quote; shared prompt builder validates combined model limit before charge and preserves idempotent reconfirmation; photo-free claim removed. Added regressions first: native editor absent/changes ignored and Seedance/Kling combined limit not rejected, then verified green. Updated disclosure-opening test steps to assert the now-always-visible field without changing payment assertions.
