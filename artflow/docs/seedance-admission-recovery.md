# Native admission rejection and Seedance fallback

> Historical PR #281 evidence. The current contract is [fenced admission recovery](seedance-presubmit-recovery.md). A UUID-only 503 is no longer fallback authority; versioned opt-in receipt and durable upstream key fencing are required. The post-preparation handoff placement and lost-commit-ack recovery below are retained.

## Incident and scope (2026-10-18)

Production APIX `0da8798d42dafbe2ba721bebcb85fe186605026b` kept new Seedance 2.5 requests at a Neironych submission-unknown marker after HTTP 503. Fresh gateway logs identified `native_inference_rejected`, stage `provider_capital`, before any paid supplier work. Qwen photo-to-prompt requests failed at the same stage. Healthy containers and public HTTP health were not evidence of successful generation.

This repair changes APIX response classification and the existing Neironych-to-KIE handoff. It does not bypass provider capital checks, erase procurement holds, change tariffs, manually alter customer balances, or replay old unknown jobs. The separate audit completion PR is not part of this release.

## Verified upstream contract

Source: `Bambale0/ooo@50963d35033497d5014b830bf3a1eda263d72402`, `app/inference/router.py:inference`, `app/inference/service.py:reserve`.

The gateway locks the partner and checks an existing idempotent generation before capital admission. Admission failures return FastAPI's exact JSON object `{"detail":"provider_temporarily_unavailable"}` with HTTP 503 and a diagnostic UUID in `X-Request-Id`. Video acceptance returns 202 and a generation request ID. Synchronous errors after admission use a different `error` envelope with a generation request ID. This distinction is essential: a generic 503 never proves that no paid request exists.

`api/neironych_admission.py` recognizes only the exact detail-only object, `application/json`, HTTP 503, a canonical UUID trace and one of the two known native POST paths. Extra fields, missing/invalid traces, HTML, malformed bodies, 502/504 and downstream error envelopes remain ambiguous. Provider 404 during reconciliation remains nonterminal; no second paid POST is inferred from a missing lookup result.

The Seedance client logs the safe local request UUID and gateway trace UUID for a classified rejection. The Qwen client records `failure=admission_rejected` plus the same safe trace. Request bodies, prompts, media URLs and credentials are not logged by the new code.

## Durable fallback

The existing configured routing policy remains authoritative. A proven Neironych admission rejection may use the already-configured KIE backup once. Photo prompt and assistant similarly use their existing database-backed provider order; no new model substitution is introduced.

All three Seedance KIE submission sites (Seedance 2, current Seedance 2.5 wrapper, legacy Seedance 2.5 wrapper) now call the existing durable handoff immediately after local payload preparation and before the paid KIE POST. The repository compare-and-swap admits only the exact still-submitting Neironych attempt, persists `kie-submit:<generation_id>`, and marks the old journal `definite_rejected_fallback_kie`. Accepted KIE IDs bind through the KIE journal rather than the old Neironych journal. A duplicate handoff, stale/unknown attempt or failed persistence cannot launch another KIE job.

The legacy KIE-primary path is deliberately unchanged: it has no Neironych journal to transfer. Existing reverse fallback and unknown-outcome handling remain in force. Old unknown requests are not automatically replayed; the existing per-generation reconciliation/refund scheduler continues to own them.

## Verification evidence and limits

- Initial classifier regressions: 3 expected failures before the fix, 22 negative cases already safe.
- Real local SQLite pipeline exposed all 3 missing journal call sites before the handoff fix.
- Revised focused set: 136 passed, including 34 new classifier/pipeline cases, timeout and failed journal persistence, existing unknown-submission, Wan handoff and multimodal contract cases.
- Cross-repository ASGI probe against the exact gateway source: capital-rejected Seedance/Qwen requests created zero generation rows and zero paid upstream calls; already-admitted video replay still returned the same 202 even after capital became unavailable. Together with existing gateway diagnostics: 18 passed. This was a local synthetic probe, not a production POST.
- Full application Ruff and changed Python compilation/whitespace checks passed.
- Maintained backend local run: 2036 passed, 2 stopped by the test-database name safety guard. The disposable DB had a different name than the guard requires. A subsequent DB-setup command and a further local test command were blocked before execution and were not retried. Exact-head GitHub CI, using its existing dedicated PostgreSQL service, remains mandatory before merge.

No live paid AI request or bank operation was performed. Supplier availability and a real completed render require separate runtime evidence; synthetic tests must not be reported as a live result. No schema migration or new business configuration is introduced.

## PR review: failed handoff and uncertain journal commit

Review identified that a KIE handoff failure initially propagated the pre-submit exception even though the Neironych attempt was already marked started. The normal pre-submit handler correctly refuses to refund a started context, so that path did not immediately record the recovery marker. The existing scheduler does select Neironych submission prefixes and has a bounded timeout, but explicit reconciliation state was missing.

The fallback-only helper now routes failed admission persistence into the existing unknown-submission handler. That handler preserves a KIE journal when its COMMIT succeeded but the acknowledgement was lost, using the persisted exact generation/client identity instead of the in-memory flag. It never overwrites a bound or terminal task. Neither path launches another provider request or manually refunds an unverified attempt.

RED/green evidence: all 3 real Seedance handoff tests first failed to reach the recovery path; a fourth test reproduced a committed KIE journal with lost acknowledgement. After the fix, 115 focused admission/unknown/handoff/callback tests passed. The new regression file now contains 35 cases. The first revision's four required GitHub checks all passed; the revised exact-head checks must run again before merge.
