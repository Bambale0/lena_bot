# Production autodeploy

APIX deploys from branch `main` after the `APIX CI/CD` backend and webapp checks complete successfully.

## GitHub configuration

Create or update the `production` environment and set these secrets:

| Name | Value |
| --- | --- |
| `DEPLOY_HOST` | Production server IP or hostname |
| `DEPLOY_KNOWN_HOSTS` | Verified SSH host key line |
| `DEPLOY_SSH_PRIVATE_KEY` | Private Ed25519 deploy key |

Set these variables both on the repository or environment:

| Name | Value |
| --- | --- |
| `AUTODEPLOY_ENABLED` | `true` |
| `DEPLOY_USER` | `root` |
| `DEPLOY_PORT` | `22` |
| `DEPLOY_PATH` | `/root/mkdir/lena_bot` |
| `DEPLOY_APP_SUBDIR` | `artflow` |
| `DEPLOY_BRANCH` | `main` |
| `DEPLOY_PUBLIC_HEALTH_URL` | `https://apixbotai.com/api/v1/health` |

## Server requirements

The server checkout must already contain production `.env` at `artflow/.env`.
The deploy script never creates or overwrites `.env`.

The application loads its runtime credentials only from `artflow/.env`.
In particular, `NEIRONYCH_API_KEY` must come from this canonical file.
The existing `.env.neironych` is a separate local lab file: production Compose
must not load it. Leave that real file untouched; do not copy, rename, overwrite
or delete it as part of a production deployment or credential repair.

The `backend-quality` deploy-contract gate resolves Compose against synthetic
files in a temporary directory, including a conflicting lab value, to prevent
an optional local file from overriding or supplying production credentials.
These tests never read either real server secret file.

Required runtime tools:

- Git
- Docker Engine with the Compose plugin
- `curl`
- `flock`

## Deploy flow

The `deploy` job in `.github/workflows/ci.yml` streams `artflow/scripts/deploy-production.sh`
over SSH. The script:

1. Acquires a deployment lock.
2. Fetches and fast-forwards `origin/main`.
3. Builds the webapp assets in a Node 22 container.
4. Validates `docker compose`.
5. Builds the app image.
6. Starts PostgreSQL and Redis.
7. Runs Alembic migrations.
8. Starts the app and Nginx.
9. Checks the public health URL.

The script does not run `git reset` and does not discard local production overrides.
If a future commit conflicts with local tracked changes, Git stops the deployment.

## Rollback

Revert the bad commit on `main`, wait for CI to pass, and let autodeploy deploy the reverted commit.
Database migrations are not automatically downgraded; use a forward repair migration after schema changes reach production.
