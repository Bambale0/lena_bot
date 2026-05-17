# Codex Task — Backend Web API Detail

## Scope

Work in:

```text
api/web/
api/realtime.py
api/public_files.py if stable media handling needs it
```

Do not change Telegram bot flows.  
Do not change payment/KIE webhooks unless a compatibility bug is found.

## Implement endpoints

### Required

```text
GET /api/web/health
GET /api/web/me
GET /api/web/models
GET /api/web/price-plans
GET /api/web/feed
GET /api/web/feed/top
GET /api/web/prompts
GET /api/web/prompts/{prompt_id}
GET /api/web/history
```

### Actions

```text
POST /api/web/feed/{generation_id}/like
POST /api/web/feed/{generation_id}/share
POST /api/web/prompts/{prompt_id}/like
POST /api/web/prompts/{prompt_id}/use
POST /api/web/prompts
```

### Billing/profile

```text
GET /api/web/billing/transactions
GET /api/web/referrals
```

## Rules

- use existing repository functions;
- serialize media safely;
- do not return stale local upload URLs without fallback metadata;
- auth tokens never in logs/query;
- responses use envelope.

## Tests

Add contract tests for:

- health;
- serializers;
- feed;
- prompts;
- auth failure;
- dev auth if enabled.

## Acceptance

- `/api/web/health` 200;
- auth endpoints require auth;
- prompt/feed lists work;
- no payment/KIE regressions.
