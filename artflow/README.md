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

The latest Alembic head at this audit is `044_trend_run_claims`; use `alembic heads` to check the active branch rather than a copied migration count. The application also runs migrations in its Compose startup command.

Build the Mini App from `artflow/webapp/`:

```bash
npm ci
npm run typecheck
npm run test:unit
npm run build
```

## Verification

The protected `main` branch requires `backend-quality`, `webapp`, `provider-contracts` and `bot-navigation`. The maintained backend gate is defined in [CI](../.github/workflows/ci.yml); provider checks are defined in [Provider Contract Compliance](../.github/workflows/provider-contracts.yml). The complete historical `pytest` suite has known failures outside that gate; see the [full-project audit](docs/audits/2026-10-16-full-project.md) before treating it as a release signal.

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
