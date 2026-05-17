# APIX Current Surface Inventory

Дата: 2026-05-17

Документ фиксирует baseline standalone site перед доведением Prompt Riot spec pack.

## Frontend Surfaces

| Surface | Path | Code | Notes |
|---|---|---|---|
| Public/app SPA | `/` | `landing/index.html`, `landing/js/riot-site.js`, `landing/css/riot-site.css` | Current Prompt Riot standalone entrypoint. |
| Legacy landing pages | `/account.html`, `/features.html`, `/guide.html`, `/contact.html` | `landing/*.html`, `landing/js/main.js`, `landing/css/styles.css` | Static legacy pages; not primary app-mode. |
| Telegram Mini App | `/app` | `web/static/prompt-riot/`, `webapp/` | Separate surface; do not mix with standalone site. |

## Current SPA Routes

`landing/js/riot-site.js` currently registers:

- `home`
- `examples`
- `features`
- `studio`
- `prompts`
- `feed`
- `works`
- `billing`
- `profile`

Implemented baseline capabilities:

- guest/public home with hero, examples, feed preview, prompt preview;
- authenticated dashboard;
- image/video/music/assistant studio forms;
- model picker, dynamic settings, review summary;
- reference upload/link handling;
- local queue persisted in `localStorage`;
- realtime WebSocket with first-message auth;
- polling fallback for active queue items;
- feed/prompt actions with busy state;
- Telegram Login Widget auth.

Known UX gaps to close:

- detail drawers for feed/prompt/result;
- richer billing transaction/referral panels;
- explicit inline validation messages and disabled launch state;
- richer mobile app shell and bottom tabs;
- admin moderation route for web admins.

## Web API Endpoints

Mounted in `main.py`:

```text
app.include_router(web_router, prefix="/api/web")
```

Current `api/web/` endpoints:

- `GET /api/web/health`
- `GET /api/web/auth/config`
- `POST /api/web/auth/telegram-login`
- `GET /api/web/me`
- `GET /api/web/models`
- `GET /api/web/price-plans`
- `GET /api/web/feed`
- `GET /api/web/feed/top`
- `POST /api/web/feed/{generation_id}/like`
- `POST /api/web/feed/{generation_id}/share`
- `GET /api/web/prompts`
- `GET /api/web/prompts/{prompt_id}`
- `POST /api/web/prompts/{prompt_id}/like`
- `POST /api/web/prompts/{prompt_id}/use`
- `POST /api/web/prompts`
- `GET /api/web/history`
- `GET /api/web/image-sessions/active`
- `POST /api/web/image-sessions`
- `POST /api/web/image-sessions/{session_id}/archive`

Known API gaps to close:

- grouped `/api/web/models` contract;
- `/api/web/billing/transactions`;
- `/api/web/referrals`;
- admin prompt moderation endpoints;
- richer serializers for `result_urls`, prompt visibility, action eligibility, language and payment/referral state.

## Generation API Used By Site

Current standalone SPA calls compatible `/api/v1/*` endpoints:

- `GET /api/v1/models/image`
- `GET /api/v1/models/video`
- `GET /api/v1/models/music`
- `GET /api/v1/history`
- `GET /api/v1/generations/{id}`
- `POST /api/v1/generate/image`
- `POST /api/v1/generate/video`
- `POST /api/v1/generate/music`
- `POST /api/v1/assistant`
- `POST /api/v1/photo-prompt`
- `POST /api/v1/prompt/improve`
- `POST /api/v1/feed/{gen_id}/remix`

## Realtime

Mounted in `main.py`:

```text
app.include_router(realtime_router)
```

Endpoint:

```text
GET /api/v1/ws/generations
```

Current behavior:

- accepts WebSocket connection;
- reads auth from first JSON message `{ "type": "auth", "token": "..." }`;
- retains legacy header/query auth compatibility;
- sends `generation.snapshot` for active `pending`/`processing` history items;
- accepts `ping` and responds with `pong`;
- exposes `publish_generation_event(gen)` for lifecycle push.

Risk to monitor:

- legacy query auth remains supported for compatibility, but standalone site uses first-message auth and should not put tokens into URLs.

## Stable Media Handling

Current serializers in `api/web/schemas.py` and `api/realtime.py` use `api.public_files.public_url_is_available`.

Behavior:

- missing local `/static/upload/*` files are hidden from payloads;
- external CDN/provider URLs are treated as available;
- frontend media frames show a visible fallback on broken load.

## Verification Baseline

Required before delivery on code changes:

```bash
node --check landing/js/riot-site.js
python -m compileall api db main.py
tools/codex_static_checks.sh
```

