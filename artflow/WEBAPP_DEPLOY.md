# Telegram Mini App Deploy

Build frontend:

```bash
cd /root/lena/lena_bot/artflow
cd webapp
npm install
npm run build
cd ..
```

The built `webapp/dist` directory is committed, so a plain `git pull` also
keeps `/app` available. Rebuild it after frontend changes.

Restart webhook service:

```bash
systemctl restart artflow-webhook
```

Check production:

```bash
curl -I https://apix.chillcreative.ru/app
curl https://apix.chillcreative.ru/api/v1/health
```

Outside Telegram the app opens with demo data. Real `/api/v1/*` mini-app endpoints require valid Telegram WebApp `initData`.

## Shared bot data

The Mini App uses the same backend repositories and database records as the Telegram bot:

- `/api/v1/me` returns the common user balance, referral code and language.
- `/api/v1/generate/image`, `/api/v1/generate/video`, `/api/v1/generate/music` create the same generation records used by the bot.
- `/api/v1/history`, `/api/v1/feed`, `/api/v1/prompts` read shared generation, public feed and prompt-library data.
- `/api/v1/assistant` calls the same assistant service as the bot assistant.
- `/api/v1/settings/language` updates the shared user language.
- `/api/v1/referrals` and `/api/v1/referrals/withdrawals` use the shared referral balance and withdrawal tables.

Do not create a separate Mini App database. Add new web capabilities through the existing repository layer unless a migration is explicitly required.
