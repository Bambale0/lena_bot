# APIX · Neironych Seedance video recovery

Incident basis: video `aeb56f5f-ddfd-42fe-baba-115372cbb1e4` remained `processing` even after Neironych reported terminal `failed`. An operator had to check it manually; only then were 70 credits refunded atomically. The root cause was missing scheduled video polling and an unsafe generic 20-minute timeout/refund path.

## Recovery lifecycle

- Only product models `bytedance/seedance-2` and `bytedance/seedance-2-5` whose existing `task_id` identifies Neironych are polled. Read-only `GET /v1/videos/{request_id}`; when completed, download `GET /v1/videos/{request_id}/content` using the provider client and persist under APIX-owned public media. **No automated paid rerun or cross-provider fallback**.
- Default interval is 90 seconds, minimum task age 30 seconds, max 24 video polls plus 24 notice retries per cycle, 4 concurrent requests per pool, 240-second upper bound for provider status/download and Telegram send (the subsequent atomic DB settlement is not aborted by this timer). The scheduler fairly revisits old tasks while checking new ones. Configuration is typed in `core/config.py` and can be overridden through deployment settings.
- Provider status `failed`, `cancelled` or `expired` raises a typed terminal failure only after validating any `request_id` returned in the JSON against the requested task UUID. A mismatched response cannot trigger a refund. `repo.fail_generation_and_refund` uses the existing locked, single-winner pending/processing→failed transition to credit the user's account once, and enqueues a failed Telegram notice in the *same database transaction*. A second simultaneous callback cannot refund twice.
- Provider status `queued/processing/running`, timeout, HTTP 404/429/5xx, network error, malformed status, or a completed video whose file is temporarily unavailable does **not** authorize refund. Even after 20 minutes, the job stays active. Missing provider task IDs are reported as anomalies requiring manual reconciliation; no guess at the paid operation outcome.
- Successful video: `repo.finish_generation` persists the durable result URL plus a `neironych_video_notice` pending receipt atomically; a single claim attempt sends it to the Telegram user, with direct MP4 first and Telegram link fallback.
- Failure: Telegram user is told about the confirmed provider failure and the refund (only if the ledger marker says credits were returned). Public website tasks (`web:` prefix) do not receive unsolicited Telegram notifications. Site/Mini App/task history all read the same terminal status/credits from the shared DB.
- If Telegram is unavailable, the notice remains in `generations.input_params` with an attempt counter and exponential backoff. A DB row lock, per-attempt UUID and 600-second lease prevent concurrent delivery workers from sending the same item. Retry after crash/restart if a claim lease expires. Successful delivery is marked `sent`. **The configured maximum attempt count is checked both at claim and at completion:** a crash after an attempted send cannot bypass the cap when its lease expires. After 8 unsuccessful/unconfirmed attempts (default) the notice becomes a `dead_letter` for investigation, never an infinite send loop.
- Status GET, provider video download **and DB settlement** hold an auto-renewed Redis task lease (conditional token-based Lua renewal). Lost ownership cancels only an in-flight provider wait, not the scheduler; once a confirmed result enters irreversible DB settlement, Redis renewal errors must **not** interrupt the committed result, feed royalties or linked session update. The same lease covers scheduled and exceptional direct reconciliation. PostgreSQL read transactions are committed before long provider calls. Redis outage defers polling without re-submission or refunds.
- Telegram chat Seedance generations are owned **exclusively by the background recovery scheduler** after submission; the older foreground `poll_until_done` was removed from Neironych route because its timeout/refund callback raced background completion and could duplicate downloads/delivery. Other providers keep their original polling logic.
- Both the production ASGI lifespan and local `python run_polling.py` entrypoint require a real Redis connection before accepting paid jobs. Production probes `PING` on the exact configured `REDIS_URL` **before Bot/webhook setup**, and fails startup if unavailable (creating the client alone is not sufficient). Polling-only mode also starts/stops the same worker, and fails startup if Neironych credentials are configured but the Redis fallback is MemoryStorage.
- Telegram notices are discovered by **two indexed primary-key ranges**: a recent window for new results and a progressing historical sweep for older notices. The historical sweep checkpoint and every discovered notice ID are persisted **atomically** in Redis via Lua, with a Redis sorted set tracking each pending/sending notice by its next due time. This bounds every `input_params ~` scan; the cursor advances even when no notices match, while an old failed notice is retried after its configured backoff or expired claim lease **without waiting for the full historical sweep to wrap**. After sending, the due time is read from the authoritative DB receipt; `sent` and `dead_letter` are removed from the sorted set. A crash between discovery and delivery cannot lose the queued notice. If Redis loses persisted state, the scan safely resumes from its available checkpoint; no DB receipt is falsely marked complete. No DDL required.
- **Mini App / website status and history GET routes do not poll Neironych at all.** They return the current committed DB state promptly while the background worker updates it (normally on a 90-second cycle). This prevents a slow provider GET or 250 MB download from blocking browser requests and causing UI 503/timeout. Other providers keep their existing on-demand path.
- Both immediate status-request delivery and periodic retry are bounded by `NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS` before their receipt is retried. Notification lease must exceed this timeout plus 30 seconds. On persistent Telegram rejection, it enters `dead_letter` after the configured attempt limit.
- Delivery is **at least once**, not mathematically exactly once: if Telegram accepts a message and the process crashes before committing its receipt, one repeat is possible after the lease. No duplicate paid generations or credit adjustments are triggered by notice retries.

## Configuration

| Setting | Default | Meaning |
|---|---:|---|
| `NEIRONYCH_VIDEO_RECONCILE_INTERVAL_SECONDS` | 90 | Delay between cycles |
| `NEIRONYCH_VIDEO_RECONCILE_MIN_AGE_SECONDS` | 30 | Grace before first provider status GET |
| `NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE` | 24 | IDs per query lane |
| `NEIRONYCH_VIDEO_RECONCILE_CONCURRENCY` | 4 | Parallel upstream checks / Telegram retries |
| `NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS` | 240 | Provider poll/download and Telegram send timeout, excluding DB settlement |
| `NEIRONYCH_VIDEO_POLL_LEASE_SECONDS` | 600 | Redis single-poller lease (must exceed timeout plus safety margin) |
| `NEIRONYCH_VIDEO_ALERT_AGE_SECONDS` | 3600 | Emit overdue warnings (no automatic refund) |
| `NEIRONYCH_VIDEO_NOTICE_LEASE_SECONDS` | 600 | Retry abandoned claimed notification after lease |
| `NEIRONYCH_VIDEO_NOTICE_RETRY_SECONDS` | 60 | First Telegram delivery retry delay |
| `NEIRONYCH_VIDEO_NOTICE_MAX_BACKOFF_SECONDS` | 900 | Upper retry delay bound |
| `NEIRONYCH_VIDEO_NOTICE_MAX_ATTEMPTS` | 8 | Limit sends before `dead_letter` (no more automatic retries) |
| `NEIRONYCH_VIDEO_NOTICE_SCAN_ID_SPAN` | 5000 | Indexed ID-window width for recent notices and historical catch-up |

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
