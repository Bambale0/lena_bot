# Email auth provider setup for APIX

## What is already prepared

The backend now supports real email delivery for web auth codes via SMTP.

Implemented files:
- `api/web/auth.py`
- `core/config.py`
- `.env.example`

Behavior:
- If SMTP is configured and `WEB_AUTH_EMAIL_ENABLED=true`, `/api/web/auth/contact/request` accepts email and sends a real code.
- If SMTP is not configured, the API responds honestly with `503` and suggests Telegram login instead.
- Phone login is still intentionally disabled until a real SMS provider exists.

## Recommended provider

Use **Resend API** as the first production provider.

Why:
- fastest setup for transactional OTP mail
- good developer UX
- verified sender domain already in place
- simple API key based delivery

## Env config

```env
WEB_AUTH_EMAIL_ENABLED=true
RESEND_API_KEY=your_resend_api_key
RESEND_FROM_EMAIL=no-reply@mail.your-domain.com
RESEND_FROM_NAME="APIX Studio"
SMTP_REPLY_TO=support@your-domain.com
```

Optional fallback if you later want SMTP instead of Resend:

```env
SMTP_HOST=smtp-relay.example.com
SMTP_PORT=587
SMTP_USERNAME=your_smtp_username
SMTP_PASSWORD=your_smtp_password
SMTP_FROM_EMAIL=no-reply@your-domain.com
SMTP_FROM_NAME="APIX Studio"
SMTP_REPLY_TO=support@your-domain.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

## Before enabling in production

1. Verify sender domain in Resend
2. Set SPF / DKIM / optional DMARC
3. Put real Resend credentials into `.env`
4. Set `WEB_AUTH_EMAIL_ENABLED=true`
5. Restart `artflow-webhook.service`
6. Smoke test `POST /api/web/auth/contact/request`

## Expected smoke result

Successful request should return payload like:

```json
{
  "ok": true,
  "data": {
    "contact_type": "email",
    "contact": "user@example.com",
    "expires_in": 600,
    "delivery": "provider",
    "message": "Код отправлен. Введите его, чтобы открыть кабинет."
  }
}
```
