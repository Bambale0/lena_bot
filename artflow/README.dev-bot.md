# APIX isolated Telegram dev bot

This dev bot contour is for testing branch changes on a separate Telegram bot before promoting code to `main`.

## Why separate it

- Production bot token remains untouched.
- Telegram updates for the dev bot arrive on a separate webhook path.
- Dev database, Redis and uploaded files are isolated.
- The dev app listens only on localhost by default, so the existing production nginx can own ports 80/443.

## First-time setup

1. Create a separate bot in BotFather, for example `apix_ai_dev_bot`.
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

## Deploy branch to the dev bot

```bash
cd ~/mkdir/lena_bot/artflow
bash scripts/deploy-dev-bot.sh agent/miniapp-shadcn-rework
```

The script builds `webapp/dist`, validates `docker-compose.dev-bot.yml`, and starts an isolated Compose project named `artflow_devbot` by default.

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

## Register/check webhook

The app sets webhook on startup, but this helper is useful for explicit first-time setup or debugging:

```bash
cd ~/mkdir/lena_bot/artflow
bash scripts/set-dev-bot-webhook.sh
```

It calls Telegram `setWebhook` with `WEBHOOK_URL + WEBHOOK_PATH`, passes `WEBHOOK_SECRET`, drops old pending updates by default, and prints `getWebhookInfo`.

## Suggested workflow

1. Push changes to a feature branch.
2. Deploy that branch to the dev bot with `scripts/deploy-dev-bot.sh`.
3. Test Mini App and Telegram flows in the dev bot.
4. After approval, merge the PR to `main`.
5. Deploy production with the existing production script/env.

Never copy production `.env` into `.env.dev` without changing at least `BOT_TOKEN`, `BOT_USERNAME`, `WEBHOOK_URL`, `WEBHOOK_PATH`, database, Redis and payment/provider credentials where sandbox alternatives exist.
