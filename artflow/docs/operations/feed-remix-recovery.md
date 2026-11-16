# Feed-remix paid admission recovery (#358)

The Telegram Mini App now supplies an opaque per-submit `idempotency_key`
persisted in sessionStorage **before** issuing the paid POST. The server
creates a unique `(user_id, request_key)` claim **before** any credit debit,
then links the generation **before** any supplier submission. Replayed
requests with the same key and exact frozen payload return the linked
generation without another debit, while conflicting payloads return 409.

Use authenticated `GET /api/v1/feed/remix-claim/{key}` to recover the
**exact** task for the current user, without guessing from the last twenty
history entries. The response is `complete` with the task,
`processing` when the first request may still be running or was
interrupted, or `unavailable` for an unknown key.

**IMPORTANT LIMIT:** A claim with no generation ID may mean the request
failed or was interrupted between credit debit and generation commit. The
recovery endpoint intentionally does NOT remove it or retry a paid
submission. Inspect the payment ledger, generation history and provider
evidence under controlled access. Do not delete claims to unblock a paid
retry unless the original outcome is authoritatively resolved.

Legacy clients without a request key retain their old behavior until their
WebView updates; do not claim a universal exactly-once guarantee. New clients
without secure sessionStorage/cryptographic randomness fail closed. The UI
does not permit a manual override of a keyed ambiguous attempt.

Safe operator checks (read-only):

```sql
BEGIN READ ONLY;
SELECT status, COUNT(*),
       COUNT(*) FILTER (WHERE generation_id IS NULL) AS unlinked
FROM feed_remix_claims GROUP BY status;
COMMIT;
```

No prompt, Telegram initData, provider token, full request payload or key
should be written to operational logs. Do not send real paid provider jobs
as a production smoke test. The schema migration preserves existing payment
and generation rows; downgrade refuses to discard nonempty claim history.

## Proven pre-admission price conflicts

A `409` carrying `detail.code = feed_remix_preadmission_price_changed`
is emitted **before** the idempotency claim is reserved or credits are
charged. The Mini App may clear the local launch marker, refresh the quote,
and request explicit confirmation of the updated price. It must still
create a fresh random key for the new attempt.

A generic `409`, a network timeout, a connection loss, or an unknown paid
response is **not** a proven pre-admission rejection. Retain the original
key and block a new paid submit until exact-key recovery or an operator-led
ledger reconciliation establishes the outcome. Never treat all `409`s as
retryable and never bypass branch-required CI or protected merges to roll
out the financial fix.
