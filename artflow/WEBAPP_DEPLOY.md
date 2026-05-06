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
curl https://apix.chillcreative.ru/api/webapp/health
```

Outside Telegram the app opens with demo data. Real `/api/webapp/*` endpoints require valid Telegram WebApp `initData`.
