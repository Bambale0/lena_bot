# T-Bank pending reconciliation — operator runbook

This is a **bounded manual catch-up tool**, not a scheduler. The first run must be a dry-run. It never creates an invoice or charges a card.

Run from the ArtFlow app container (production has its canonical environment):

```bash
docker compose exec -T app python scripts/fix_stuck_tbank_payments.py --limit 20 --lookback-days 30 --min-age-minutes 30
```

Dry-run uses T-Bank `GetState` to classify rows but makes **no local database writes**. It prints only local transaction IDs, normalized decisions and reasons, never provider payloads or credentials.

Only after an authorized operator has reviewed the report and confirmed that provider credentials, amount and payment identity are correct:

```bash
docker compose exec -T app python scripts/fix_stuck_tbank_payments.py --apply --limit 20 --lookback-days 30 --min-age-minutes 30
```

Safety properties:
- Hard cap of 50 per execution; default 20. Bounded T-Bank GetState lookups, no parallelized flood.
- T-Bank `Success=True`, exact `PaymentId`, optional terminal key and integer minor-unit amount must agree.
- `CONFIRMED` is credited via the existing atomic `confirm_transaction_and_add_credits` ledger seam, with the first-topup referral policy installed. Concurrent webhook/reconcile calls cannot credit the same pending transaction twice.
- Only verified final provider failures can set `failed`; all other statuses are retained.
- Refund and partial refund states always require the separate refund-reconciliation path; **never** assume they can be marked failed.
- No direct SQL changes to balances or transaction statuses. An error during one transaction does not cancel the batch.
- Never automatically retry the checkout or create new invoices.

Backlog size alone is not evidence of unpaid credits: some pending invoices are abandoned or cancelled. For the production baseline from 2026-11-15, see APiX issue #343.

Verification after an authorized apply:
1. Compare paid transactions with exactly one matching `credit_ledger` source entry.
2. Check first-topup referral entries and refund notices.
3. Re-run the same batch in dry-run to ensure no further actionable states.
4. Review logs for provider API failures or mismatched identities/amounts.
5. If anything does not match, **stop** the batch and investigate; do not manually modify balances.
