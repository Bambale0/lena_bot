# APIX V4 Production Mini App

## Status

This document describes the clean production integration of the APIX V4 Telegram Mini App in `artflow`.

The production branch is intentionally not based on the old visual prototype PR. It carries only the clean V4 shell and the API contract needed for staging and production verification.

## Goal

Deliver a premium, commercial-grade Telegram Mini App UI without the legacy override stack that previously caused stale visuals, broken demo media, and hard-to-debug CSS precedence.

Target flow:

```text
main -> feat/apix-miniapp-v4-production -> staging preview -> Telegram WebView approval -> production merge
```

## Files in scope

```text
artflow/webapp/src/main.jsx
artflow/webapp/src/apix/AppV4.jsx
artflow/webapp/src/apix/apix.v4.css
artflow/webapp/src/apix/api.js
artflow/webapp/src/apix/demoData.js
artflow/webapp/src/apix/archiveAssets.js
artflow/tests/test_apix_v4_production_miniapp.py
```

## Files intentionally not imported

The production entrypoint must not import the old visual layers:

```text
apix.css
apix-art.css
apix.archive.css
apix.final-pass.css
apix.structural.css
apix.v3.css
```

`main.jsx` must stay minimal:

```jsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./apix/AppV4.jsx";
import "./apix/apix.v4.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

## API contract

V4 keeps the current backend contract:

```text
GET  /api/v1/me
GET  /api/v1/feed?source=recent&limit=60
GET  /api/v1/prompts?source=popular&limit=30
GET  /api/v1/models/image
GET  /api/v1/models/video
GET  /api/v1/history?limit=40
GET  /api/v1/plans
POST /upload
POST /api/v1/photo-prompt
POST /api/v1/prompt/improve
POST /api/v1/generate/image
POST /api/v1/generate/video
GET  /api/v1/generations/{id}
POST /api/v1/feed/{id}/like
GET  /api/v1/feed/{id}/link
POST /api/v1/generations/{id}/share
```

Auth headers are still owned by `api.js`:

```text
X-Telegram-Init-Data
X-Web-Auth-Token
```

## Visual system

V4 uses a single CSS layer with the `.v4*` namespace only.

Design principles:

- content-first feed;
- no large promotional hero blocks above the feed;
- two-column masonry feed;
- glassmorphism surfaces with restrained contrast;
- 44-48px touch-friendly controls;
- Telegram safe-area support;
- reduced-motion fallback;
- no emoji as structural icons;
- no legacy class names.

Key CSS markers:

```text
.v4App
.v4Header
.v4Grid
.v4Card
.v4Create
.v4Nav
20260801-apix-v4-clean-shell
```

## Demo media policy

Demo assets are allowed only for browser preview, empty state, and API failure fallback.

Production feed media must come from backend fields:

```text
preview_url
preview_urls
result_url
result_urls
media_urls
image_url
video_url
cover_url
```

`archiveAssets.js` is temporary. The preferred production follow-up is to move demo images to hashed `.webp` files under `public/feed/` or serve them from the media CDN.

## Local verification

```bash
cd /root/mkdir/lena_bot

git fetch origin
git switch feat/apix-miniapp-v4-production
git reset --hard origin/feat/apix-miniapp-v4-production

git rev-parse HEAD

cd artflow/webapp
rm -rf dist node_modules/.vite
npm ci
npm run build
npm run dev -- --host 0.0.0.0 --port 5173 --force
```

Open:

```text
http://SERVER_IP:5173/app/?v=v4-prod
```

Bundle checks:

```bash
grep -R "20260801-apix-v4-clean-shell" dist/assets | head
grep -R "apixHero\|studioCard\|bottomNav\|apix.archive" dist/assets | head
```

Expected:

```text
V4 marker exists
legacy classes absent
```

## Python/static regression tests

```bash
cd /root/mkdir/lena_bot/artflow
pytest tests/test_apix_v4_production_miniapp.py -q
```

Recommended broader check before staging:

```bash
pytest tests/test_apix_v4_production_miniapp.py tests/test_provider_operation_gateway.py -q
```

## Staging checklist

Verify in browser and inside Telegram WebView:

1. `/app/` opens without blank screen.
2. Header respects Telegram safe area.
3. Bottom nav does not cover feed cards or CTA.
4. Feed loads real media from `/api/v1/feed`.
5. Empty/API failure state does not look like production content.
6. Image cards render as `<img>`.
7. `.webp/.jpg/.png` previews are not rendered as `<video>`.
8. Real `.mp4/.webm/.mov` previews render as video.
9. Card open/viewer works.
10. Like works.
11. Share/link works.
12. Remix sends prompt into Create screen.
13. Create image sends `/api/v1/generate/image`.
14. Create video sends `/api/v1/generate/video`.
15. Reference upload uses `/upload`.
16. Photo prompt uses `/api/v1/photo-prompt`.
17. Prompt improve uses `/api/v1/prompt/improve`.
18. Result polling uses `/api/v1/generations/{id}`.
19. Publish uses `/api/v1/generations/{id}/share`.
20. Balance sheet opens plans without inventing payment endpoints.

## Production rollout

Merge only after:

- GitHub CI is green or failures are acknowledged as unrelated;
- `npm run build` succeeds on the server;
- Telegram WebView screenshots are approved;
- bundle checks confirm V4 and no legacy UI markers;
- rollback commit is recorded.

Deploy:

```bash
cd /root/mkdir/lena_bot/artflow
docker compose build --no-cache app
docker compose up -d app
```

Post-deploy:

```bash
curl -fsS https://apixbotai.com/api/v1/health
curl -I https://apixbotai.com/app/?v=v4
```

Cloudflare:

- purge `/app/*` after deployment;
- do not aggressively cache `index.html`;
- hashed Vite assets may be cached long-term.

## Rollback

Before deployment:

```bash
git rev-parse HEAD > /root/apix-prev-prod-commit.txt
```

Rollback:

```bash
cd /root/mkdir/lena_bot
git reset --hard $(cat /root/apix-prev-prod-commit.txt)

cd artflow
docker compose build --no-cache app
docker compose up -d app
```

## Definition of Done

V4 is ready for production when:

- `main.jsx` loads only `AppV4.jsx` and `apix.v4.css`;
- old CSS layers are absent from the bundle;
- V4 build marker is present in generated assets;
- feed renders real media without broken placeholders;
- video preview detection is extension-safe;
- Telegram auth headers are sent;
- generation/polling/share flows work;
- bottom navigation stays clear of content;
- Cloudflare serves fresh HTML;
- rollback path is proven.
