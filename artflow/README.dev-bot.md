# APIX deployment flow: dev bot → main → production

This is the default development workflow for APIX:

```text
feature branch / PR
  → auto/manual deploy to isolated Telegram dev bot
  → test Mini App + Telegram flows on the dev bot
  → approve
  → merge into main
  → production autodeploy from main
```

Do not test risky UI/API changes on the production bot. The production bot should only receive code that already passed dev-bot checks.

## Why a separate dev bot exists

- Production bot token remains untouched.
- Telegram updates for the dev bot arrive on a separate webhook path.
- Dev database, Redis and uploaded files are isolated.
- The dev app listens only on localhost by default, so the existing production nginx can own ports 80/443.
- Dev can follow any feature branch; production follows `main` only.

## Branch rules

Recommended branch model:

- `main` — production only, protected by PR review/approval.
- `agent/miniapp-shadcn-rework` or any `feature/*` branch — deployable to dev bot.
- PR stays draft/open while UX and API are being tested on the dev bot.
- Merge to `main` only after dev bot testing is accepted.

GitHub Actions can run workflows on `push` and can restrict them to named branches using branch filters. Use that split for automation: dev deploy on feature/dev branches, production deploy only on `main`.

## Required GitHub/server secrets for real autodeploy

Use repository/environment secrets, never committed files:

Dev deployment secrets:

- `DEV_SSH_HOST`
- `DEV_SSH_USER`
- `DEV_SSH_KEY`
- `DEV_APP_PATH`, for example `/root/mkdir/lena_bot/artflow`
- dev bot `.env.dev` stored only on the server

Production deployment secrets:

- `PROD_SSH_HOST`
- `PROD_SSH_USER`
- `PROD_SSH_KEY`
- `PROD_APP_PATH`, for example `/root/mkdir/lena_bot/artflow`
- production `.env` stored only on the server

## First-time dev bot setup

1. Create a separate Telegram bot in BotFather, for example `apix_ai_dev_bot`.
2. Create a public dev host, for example `https://dev-apix.example.com`, and proxy it to `127.0.0.1:8010` on the server.
3. Prepare the env file:

```bash
cd ~/mkdir/lena_bot/artflow
cp .env.dev.example .env.dev
nano .env.dev
```

Required values:

- `BOT_TOKEN` — token of the dev bot only;
- `BOT_USERNAME` — username of the dev bot;
- `WEBHOOK_URL` — public dev host without trailing path;
- `WEBHOOK_PATH` — separate Telegram webhook path, for example `/webhook/telegram/dev`;
- `WEBHOOK_SECRET` — random secret sent by Telegram in `X-Telegram-Bot-Api-Secret-Token`;
- `WEB_PUBLIC_URL` — public dev host used by Mini App buttons;
- provider/payment keys — sandbox/dev values where possible.

Telegram `setWebhook` supports `secret_token`; Telegram sends that value back in the `X-Telegram-Bot-Api-Secret-Token` header for every webhook request. Use a different secret for dev and production.

## Nginx proxy idea for dev host

The isolated dev app exposes FastAPI on localhost by default:

```text
127.0.0.1:8010 → dev bot API + /app Mini App
```

A simple nginx server block can proxy the dev subdomain to it:

```nginx
server {
    server_name dev-apix.example.com;

    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Keep the dev domain separate from production. Do not point the dev bot to the production `WEB_PUBLIC_URL`.

## Deploy current branch to the dev bot

```bash
cd ~/mkdir/lena_bot/artflow
bash scripts/deploy-dev-bot.sh agent/miniapp-shadcn-rework
```

The script builds `webapp/dist`, creates the shared `apix_devbot_backend` Docker network when missing, validates `docker-compose.dev-bot.yml`, and starts an isolated Compose project named `artflow_devbot` by default.

Default local ports:

- app: `127.0.0.1:8010`;
- postgres: `127.0.0.1:5434`;
- redis: `127.0.0.1:6380`.

Override them if needed:

```bash
DEV_BOT_APP_PORT=8011 \
DEV_BOT_POSTGRES_PORT=5435 \
DEV_BOT_REDIS_PORT=6381 \
bash scripts/deploy-dev-bot.sh agent/miniapp-shadcn-rework
```

## Register/check dev webhook

The app sets webhook on startup, but this helper is useful for explicit first-time setup or debugging:

```bash
cd ~/mkdir/lena_bot/artflow
bash scripts/set-dev-bot-webhook.sh
```

It calls Telegram `setWebhook` with `WEBHOOK_URL + WEBHOOK_PATH`, passes `WEBHOOK_SECRET`, drops old pending updates by default, and prints `getWebhookInfo`.

## Daily development workflow

1. Make changes in a feature branch.
2. Push branch.
3. Deploy to dev bot:

```bash
cd ~/mkdir/lena_bot/artflow
bash scripts/deploy-dev-bot.sh <branch-name>
```

4. Test in the dev Telegram bot:
   - `/start` opens the dev bot, not production;
   - Mini App opens from dev `WEB_PUBLIC_URL`;
   - webhook info points to dev `WEBHOOK_URL + WEBHOOK_PATH`;
   - generation/payment providers use dev/sandbox keys or disabled payments;
   - database changes are isolated in `artflow_dev`.
5. Fix until accepted.
6. Merge PR into `main`.
7. Production autodeploy pulls `main` and runs the production script/env.

## Production deploy rule

Production deploys only from `main`. The script default branch is `main`; `DEPLOY_BRANCH=main` can be set explicitly in CI for readability.

Manual production deploy from the server:

```bash
cd ~/mkdir/lena_bot/artflow
DEPLOY_BRANCH=main bash scripts/deploy-production.sh
```

Production deploy with a checked SHA from CI:

```bash
cd ~/mkdir/lena_bot/artflow
DEPLOY_BRANCH=main bash scripts/deploy-production.sh <tested-main-commit-sha>
```

Important: the first argument of `deploy-production.sh` is an optional 40-character expected commit SHA, not a branch name. Do not run `bash scripts/deploy-production.sh main`.

For CI/CD, configure production deployment to run only after a successful push/merge to `main`. Do not let feature branches deploy to the production bot.

## GitHub Actions deployment split

Recommended automation shape:

```yaml
# Dev bot: runs for feature/dev branches, never for main production.
on:
  push:
    branches-ignore:
      - main
```

```yaml
# Production: runs only after merge/push to main.
on:
  push:
    branches:
      - main
```

Dev SSH command:

```bash
cd "$DEV_APP_PATH" && bash scripts/deploy-dev-bot.sh "$GITHUB_REF_NAME"
```

Production SSH command:

```bash
cd "$PROD_APP_PATH" && DEPLOY_BRANCH=main bash scripts/deploy-production.sh "$GITHUB_SHA"
```

## Rollback

Dev bot rollback:

```bash
cd ~/mkdir/lena_bot/artflow
bash scripts/deploy-dev-bot.sh <previous-good-branch-or-sha>
```

Production rollback:

```bash
cd ~/mkdir/lena_bot
git fetch origin main
git reset --hard <previous-good-sha>
cd artflow
DEPLOY_BRANCH=main bash scripts/deploy-production.sh
```

## Hard safety rule

Never copy production `.env` into `.env.dev` without changing at least:

- `BOT_TOKEN`
- `BOT_USERNAME`
- `WEBHOOK_URL`
- `WEBHOOK_PATH`
- `WEBHOOK_SECRET`
- database URL
- Redis URL/database
- payment/provider credentials where sandbox alternatives exist
