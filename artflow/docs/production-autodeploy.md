# Production autodeploy

APIX deploys from branch `v2` after the `APIX CI/CD` backend and webapp checks complete successfully.

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
| `DEPLOY_BRANCH` | `v2` |
| `DEPLOY_PUBLIC_HEALTH_URL` | `https://apixbotai.com/api/v1/health` |

## Server requirements

The server checkout must already contain production `.env` at `artflow/.env`.
The deploy script never creates or overwrites `.env`.

Required runtime tools:

- Git
- Docker Engine with the Compose plugin
- `curl`
- `flock`

## Deploy flow

The `deploy` job in `.github/workflows/ci.yml` streams `artflow/scripts/deploy-production.sh`
over SSH. The script:

1. Acquires a deployment lock.
2. Fetches and fast-forwards `origin/v2`.
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

Revert the bad commit on `v2`, wait for CI to pass, and let autodeploy deploy the reverted commit.
Database migrations are not automatically downgraded; use a forward repair migration after schema changes reach production.
