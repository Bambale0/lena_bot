# Payment / credit ledger integrity audit (read-only)

Use when triaging #343 or after a deployment. The audit **does not** request
T-Bank / CryptoBot / Lava / Telegram Stars status, does not create or re-open
invoices, and never credits or refunds any account.

## Run

From \`/root/mkdir/lena_bot/artflow\` on production:

```bash
docker compose exec -T app python scripts/report_payment_integrity.py
```

The script executes a **REPEATABLE READ READ ONLY** PostgreSQL transaction,
with a 15-second per-statement timeout, and rolls back at the end.
It reports only aggregate counts per provider. No transaction IDs, customer
identifiers, raw payment references, tokens, or DSNs appear in its output.
Exit code 0 means all queried local ledger invariants hold, exit code 1
means at least one local integrity anomaly, and exit code 2 means report failure.

## Interpretation

- `paid_without_ledger`: paid transaction with no `payment_credit` ledger entry.
- `paid_duplicate_ledger`: multiple payment-credit ledger entries for one paid transaction.
- `paid_credit_mismatch`: exactly one ledger entry with different credited amount.
- `ledger_owner_mismatch`: ledger user differs from the transaction owner.
- `nonpaid_with_payment_ledger`: credit entry linked to a pending/failed payment.
- `orphan_payment_ledger`: credit entry linked to no transaction.
- `pending_older_7d` / `pending_older_90d`: aged unresolved local invoices, **not** evidence that money was received. Do not mark these paid or failed by age.

If anomalies occur, stop any bulk reconciliation, preserve the report, compare the
provider's authoritative settlement and webhook history, and use the idempotent
ledger settlement workflow. Never directly update `User.credits` or
`Transaction.status` from a SQL console.

## Coverage / limitations

This is a **local accounting invariant report**, not a bank statement or a
provider reconciliation. It cannot determine whether a `pending` invoice has
actually been paid, whether an external refund has settled, or whether a
provider webhook was sent but lost. Provider status checks and refund
settlement must follow separate explicit procedures (see
`docs/tbank-reconciliation-runbook.md`), with review and appropriate
commission handling.

Counts are an as-of snapshot. Operators can compare summaries across days,
but should not identify a customer's account from this report.
