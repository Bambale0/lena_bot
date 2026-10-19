# Wan 3.0 / Prime public-feed repeats

## Incident and repaired path (19 October 2026)

Baseline `f1cfa8eb2797d825389df4c5819ed504956adae8` allowed the public-feed path to price/debit a generic video request, then call the Wan service without its required `Wan30Request`. The service correctly rejected before a supplier call. The reported source was 61270; previous diagnostics found failed repeats for a different account, not proven paid failures by the requested reader. This repair is model-wide; no account IDs, special-case source IDs or production media are embedded in the code/tests.

Both `/api/v1/feed/{id}/remix/quote` and the corresponding web proxy now use the existing strict Wan constructor and exact active quality tariff. The paid endpoint remeasures the same local inputs, rechecks that tariff and requires the displayed quote to match **before debit**, even without input-video references. Missing input, disabled quality/base pricing, invalid media/combined duration and changed/missing quote cannot reach spending or the provider. Storage/probe failure is a retryable 503, not a charged generation.

The accepted request and billing snapshot are persisted before provider submission. `wan_request` reaches the existing service; its defensive guard, signed callbacks, durable Neironych/KIE journals, unknown-outcome recovery and idempotency behavior are retained. No new provider route or paid retry was added. The request is never reconstructed from a supplier GET.

## Recipe and surface parity

`wan30_request` is authoritative for a known public Wan video. All original video references and timed audio are remeasured, ordered and deduplicated by the shared constructor. Original mode, resolution, ratio, fixed duration, audio flag, seed (including zero) and safety setting are retained. Reader photos replace creator image/frame identity inputs. First/last-frame recipes require exactly their original frame count; reference recipes do not silently become first-frame mode just because only one photo was uploaded. The source's published output MP4 is never substituted for its original input recipe.

Source reference audio/file/link fields remain server-side. Public quote/results contain no creator prompt or private reference URLs. Existing publication/model/reader-photo authorization rules remain in place. Legacy generic inputs still pass the strict Wan constructor; missing or unsupported provenance is not fetched from the supplier or invented.

The website and Mini App use the same handlers and schema. Telegram public-feed preparation uses the same pure recipe restoration helper, then the existing one-time quote confirmation and launch. Local values captured from the old UI draft are refreshed before quoting. Re-entering confirmation preserves the original seed instead of treating it as a new user control. Own-history repeats and non-Wan models retain their existing paths.

## Verification and delivery boundaries

- HTTP regressions first reproduced the exact original `wan_request` exception for normal Wan and Prime. Separate RED cases reproduced missing immediate pre-charge I/O handling and incorrect Telegram `multimodal` restoration.
- 30 new backend cases exercise real HTTP routes, normalizer, Wan builder, strict tariff lookup and video service; external media probes, persistence and supplier calls are synthetic. Coverage includes web/Mini App, Telegram preparation/visible confirmation, private prompt/reference exclusion, edit/reference/frame/file/link modes, multiple measured/deduplicated inputs, stale prices and unknown paid outcomes without refund/replay.
- Initial full local suite: 3459 passed, 64 environment-dependent skips, zero failures. The added final three tests also pass. The normal exact-head GitHub backend job must run its dedicated PostgreSQL/Nginx tests; skips are not proof of those integrations.
- Frontend unit: 114 passed. Fresh typecheck/production build and 8 new Wan/Prime browser scenarios passed in iPhone SE/iPhone 13/Pixel 5/Desktop Chromium emulation. Browser endpoints are mocked; this is not a paid render or a physical-device test.
- Full Ruff passed. OpenAPI export still matches the committed 195-path schema. Provider inventory/readiness/dry smoke manifest remains valid for 98 contracts, no paid execution.

No migration, new business configuration, price/model routing change, customer compensation or manual production update is required. Ship only via reviewed PR and the normal protected-main autodeploy. Production identity/health and a new real paid render are distinct verification steps; a paid render was not executed by this work.

## Review amendment: unknown source provenance

Independent review found that a public legacy Wan video without a recognizable input snapshot could enter the generic public-output editing fallback. Both API quote/launch and Telegram preparation now reject this case before probing, quoting or charging instead of silently substituting the rendered output. Known canonical recipes (including source 61270) and recognizable stored inputs still use the normal path; own-history operations are unchanged. Eighteen RED cases covered both Wan models, both HTTP surfaces, Telegram and missing/empty/malformed snapshots; all pass after the guard. New regression total: 48. Related post-amendment suite: 232 passed. No paid generation or customer balance mutation.

The second review finding (Telegram transient media-probe errors) is fixed with the same safe pre-charge retry outcome as HTTP. Four RED/green cases cover OSError and RuntimeError on both Wan variants; the bot returns a retry message without spending, saving a generation or calling a supplier. The regression module now has 52 cases. No exception body/private media URL is included in the new log line.

### KIE submission marker reconciliation (2026-10-19)

The `kie-submit:<generation_id>` journal marker (including `web:`-prefixed
variants) is **not** a provider task ID. Status reconciliation must keep the
paid order pending until the canonical provider task ID is bound by the
submission response or signed callback. Never call KIE status polling with
this marker, never resubmit paid work merely because the marker is pending,
and do not refund on a malformed status response. Regression coverage:
`tests/test_wan_kie_submit_reconcile.py`.

### Follow-up: bind KIE-only successful feed submissions

Baseline: `362069e887bd3c289a3a6af32eb946481f1c588f`. The authorized
production repeat smoke exposed a second, independent omission: the feed
success path checked only the Neironych `started` flag. A KIE-only submission
sets `kie_started`, so its response went through the legacy empty-ID update
instead of the durable KIE binder. The paid task remained recoverable by its
signed callback, but polling could not start until that callback arrived.

Acceptance: both Wan models on web and Mini App must bind the successful KIE
response immediately through `has_paid_submission_journal` and the existing
`persist_submission_result`; deferred/failed binding must never resubmit or
refund paid work. Telegram and ordinary video creation already use this
shared guard. No pricing, provider, migration or authorization change.

Execution: add failing route regressions for both models and HTTP surfaces,
including deferred and failed identity persistence; apply the minimal guard
correction; run regression/CI gates; deliver through protected-main auto-
deploy; verify canonical task binding and actual paid render completion.

Verification: all 12 new model/surface/binding-outcome cases failed on the
baseline because the durable binder was never called. After replacing the
one success-path condition with the existing shared journal predicate,
233 Wan/fallback/callback/delivery/refund tests pass and full application
Ruff passes. Both Telegram launch sites already use that predicate; no bot
code change is necessary. Late callbacks and persistence failures remain
single-purchase, recoverable operations. Paid production verification and
exact merge/deploy receipts are recorded in the follow-up pull request.

The full local Python suite for this follow-up completed with 3498 passed,
64 environment-dependent skips and 3 warnings. It used dummy credentials,
not production data. Exact-head CI remains mandatory for the skipped
PostgreSQL/Nginx integrations; local results never bypass protected checks.
