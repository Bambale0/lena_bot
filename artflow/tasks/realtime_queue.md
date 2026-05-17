# Codex Task — Realtime and Queue

## Backend

- WebSocket auth first message:
  `{ "type": "auth", "token": "..." }`
- Snapshot active tasks after auth.
- Send event on generation done.
- Send event on generation failed.
- Heartbeat ping/pong.
- Clean stale sockets.
- Keep polling fallback.

## Frontend

- Connect after auth.
- Do not put token in query string.
- Limit reconnect attempts.
- Continue polling if WS fails.
- Update queue/history/balance/result on events.
- Deduplicate result toasts.

## Acceptance

- result appears without refresh;
- WS loss does not break queue;
- no token/init_data in access logs;
- no duplicate toast.
