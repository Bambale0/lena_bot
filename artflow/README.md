# APIX application

`artflow/` contains the production FastAPI application, Telegram bot, standalone site and Telegram Mini App. This page is an entry point for developers. Runtime tariffs, enabled models and provider routes come from the backend and its authenticated admin controls; values in historical design documents are not a live price list.

## Runtime map

| Surface | Entry point | API |
| --- | --- | --- |
| Standalone site and Studio | `landing/` at `/` and `/studio.html` | `/api/web/*` |
| Telegram Mini App | `webapp/src/main.tsx` at `/app` | `/api/v1/*` |
| Legacy Mini App | `webapp/src/main.jsx` behind `?legacy=1` | `/api/v1/*` |
| Telegram bot | `main.py` webhook; `run_polling.py` for local polling | Shared domain and provider services |

FastAPI mounts the routers in `main.py`. PostgreSQL stores users, balances, generations, payments, prompts, provider settings and trend run claims. Redis supports bot state and coordination. Provider adapters and contract metadata live in `api/`; database repositories and Alembic migrations live in `db/`.

For route and UI ownership, see [current surface inventory](docs/current_surface_inventory.md). For the current provider registry, see [generated contract coverage](docs/provider_contract_coverage.md). For trend behavior, see [trends](docs/trends.md).

## Local development

From the repository root:

```bash
cd artflow
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Set local credentials in the untracked `.env`. If PostgreSQL and Redis run through Compose, set `DATABASE_URL` to use `localhost:5433` and `REDIS_URL` to use `localhost:6379` for a host-side Python process. The Docker container uses the service names from `.env.example`. Then start the required services and apply migrations:

```bash
docker compose up -d postgres redis
alembic upgrade head
python run_polling.py
```

The current Alembic head is `055_referral_credit`; use `alembic heads` to check the active branch rather than a copied migration count. The application also runs migrations in its Compose startup command.

Build the Mini App from `artflow/webapp/`:

```bash
npm ci
npm run typecheck
npm run test:unit
npm run build
```

## Verification

The protected `main` branch requires `backend-quality`, `webapp`, `provider-contracts` and `bot-navigation`. The maintained backend gate is defined in [CI](../.github/workflows/ci.yml); provider checks are defined in [Provider Contract Compliance](../.github/workflows/provider-contracts.yml). The backend gate now runs the full `pytest` suite. See [audit completion](docs/audits/2026-10-16-completion.md) and [payment/catalog contracts](docs/payments-refunds-catalog.md) for repaired behavior, migration checks and verification boundaries.

Useful local checks:

```bash
python -m compileall -q api bot core db payments main.py
python scripts/check_provider_contracts_ci.py
python scripts/check_provider_product_readiness.py
python scripts/run_provider_live_smoke.py
pytest -q tests/test_trend_run_reliability.py tests/test_payment_webhooks.py
```

`run_provider_live_smoke.py` without `--execute` validates the manifest only; it does not submit paid provider jobs. Some checks need non-production placeholder `BOT_TOKEN`, `COMET_API_KEY` and `DATABASE_URL` values to import settings.

## Delivery and operations

Changes reach `main` through a reviewed PR with native squash auto-merge. On a successful `main` CI run, Production Autodeploy builds the frontend, applies migrations and checks the public health endpoint. Do not manually rebuild or restart the production server for ordinary releases. See [Production autodeploy](docs/production-autodeploy.md) for the deploy and rollback contract.

Secrets belong in the production `.env` and must not be committed. For configuration names and examples, use [.env.example](.env.example). The public health checks are `/health` and `/api/v1/health`.

Referral ancestry is assigned only when an account is created and is immutable afterward. The incident-repair tool is dry-run by default:

```bash
python -m scripts.repair_referral_lineage
```

An approved repair requires both `--apply` and a named `--operator`; it records append-only lineage and finance evidence in PostgreSQL and is idempotent by `--batch-key`.

Supplier-cost reconciliation for failed image HTTP 5xx, delayed Nexus callbacks and refunded Seedance tasks (Neironych or Kie) continues silently:
provider outcomes, unresolved-liability states and credit-ledger changes stay available in
the protected admin API and structured logs. These routine supplier-review transitions,
including late outcomes and manual-resolution markers, **do not send Telegram admin alerts**.
Alerts about actual provider credit shortages, anti-fraud, and backup notifications are unchanged.
Customer completion/failure notifications are unchanged.

Audit follow-up: [verified fixes and explicitly open blockers](docs/audits/2026-10-16-remediation.md). The full pytest suite and payment findings are not closed by this release.

## Seedance admission incident

For the verified native 503 contract, durable Neironych-to-KIE fallback and verification boundaries, see [Seedance admission recovery](docs/seedance-admission-recovery.md). Generic provider failures still require reconciliation; HTTP health is not a live generation test.

## Image fallback: Nexus → Neironych

A canonical Nexus image task with a confirmed terminal `E-294` overload failure can be
recovered through Neironych using the **same** model and **same** original image
references. Supported exact-model routes are Nano Banana Pro, Nano Banana 2,
and GPT Image 2 (text-to-image and image-to-image). VIP and other models are
excluded to avoid changing product or quality. Content-policy rejections,
ambiguous Nexus timeouts/5xx, and unknown submission outcomes never trigger
a second paid request.

Per-model fallback is enabled by default and can be disabled without deploy:
`GET /api/web/admin/provider-routing/image-fallbacks` and
`PUT /api/web/admin/provider-routing/image-fallbacks/{model_key}`
with `{"enabled": false}`. Changes require admin authorization and are audited.

A generation-level PostgreSQL claim and deterministic Neironych request ID
prevent duplicate submissions from concurrent webhooks/pollers. The customer
is charged **once** and receives either the recovered image or the normal
idempotent refund. If the Neironych submission outcome is uncertain, the
system only polls the existing request by ID; it never blindly resubmits.
See `docs/agents/EXECUTION/nexus-neironych-image-fallback-20261031.md`.
