# Seedance and Qwen: rejected admission versus lost submission response

## Incident and contract

On 18 October 2026, production logs correlated Seedance 2.5 and Qwen photo-to-prompt failures with the native gateway's `provider_capital` stage. The gateway rejected these requests before creating/dispatching generation work, but an ordinary HTTP 503 was indistinguishable from a lost response after paid acceptance. APIX conservatively held video tasks for reconciliation and did not use the configured Qwen backup.

The native gateway now emits a receipt only after rollback of a typed capital-stage admission rejection:

- HTTP 503 with exactly `{"detail":"provider_temporarily_unavailable"}`;
- `X-Submission-State: not-accepted-v1`;
- `X-Client-Request-Id` equal to the outbound invocation ID;
- `X-Idempotency-Key-Sha256` equal to SHA-256 of the outbound idempotency key.

`api/neironych_admission.py` verifies all fields. Seedance 2/2.5 can then take the existing equivalent KIE fallback. Qwen returns a definite `admission_rejected` error so the existing text/photo routing can take its configured backup. No model, tariff or routing priority is changed.

## Safety and persistence

A missing, unrecognized, malformed or mismatched receipt remains ambiguous. Generic 503, timeout, missing success ID and 404 lookup are not fallback authority. Old provider deployments remain fail-closed. Already submitted historical jobs are not replayed and financial reservations are not manually deleted.

For Seedance's Neironych-to-KIE fallback, the existing durable `before_kie_submit` hook is now called by the routing layer before the second provider path. It changes the original attempt journal to `definite_rejected_fallback_kie`, commits KIE's single-use intent and retains signed callback correlation. This preserves one user generation and one existing charge across bot, site and Mini App. Lost KIE replies remain recoverable by the signed callback; duplicate launches cannot re-enter either provider.

No schema migration, production price edit, historical wallet repair or paid provider smoke is part of this patch. Procurement holds stay intact and still need evidence-based reconciliation by their owning system. HTTP mock plus durable SQLite tests cover the incident, mismatched receipts, all three caller surfaces and duplicate submissions. Existing PostgreSQL/concurrency gates remain enabled in CI.

## Concurrent retry safety

The client explicitly opts into terminal rejection semantics with `X-Submission-Receipt: v1`. The gateway rolls back the rejected admission, re-locks the existing partner/idempotency boundary and checks again. If a concurrent request was accepted, it returns that accepted identity without a rejection receipt. Otherwise it commits an unbilled terminal idempotency tombstone before emitting the receipt; that logical key can never later create paid work. A new user action uses a new logical key. Legacy consumers without the opt-in retain the original retryable rejection contract. The receipt is provider-agnostic for typed pre-acceptance service-unavailable failures, not a disclosure of a procurement stage.
