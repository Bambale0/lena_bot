# Nano Banana 2.1 — APIX / Artflow

Product model ID: `nano-banana-2.1` (independent of Nano Banana 2 and Pro).

## Provider routing

- **Primary:** Neironych `POST /v1/images/generations` (without references) or `POST /v1/images/edits` (with references).
- **Fallback:** Nexus `POST /generate`, asynchronous task polling using the existing `nexus:` task ID prefix and webhook route.
- Active provider selector: database-backed `provider_routing_settings`, edited in Telegram `/admin → 🔀 Banana 2.1 провайдер` or authorized Web API `GET/PUT /api/web/admin/provider-routing/nano-banana-2.1`. `NANO_BANANA_21_PRIMARY_PROVIDER=neironych|nexus` is used only if the database has no override.
- All provider credentials and base URLs use existing environment settings. Never expose tokens in frontend, logs or Git.

Verified contracts (8 October 2026): Neironych `GET /v1/models` returned `nano-banana-2.1` enabled for the APIX key. Nexus OpenAPI has `NanoBanana21`, with `image_size=1K|2K|4K`. The common reference limit is **4**. The application keeps both providers on the exact 2.1 model ID, not another Banana version.

### Neironych protocol

- Generate a deterministic `client_request_id` UUID from the saved APIX generation ID. **Commit** the task marker `neironych-image:<uuid>` before submitting the paid POST. Use this UUID for both `Idempotency-Key` and `X-Client-Request-Id`; include `model`, `prompt`, `n=1`, `resolution=1k|2k|4k`, `aspect_ratio`, `response_format=b64_json`.
- Do not pass `size`: forbidden for this model.
- For reference images, use `images:[{"image_url":"https://..."}]`.
- Successful result arrives synchronously as `data[].b64_json`; fully decode and verify JPEG/PNG/WebP dimensions/content, then persist to the APIX-owned public static upload directory before returning. Configured provider base URLs must use HTTPS and never carry inline credentials.
- Timeout default `NEIRONYCH_IMAGE_TIMEOUT_SECONDS=100` is under the APIX nginx 120-second proxy limit and the legacy Mini App's 110-second override. Larger timeouts need coordinated proxy/frontend changes.

### Safe failover rules

- Fallback to Nexus only for a **definitive upstream rejection** (e.g., HTTP 402/429; other explicit no-work-rejections).
- **Never** fallback or repeat paid POST automatically after timeout, connection loss, HTTP 5xx, malformed success or an uncertain 422. Neironych explicitly warns that the upstream generation may have been accepted or charged.
- Each accepted Nexus task is tracked/polled under its prefixed task ID and uses the existing generation balance settlement.
- After timeout, HTTP 5xx or an invalid result, **leave the already charged APIX generation processing** with its persisted `request_id`. Reconcile through the read-only `GET /api/v1/generations/by-client-request-id/<uuid>` and the bounded background scheduler (`NEIRONYCH_IMAGE_RECONCILE_INTERVAL_SECONDS=75`, configurable). Only provider-confirmed terminal failures are eligible for the existing atomic refund. Recovered completed results are finalized and delivered with a single-winner DB state transition. If the synchronous base64 result is not recoverable from the provider's persisted status, leave it pending for **manual operator reconciliation**; do not claim delivered or retry automatically.
- Failover happens at launch, not in a second run after a task is already accepted.

## Pricing and product surfaces

On startup, `db.seed._seed_nano_banana_21_prices` creates missing base/2K/4K commercial rows by cloning the **current DB-admin-configured Nano Banana 2 prices**. It never overwrites existing 2.1 rows. The 1K option falls back to the base row. Administrators can adjust 2.1 independently through the regular model price editor; no fixed business prices are hardcoded.

The same `ImageModel`, `IMAGE_CAPS`, and database prices drive the website, Telegram Mini App, and text bot. Ref count = 4; modes = text and reference edit; output resolutions = 1K/2K/4K.

## Verification

```bash
cd /root/mkdir/lena_bot/artflow
.venv/bin/python -m pytest tests/test_nano_banana21_routing.py tests/test_nano_banana21_control_plane.py tests/test_nano_banana21_api_integration.py tests/test_nexus_image_migration.py -q
.venv/bin/python -m ruff check api/neironych_image_adapter.py api/image_service.py api/nexus_image_adapter.py tests/test_nano_banana21_routing.py
cd webapp && npm run build
```

Live smoke: one low-cost 1K text-to-image generation with an innocuous prompt. Verify Neironych completion, existence of local result file, an accessible public URL, site/Mini App/Telegram model availability, and absence of double charges.

**Rollback**: change primary to Nexus in Telegram/Web admin (no redeploy) or deactivate the 2.1 commercial model in the model-cost editor. Existing Neironych tasks keep their own correlation IDs and are reconciled on their original provider; never migrate pending work to the new primary. Secrets remain in the environment. **Schema**: additive Alembic migration `037_provider_routing_settings` creates routing/audit tables; applying it to production requires explicit operator approval under `AGENTS.md`.
