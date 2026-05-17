# Realtime generation events

APIX exposes a WebSocket channel for generation status updates. It is used by
the standalone site and Telegram Mini App to show results immediately while
keeping REST polling as a fallback.

## Endpoint

```text
GET /api/v1/ws/generations
```

Authentication is sent as the first WebSocket message because browser
WebSocket clients cannot reliably set custom headers, and query strings are
written to proxy access logs.

After the socket opens, the client must send one auth message:

```json
{ "type": "auth", "token": "web-auth-token" }
```

or:

```json
{ "type": "auth", "init_data": "telegram-init-data" }
```

The URL itself intentionally has no token/query parameters, so reverse proxy
access logs cannot leak auth data:

```text
wss://apix.chillcreative.ru/api/v1/ws/generations
```

## Messages

On connect the server sends a snapshot of currently active generations:

```json
{
  "type": "generation.snapshot",
  "items": []
}
```

Every status change that finalizes a generation is sent as:

```json
{
  "type": "generation.updated",
  "generation_id": 123,
  "id": 123,
  "model": "nano-banana-2",
  "gen_type": "image",
  "prompt": "product photo on a clean background",
  "status": "done",
  "result_url": "https://example.test/result.png",
  "result_urls": ["https://example.test/result.png"],
  "error": null,
  "credits_spent": 10,
  "created_at": "2026-05-16T18:00:00+00:00",
  "finished_at": "2026-05-16T18:01:00+00:00",
  "is_public_feed": false,
  "is_prompt_library": false
}
```

Clients may send:

```json
{ "type": "ping" }
```

The server responds with:

```json
{ "type": "pong" }
```

## Client behavior

- Use WebSocket events for immediate UI updates.
- Keep polling `/api/v1/generations/{id}` as fallback.
- On `done`, refresh balance/history and render image, video, or audio result.
- On `failed`, show a visible error and keep the failed task in history.
- Never trust events for another user; the backend only sends events to sockets
  authenticated as the generation owner.

## Deployment note

Nginx locations that proxy the app must support WebSocket upgrade:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 3600s;
```

The production nginx template in `deploy/apix.chillcreative.ru.nginx.conf`
contains a dedicated `/api/v1/ws/` location with these headers. It also strips
legacy query strings before proxying to uvicorn, while forwarding old `token`
or `init_data` values through internal headers for already-open stale clients.
