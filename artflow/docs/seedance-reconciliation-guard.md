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
