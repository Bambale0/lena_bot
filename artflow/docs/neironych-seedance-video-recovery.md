# APIX · Neironych Seedance video recovery

Incident basis: video `aeb56f5f-ddfd-42fe-baba-115372cbb1e4` remained `processing` even after Neironych reported terminal `failed`. An operator had to check it manually; only then were 70 credits refunded atomically. The root cause was missing scheduled video polling and an unsafe generic 20-minute timeout/refund path.

## Recovery lifecycle

- Only product models `bytedance/seedance-2` and `bytedance/seedance-2-5` whose existing `task_id` identifies Neironych are polled. Read-only `GET /v1/videos/{request_id}`; when completed, download `GET /v1/videos/{request_id}/content` using the provider client and persist under APIX-owned public media. **No automated paid rerun or cross-provider fallback**.
- Default interval is 90 seconds, minimum task age 30 seconds, max 24 video polls plus 24 notice retries per cycle, 4 concurrent requests per pool, 240-second per-task upper bound. The scheduler fairly revisits old tasks while checking new ones. Configuration is typed in `core/config.py` and can be overridden through deployment settings.
- Provider status `failed`, `cancelled` or `expired` raises a typed terminal failure only after validating any `request_id` returned in the JSON against the requested task UUID. A mismatched response cannot trigger a refund. `repo.fail_generation_and_refund` uses the existing locked, single-winner pending/processing→failed transition to credit the user's account once, and enqueues a failed Telegram notice in the *same database transaction*. A second simultaneous callback cannot refund twice.
- Provider status `queued/processing/running`, timeout, HTTP 404/429/5xx, network error, malformed status, or a completed video whose file is temporarily unavailable does **not** authorize refund. Even after 20 minutes, the job stays active. Missing provider task IDs are reported as anomalies requiring manual reconciliation; no guess at the paid operation outcome.
- Successful video: `repo.finish_generation` persists the durable result URL plus a `neironych_video_notice` pending receipt atomically; a single claim attempt sends it to the Telegram user, with direct MP4 first and Telegram link fallback.
- Failure: Telegram user is told about the confirmed provider failure and the refund (only if the ledger marker says credits were returned). Public website tasks (`web:` prefix) do not receive unsolicited Telegram notifications. Site/Mini App/task history all read the same terminal status/credits from the shared DB.
- If Telegram is unavailable, the notice remains in `generations.input_params` with an attempt counter and exponential backoff. A DB row lock, per-attempt UUID and 600-second lease prevent concurrent delivery workers from sending the same item. Retry after crash/restart if a claim lease expires. Successful delivery is marked `sent`. After 8 failed sends the notice becomes a `dead_letter` for operator investigation rather than retrying a blocked/deleted Telegram chat indefinitely.
- Status GET, provider video download **and DB settlement** hold an auto-renewed Redis task lease (conditional token-based Lua renewal). Lost ownership cancels only that polling attempt, not the scheduler, and never authorizes a refund. The same lease covers scheduled and on-demand history polling. PostgreSQL read transactions are committed before long provider calls. Redis outage defers polling without re-submission or refunds.
- Telegram chat Seedance generations are owned **exclusively by the background recovery scheduler** after submission; the older foreground `poll_until_done` was removed from Neironych route because its timeout/refund callback raced background completion and could duplicate downloads/delivery. Other providers keep their original polling logic.
- Both immediate status-request delivery and periodic retry are bounded by `NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS` before their receipt is retried. Notification lease must exceed this timeout plus 30 seconds. On persistent Telegram rejection, it enters `dead_letter` after the configured attempt limit.
- Delivery is **at least once**, not mathematically exactly once: if Telegram accepts a message and the process crashes before committing its receipt, one repeat is possible after the lease. No duplicate paid generations or credit adjustments are triggered by notice retries.

## Configuration

| Setting | Default | Meaning |
|---|---:|---|
| `NEIRONYCH_VIDEO_RECONCILE_INTERVAL_SECONDS` | 90 | Delay between cycles |
| `NEIRONYCH_VIDEO_RECONCILE_MIN_AGE_SECONDS` | 30 | Grace before first provider status GET |
| `NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE` | 24 | IDs per query lane |
| `NEIRONYCH_VIDEO_RECONCILE_CONCURRENCY` | 4 | Parallel upstream checks / Telegram retries |
| `NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS` | 240 | Per video poll/download/notice timeout |
| `NEIRONYCH_VIDEO_POLL_LEASE_SECONDS` | 600 | Redis single-poller lease (must exceed timeout plus safety margin) |
| `NEIRONYCH_VIDEO_ALERT_AGE_SECONDS` | 3600 | Emit overdue warnings (no automatic refund) |
| `NEIRONYCH_VIDEO_NOTICE_LEASE_SECONDS` | 600 | Retry abandoned claimed notification after lease |
| `NEIRONYCH_VIDEO_NOTICE_RETRY_SECONDS` | 60 | First Telegram delivery retry delay |
| `NEIRONYCH_VIDEO_NOTICE_MAX_BACKOFF_SECONDS` | 900 | Upper retry delay bound |
| `NEIRONYCH_VIDEO_NOTICE_MAX_ATTEMPTS` | 8 | Limit sends before `dead_letter` (no more automatic retries) |

No new migrations or business-price parameters. No secrets in logs or URLs returned by the new scheduler.

## Diagnose and verify

```bash
cd artflow
.venv/bin/python -m pytest tests/test_neironych_video_stuck_recovery.py tests/test_neironych_video_notice_outbox.py tests/test_reconcile_video_delivery.py tests/test_neironych_seedance_runtime.py -q
# On production (read-only)
docker compose logs --since=30m app | grep -E 'Neironych Seedance video recovery|Neironych video overdue|Neironych video notification'
docker compose exec -T postgres psql -U bot -d artflow -c \
  "select id, model, status, age(now(),created_at) from generations where gen_type='video' and status in ('pending','processing') order by created_at limit 25"
```

Expected after deployment: `Neironych Seedance video recovery scheduler started` at startup and periodic summary when active tasks or notices exist. For an old unknown upstream state, inspect provider read-only API by persisted request UUID; do not trigger a new paid POST as a diagnostic. `generation_id` and provider task ID are the correlation fields. Failed task refunds must match the `credit_ledger` exactly once.

**Rollback:** revert the PR using the protected `main` workflow. New pending receipt keys remain in existing `input_params` JSON, so no schema rollback or credit rewriting is necessary. If rolled back during an undelivered notice, it will remain stored for restoration by the new worker; users can still retrieve finished media in generation history.
