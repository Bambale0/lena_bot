# APiX T-Bank pending audit pagination (issue #357)

This is an **operator-only, bounded dry-run**. It queries existing `pending`
transactions and uses **T-Bank GetState** for each selected external invoice ID.
No `--apply` means **no database status change, provider charge, refund, or
customer credits**.

Start with the desired cohort (example commands are issued *inside* the
production app container, where credentials already exist):

```sh
python scripts/fix_stuck_tbank_payments.py --limit 20 --offset 0 --lookback-days 3650 --min-age-minutes 60
python scripts/fix_stuck_tbank_payments.py --limit 20 --offset 20 --lookback-days 3650 --min-age-minutes 60
```

Use the `summary.next_offset` returned from a page **only for another dry-run**;
`summary.has_more` signals more matching rows as observed at that moment.
Pagination is ordered by `created_at, id`. Because incoming payments and
independent reconciliations can change the pending set between queries, this
is a *moving* inventory, not a permanent snapshot. Use a consistent lookback
window, record run timestamps and re-run a final overlap audit. Do not infer
provider success/failure from age.

`--apply` **cannot be combined with a nonzero `--offset`**: applying a
terminal status removes a row from the pending set and would cause offset-based
pagination to skip payments. The existing apply flow always starts from the
oldest eligible pending rows and re-verifies invoice identity, provider status,
terminal key and amount before any atomic repository mutation. A manual
operational approval and backup are required before running it.

The CLI emits local transaction identifiers only in the restricted operator
terminal; do **not** paste raw logs or payment/provider identifiers into GitHub.
Avoid large audits that exceed provider GetState rate limits. Never use paid
create-payment calls to determine an invoice's outcome.

Provider-specific statuses: a CryptoBot invoice that remains nonterminal does
not become `failed` merely because it is old. Apply the same principle to
T-Bank, Lava and Telegram Stars; each provider requires its own authoritative
query contract.
