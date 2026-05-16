# CODEX TASK — Build APIX Prompt Riot Zine Web Layer

Рабочая папка: `artflow/`

## Objective

Implement a web product layer for APIX Artflow using the **Prompt Riot Zine** visual direction and existing Artflow backend logic.

The web layer must expose API endpoints and a static prototype UI that can be served by FastAPI. It should not break the Telegram bot, KIE webhook, payment webhooks, migrations, prompt marketplace, feed, or image-session flow.

## Current product logic to reuse

Use existing Artflow concepts:

- `User.tg_id`
- `User.credits`
- `ImageSession`
- `Generation`
- `UserPrompt`
- `PromptStatus`
- `ModelCost`
- `PricePlan`
- prompt reward logic
- feed generation logic
- KIE webhook-first generation flow

## Deliverables

### 1. Add web API router

Create `api/web/` module with routers:

- `health.py`
- `deps.py`
- `schemas.py`
- `me.py`
- `models.py`
- `feed.py`
- `prompts.py`
- `sessions.py`
- `history.py`
- `billing.py`
- `referrals.py`

Mount in `main.py`:

```python
from api.web import router as web_router
app.include_router(web_router, prefix="/api/web")
```

### 2. Add static UI prototype

Create:

```text
web/static/prompt-riot/index.html
web/static/prompt-riot/styles.css
web/static/prompt-riot/app.js
```

Mount in FastAPI:

```python
app.mount("/app", StaticFiles(directory="web/static/prompt-riot", html=True), name="prompt_riot_app")
```

The prototype must visually match `design_refs/`:
- torn paper cards;
- black/pink/cyan/yellow palette;
- prompt marketplace grid;
- active series screen;
- feed;
- billing;
- profile/referrals.

It can use mock rendering when auth is missing, but API calls must be real where endpoints exist.

### 3. Implement API endpoints

Minimum working endpoints:

```text
GET /api/web/health
GET /api/web/me
GET /api/web/models
GET /api/web/price-plans
GET /api/web/feed
GET /api/web/prompts
GET /api/web/history
GET /api/web/image-sessions/active
```

Use dev auth header only if `APIX_WEB_DEV_AUTH=1`:

```text
X-Dev-Tg-Id: <telegram id>
```

### 4. Implement prompt endpoints

Use existing `db.prompt_repository` functions.

Endpoints:
- list prompts by source/tag;
- prompt detail;
- like prompt;
- use prompt;
- submit prompt.

For prompt submission, support:
- title optional;
- description optional;
- prompt_text required;
- tags optional;
- preview_url optional;
- model optional.

Default status should remain moderation-safe: `pending`.

### 5. Implement feed endpoints

Use existing `repo.get_feed_generations`, `repo.get_top_day_generations`, `repo.like_feed_generation`, `repo.increment_feed_share`.

Return compact cards:
- id
- result_url
- prompt
- model
- author label
- likes
- remix_count
- shares
- aspect_ratio
- quality
- created_at

### 6. Implement active image session endpoints

Endpoints:
- get active session;
- create new session from model/settings;
- archive session.

Generation launch endpoints can be added, but if you cannot safely wire generation end-to-end, return `501` with clear message. Do not fake successful generation.

### 7. Tests

Add tests where possible:
- schema serialization;
- web health endpoint;
- feed serialization with fake objects or monkeypatched repo;
- prompt listing logic;
- dev auth behavior.

### 8. Do not over-refactor

This is a product web-layer task, not a rewrite.

Do not move Telegram handlers.
Do not rename database columns.
Do not change KIE webhook behavior except if needed for shared helpers.
Do not remove existing prompt marketplace bot handlers.

## Acceptance checklist

- `/health` still returns existing APIX health.
- `/api/web/health` returns `{ok: true}`.
- `/app/` loads the Prompt Riot prototype.
- Existing Telegram webhook route still exists.
- Existing KIE webhook route still exists.
- `python -m compileall core api db bot main.py` passes.
- Tests are added or existing tests are not made worse.
- No production secrets are logged or embedded.
