# Payment refunds and the Tribute catalog

## Accounting boundary

`db/payment_refunds.py` owns refund status, customer credit ledger, percentage-referral reversals and immutable refund events in one PostgreSQL transaction. It locks the payment identity even when the local transaction does not exist, then the transaction and affected user rows in ascending ID order. Duplicate and stale cumulative snapshots do not change a wallet. An interrupted write rolls the whole operation back. Negative customer balances after a legitimate refund are allowed: spent purchased credits must not turn a real refund into a free balance.

T-Bank `REFUNDED` reverses the remainder of captured funds. `PARTIAL_REFUNDED` is accounted as a cumulative refund using the remaining transaction `Amount` in minor currency units and the original stored payment amount; the `Amount` of a **Cancel request** is a requested delta and is not this input. `REVERSED` / `PARTIAL_REVERSED` describe authorization hold release, not captured-wallet refunds. Late failure events may change only `pending`, never `paid` or `refunded`. The status-check button uses the same accounting functions as callbacks; it no longer confirms a status and adds credits in two commits.

Amounts must be finite and bounded; Boolean, fractional minor-unit, negative and malformed values are rejected. A partial refund before a confirmed local payment returns a retriable error. A verified full refund before creation/confirmation is retained in `payment_refund_notices`, preventing a later confirmation from crediting it. An old already-refunded transaction is not debited again: historical two-commit inconsistencies need independent reconciliation, not a guessed automatic correction.

Percentage referral reversals use the original ledger recipient/rate/amount, not today's referral chain. Late accrual is serialized with refund, cannot resurrect a full refund, and is prorated after a partial refund. The existing first-topup credit-bonus policy is unchanged; its row-lock order is aligned to avoid deadlocks. Notifications happen outside the refund transaction. This release does not send merchant refund requests or alter a customer's balance manually.

## Tribute product administration

Open **Admin → Catalog Tribute** in the Telegram bot, or **Account → Admin → Pricing → Products Tribute** on the site. Both open `tribute-admin.html`. The same catalog feeds site, Mini App and bot checkout projections.

- `GET /api/web/admin/payments/tribute-products` lists retained offers.
- `PUT /api/web/admin/payments/tribute-products/{product_id}` validates and stores an offer.
- Server-side admin authentication is mandatory (Telegram initData or website session). The form itself grants no permission.

The request includes `plan_key`, canonical `payment_url`, `currency="usd"`, positive integer `amount_minor`, `enabled` and `expected_revision` (0 when creating). Enabled offers are verified with Tribute's read-only product API before database locks are taken. The plan supplies the credits and RUB accounting value; secrets remain environment configuration and never enter this catalog.

Every write records the actor, previous/current offer and revision. A stale revision returns 409. At most one offer per plan is active. Replacing an offer retires, rather than deletes, the old product ID. Economic terms are immutable for an existing product ID: use a new provider product for a changed amount/credit package. Disabling an old offer remains possible after the current plan changes. A plan/offer mismatch removes that offer from new checkout without changing old purchase terms. Delayed signed receipts use their retained offer, including retired offers and inactive plans.

A timeout does not prove that an admin save failed. The form does not auto-retry; reload the catalog before submitting again. HTML output uses text content, not untrusted injected markup.

## Schema and delivery

- `045_atomic_payment_refunds`: provider amount snapshot, cumulative accounting, refund events/notices and event-specific referral reversal keys.
- `046_tribute_catalog`: retained offers and administrator audit. The former six source mappings are copied once from migration seed data using existing database plan terms; runtime has no static product table or process-local catalog cache.

Migration tests run against a transaction-rolled-back schema in `apix_session_migration_test` on loopback PostgreSQL. Downgrade refuses to discard refund evidence or administrator catalog edits; production rollback is a reviewed forward repair. Ordinary delivery remains protected-main CI/autodeploy, not a manual server checkout.

## Verification boundaries and references

Signed synthetic HTTP callbacks are tested against real disposable PostgreSQL for concurrent duplicates, storage failure, stale/partial/full refunds, late events and referral accounting. Catalog tests cover authorization, strict validation, optimistic concurrency, replacement and all shared checkout consumers. Provider API calls in tests are mocked; no real payment or real refund has been executed for this change.

Primary provider references reviewed:
- https://developer.tbank.ru/eacq/intro/developer/notification
- https://developer.tbank.ru/eacq/api/get-state
- https://developer.tbank.ru/ecosystembundle/scenarios/payments/b-side/cancel_confirm
- https://tinkoff.github.io/api_asdk/openapi/prod/paths/GetState.yaml
- https://github.com/tinkoff-mobile-tech/tinkoff-asdk-android/blob/master/core/src/main/java/ru/tinkoff/acquiring/sdk/responses/CancelResponse.kt

The bank SDK exposes `OriginalAmount` and `NewAmount` on Cancel responses separately from GetState `Amount`. Documentation inspection and local contract tests do not constitute a live-bank sandbox settlement test.


## Review follow-up: reporting and reconciliation

A ledger-proven legacy payment whose status was overwritten to `failed` can still settle a partial refund: the service verifies a positive payment-credit row for the same transaction and payer, then restores the paid state and applies the partial refund in one transaction. Uncredited pending payments are still deferred; this is not an automatic historical balance backfill.

Lava status reconciliation uses its shared `is_paid_invoice` adapter so event-only and nested success payloads remain supported. The bot shows partial/full refund state explicitly instead of claiming a fresh full credit after removing credits.

Revenue aggregates in the bot, web admin, Mini App admin, referral summaries and assistant reports use one net-paid calculation. Original `amount_rub` remains unchanged for transaction provenance. Partial refunds contribute the remaining proportional RUB amount, rounded to kopecks; fully refunded and pending transactions contribute zero. Period reports still group by original payment creation date, not refund cash-flow date.

Deferred refunds log provider, a safe external payment ID (or a stable hash for malformed IDs), and an allowlisted reason code. Unknown exception text and raw provider values are never emitted. These diagnostics identify amount/currency/state mismatches without exposing callback bodies.
