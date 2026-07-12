# Telegram Mini App Deploy

Production runs from:

```bash
/root/mkdir/lena_bot/artflow
```

CI builds the Mini App frontend on `main` and on every pull request. The webapp job uses Node.js 22,
`npm ci`, and `npm run build` from `webapp/`.

Build frontend after pulling frontend or CI changes:

```bash
cd /root/mkdir/lena_bot/artflow/webapp
npm ci
npm run build
```

The production host does not require Node.js to be installed globally. If
`npm` is not available on the host, build with the Node container instead:

```bash
cd /root/mkdir/lena_bot/artflow
docker run --rm -v "$PWD:/workspace" -w /workspace/webapp node:22-alpine sh -lc "npm ci && npm run build"
```

Restart the production app container:

```bash
cd /root/mkdir/lena_bot/artflow
docker compose restart app
```

Check production:

```bash
curl -I https://apixbotai.com/app
curl https://apixbotai.com/api/v1/health
docker compose ps
```

Outside Telegram the app opens with demo data. Real `/api/v1/*` Mini App
endpoints require valid Telegram WebApp `initData`.

## Shared bot data

The Mini App uses the same backend repositories and database records as the Telegram bot:

- `/api/v1/me` returns the common user balance, referral code and language.
- `/api/v1/generate/image`, `/api/v1/generate/video`, `/api/v1/generate/music` create the same generation records used by the bot.
- `/api/v1/history`, `/api/v1/feed`, `/api/v1/prompts` read shared generation, public feed and prompt-library data.
- `/api/v1/assistant` calls the same assistant service as the bot assistant.
- `/api/v1/settings/language` updates the shared user language.
- `/api/v1/referrals` and `/api/v1/referrals/withdrawals` use the shared referral balance and withdrawal tables.

Do not create a separate Mini App database. Add new web capabilities through the existing repository layer unless a migration is explicitly required.
