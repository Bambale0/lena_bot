# Seedance uncertain submission handling

An upstream `pending` response carrying `submission_outcome_unknown` is **not a rendering queue** and is **not proof of a free failed request**. The native adapter raises a typed nonterminal review signal. The reconciler persists the signal once, without credit or provider-charge mutation, using a generation-row lock and the expected provider task identity.

## New submissions

Redis keys are scoped to environment and Seedance product model. An unresolved response opens/refreshes a pause of `SEEDANCE_UNCERTAIN_ROUTE_COOLDOWN_SECONDS` (default 1800, range 180..86400). The normal scheduler checks every 90 seconds; while explicit unknown responses continue, the pause refreshes. The PostgreSQL active-review marker is authoritative when a Redis key is absent. A failed Redis write, cache loss or expiry cannot reopen admission while that marker persists; a database-read failure fails closed. Once those jobs are finalized the key expires. No automatic provider probe submits paid work.

`submit_seedance` reads this gate **before** starting the Neironych primary. If paused, new work is sent once to existing KIE for the same model. If KIE fails, the paused Neironych route is not retried. An unavailable Redis admission check fails closed before any new paid provider POST. This is a model-level mitigation, not a promise that an external provider cannot fail; there is an observation window before the first unknown result is polled.

## Existing uncertain jobs

They are never replayed/fallback-submitted. They remain financial holds until an operator settles them from provider evidence or approves a customer refund under the existing financial procedure. Provider-side procurement reconciliation and customer refunds are separate operations; a 503 alone never authorizes writing `not_accepted` or freeing procurement liability.

The private marker `neironych_video_reconciliation.required` produces public status `reconciliation_required` for still-active jobs. Terminal DB status always wins. Standalone web REST GenerationCard, landing-site JavaScript, Mini App, legacy/V4 UI and realtime events show review rather than fake progress/success. Browser polling stays nonterminal so a later recovered completion remains visible.

Telegram receives one durable `reconciliation` notice per generation via the existing lease/token/retry outbox. It explicitly says credits remain held and directs cancellation/refund requests to support. No raw provider response is exposed. Immediately before sending a nonterminal notice, its current DB status, provider identity and claim token are revalidated; an already replaced terminal notice suppresses the obsolete message. Final `done`/`failed` transitions replace that review notice using existing transactional guards; an obsolete acknowledgement cannot erase a newer terminal notice. Website-origin generations do not send Telegram notices.

## Verification and rollback

Dedicated runtime, routing, identity, idempotency, no-refund, notice-replacement and all-surface serialization tests live in `tests/test_seedance_uncertain_submission.py`. Browser smoke covers processing -> review -> completion and asserts no paid replay or false success toast. Existing Seedance/outbox/refund suites remain in CI.

No SQL migration, price edits, key changes or manual ledger writes. Revert the PR via normal release path to roll back; private markers remain inert with old serialization. Circuit keys expire automatically. Never delete user generation rows to clear a hold.

## Lost create responses (new submissions)

New ordinary Seedance 2/2.5 attempts allocate a client UUID before dispatch. The
validated Neironych request runs a one-shot repository callback immediately before
POST. It commits the UUID, idempotency key, normalized-payload SHA-256, model and
start time in existing generation JSON, with a reserved `neironych-submit:` local
identity (`web:` remains preserved). This identity is never used as a provider ID.
No migration or backfill is required; historical missing-ID rows are not modified.

The client sends `X-Client-Request-Id` and the original `Idempotency-Key`. A lost
response, malformed success, missing ID, unrecognized rejection or HTTP 5xx raises
a typed ambiguous outcome. Neither primary nor fallback routing may turn that
outcome into another paid POST or an ordinary refund. Existing task-identified
uncertainty handling remains in force. Fallback remains available for validated
local rejection or explicitly verified no-work admission error codes.

An admission-persistence failure before POST is separately typed. Only a fresh
locked active row with no identity, or this same attempt's local identity, can use
the existing atomic failed/refund operation. An existing/superseded attempt is
ambiguous, not refundable. `update_generation_task(expected_task_id="")` means
compare-and-set only when the stored identity is NULL or empty; a KIE result may
not overwrite a concurrent unknown/bound/terminal attempt.

The existing scheduler and status read perform the documented authenticated GET
`/api/v1/generations/by-client-request-id/<UUID>`. The response must match UUID,
model and idempotency key before its real provider ID can be bound under an active
row/expected-attempt lock. Then existing native video polling, single-winner
completion/refund and delivery outbox apply. A late submit response cannot replace
a task already recovered or finalized by another worker.

A 404 is not proof that no job was accepted. Transport errors, 5xx, malformed or
mismatched lookup responses keep the charge held and the visible nonterminal
review state. The bounded scheduler retries read-only lookups at its existing
configured cadence; it never retries POST. Existing overdue alerts expose cases
that require operator investigation. Automatic completion requires authoritative
provider evidence and is not guaranteed while the provider remains unavailable.
Only confirmed terminal failure of the correctly identified native task allows
refund. No historical balances or attempts are altered by this rollout.

Contract source: https://api.xn--e1aikcel5c5a.online/docs (retrieved 2026-10-09).
MockTransport and synthetic SQLite regressions cover accepted-then-lost responses,
restart recovery, 404/5xx holds, identity mismatch, web suppression, pre-POST
failure, duplicate/stale binding and exactly-once terminal settlement. These tests
do not establish live provider availability or PostgreSQL concurrent-lock behavior.
