# API and State Contract — APIX Web Studio

## 1. Response envelope

Success:

```json
{
  "ok": true,
  "data": {}
}
```

Error:

```json
{
  "ok": false,
  "error": "human readable message",
  "code": "optional_code"
}
```

## 2. Frontend state tree

Recommended state:

```js
const state = {
  auth: {
    status: "guest | loading | authenticated | error",
    token: null,
    user: null
  },
  ui: {
    route: "home",
    drawer: null,
    toastQueue: [],
    isMobile: false
  },
  studio: {
    mode: null,
    step: "mode",
    prompt: "",
    media: [],
    model: null,
    settings: {},
    review: null,
    validation: {},
    activeSession: null
  },
  queue: {
    wsStatus: "idle | connected | reconnecting | fallback",
    items: [],
    seenResultIds: {}
  },
  feed: {
    source: "recent",
    filters: {},
    items: [],
    loading: false,
    error: null
  },
  prompts: {
    source: "popular",
    filters: {},
    items: [],
    loading: false,
    error: null
  },
  history: {
    items: [],
    loading: false
  },
  billing: {
    plans: [],
    transactions: [],
    pendingPayment: null
  }
}
```

## 3. Required API endpoints

### Health

```text
GET /api/web/health
```

Response:

```json
{
  "ok": true,
  "data": {
    "service": "api-web",
    "status": "ok"
  }
}
```

### Me

```text
GET /api/web/me
```

Response:

```json
{
  "ok": true,
  "data": {
    "id": 1,
    "tg_id": 123456789,
    "username": "creator",
    "full_name": "Creator",
    "credits": 124,
    "referral_code": "abc",
    "language": "ru",
    "is_admin": false
  }
}
```

### Models

```text
GET /api/web/models
```

Response grouped:

```json
{
  "ok": true,
  "data": {
    "image": [],
    "video": [],
    "music": []
  }
}
```

Model item:

```json
{
  "model_key": "nano-banana-pro",
  "display_name": "Nano Banana Pro",
  "technical_key": "nano-banana-pro",
  "gen_type": "image",
  "credits": 4,
  "capabilities": ["text", "image", "9:16"],
  "is_active": true
}
```

### Price plans

```text
GET /api/web/price-plans
```

### Feed

```text
GET /api/web/feed?source=recent&limit=30
GET /api/web/feed?source=top_day&limit=10
```

Feed card:

```json
{
  "id": 42,
  "type": "image",
  "result_url": "https://...",
  "result_urls": ["https://..."],
  "prompt": "text",
  "prompt_visibility": "public | hidden | excerpt",
  "model": "nano-banana-pro",
  "author": "@creator",
  "likes": 12,
  "shares": 3,
  "remix_count": 4,
  "aspect_ratio": "9:16",
  "quality": "4K",
  "created_at": "2026-05-16T00:00:00Z",
  "can_remix": true,
  "can_use_reference": true
}
```

### Prompt list

```text
GET /api/web/prompts?source=popular&tag=cinematic&limit=30
```

Prompt card:

```json
{
  "id": 7,
  "title": "Cyberpunk Face",
  "description": "short",
  "prompt_text": "full prompt",
  "preview_url": "https://...",
  "model": "nano-banana-pro",
  "tags": ["cyberpunk"],
  "likes": 40,
  "uses_count": 120,
  "status": "approved",
  "is_mine": false
}
```

### Active session

```text
GET /api/v1/generations/active
```

or if web-specific exists:

```text
GET /api/web/image-sessions/active
```

Session:

```json
{
  "id": 10,
  "model": "nano-banana-pro",
  "mode": "text",
  "aspect_ratio": "9:16",
  "quality": "4K",
  "count": 1,
  "base_prompt": "...",
  "last_prompt": "...",
  "reference_url": "...",
  "last_result_url": "...",
  "last_generation_id": 42,
  "status": "active"
}
```

## 4. WebSocket contract

Endpoint:

```text
/api/v1/ws/generations
```

Auth first message:

```json
{
  "type": "auth",
  "token": "..."
}
```

Server snapshot:

```json
{
  "type": "snapshot",
  "items": []
}
```

Generation update:

```json
{
  "type": "generation.update",
  "generation_id": 42,
  "status": "processing",
  "model": "nano-banana-pro",
  "cost": 4
}
```

Generation done:

```json
{
  "type": "generation.done",
  "generation_id": 42,
  "result_url": "https://...",
  "result_urls": ["https://..."],
  "credits": 120
}
```

Generation failed:

```json
{
  "type": "generation.failed",
  "generation_id": 42,
  "error": "Provider failed",
  "refunded": true,
  "credits": 124
}
```

Heartbeat:

```json
{
  "type": "ping",
  "ts": 1710000000
}
```

## 5. Validation rules

### Studio

Run button disabled if:

- no auth;
- prompt required but empty;
- media required but missing;
- model missing;
- insufficient credits;
- upload in progress;
- invalid file.

### Prompt submit

Submit disabled if:

- prompt_text empty;
- preview required by current policy and missing;
- moderation already pending with same content;
- user over active prompt limit.

### Billing

Payment disabled if:

- provider disabled;
- plan missing;
- previous invoice creation in progress;
- user not authenticated.

## 6. Media URL handling

If result URL is broken:

- show placeholder;
- keep actions that do not need media;
- allow retry fetch;
- do not show raw broken image icon;
- do not remove card.

If local `/static/upload/*` missing:

- API should return safe URL state if possible;
- frontend should fallback gracefully.

## 7. Events

Client events without secrets:

- page_view;
- login_start;
- login_success;
- studio_step_change;
- generation_review_opened;
- generation_started;
- generation_done_seen;
- generation_failed_seen;
- prompt_used;
- feed_remix_clicked;
- payment_started;
- payment_status_seen.

Never log:

- token;
- initData;
- full auth payload;
- provider secrets.
