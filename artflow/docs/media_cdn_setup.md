# APIX media CDN

## Target

- public media origin: `https://media.apixbotai.com/uploads/`;
- local storage remains `artflow/static/upload`;
- Nginx serves files directly from the shared read-only volume;
- Cloudflare caches only the `/uploads/` path;
- old `https://apixbotai.com/static/upload/...` URLs remain readable by the application.

## Safe rollout order

Do not deploy `nginx-media.conf` before the origin certificate exists. Nginx refuses to start when a configured certificate file is missing.

### 1. Check the HTTP ACME webroot

Run on the production host while the current Nginx container is still running:

```bash
mkdir -p /var/www/certbot/.well-known/acme-challenge
printf 'media-acme-ok\n' > /var/www/certbot/.well-known/acme-challenge/probe
curl -fsS http://media.apixbotai.com/.well-known/acme-challenge/probe
```

Expected output:

```text
media-acme-ok
```

If Cloudflare prevents this check, temporarily switch the `media` DNS record to DNS only for certificate issuance, then turn the proxy back on.

### 2. Issue the origin certificate

The host already uses Certbot and `/var/www/certbot` for HTTP-01 challenges:

```bash
certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --domain media.apixbotai.com \
  --non-interactive \
  --agree-tos \
  --keep-until-expiring
```

Verify:

```bash
test -s /etc/letsencrypt/live/media.apixbotai.com/fullchain.pem
test -s /etc/letsencrypt/live/media.apixbotai.com/privkey.pem
```

### 3. Configure the application

Add to `artflow/.env`:

```dotenv
STATIC_UPLOAD_DIR=static/upload
STATIC_UPLOAD_URL_PATH=/static/upload
STATIC_UPLOAD_PUBLIC_BASE_URL=https://media.apixbotai.com
STATIC_UPLOAD_PUBLIC_URL_PATH=/uploads
```

The first two values are the internal storage/mount contract. The second pair controls only generated public URLs.

### 4. Deploy

Use the normal production deploy after the certificate and `.env` values exist.

The deploy script checks the certificate before restarting Nginx.

### 5. Cloudflare

Use proxied DNS for `media.apixbotai.com` after certificate issuance.

Set SSL/TLS encryption mode to **Full (strict)**.

Create one Cache Rule with expression:

```text
(http.host eq "media.apixbotai.com" and starts_with(http.request.uri.path, "/uploads/"))
```

Actions:

- Cache eligibility: Eligible for cache;
- Edge TTL: Ignore cache-control and use 1 year;
- Browser TTL: Respect existing headers, or override to 1 year;
- do not apply the rule to `/health` or any future dynamic path.

The origin already emits:

```text
Cache-Control: public, max-age=31536000, s-maxage=31536000, immutable
```

Media filenames are content-addressed or versioned, so immutable caching is safe.

## Verification

```bash
curl -fsSI https://media.apixbotai.com/health
```

Expected:

```text
HTTP/2 200
cache-control: no-store
```

Select an existing file:

```bash
FILE="$(find /root/mkdir/lena_bot/artflow/static/upload -type f | head -1)"
REL="${FILE#/root/mkdir/lena_bot/artflow/static/upload/}"
echo "https://media.apixbotai.com/uploads/${REL}"
curl -fsSI "https://media.apixbotai.com/uploads/${REL}"
```

Expected origin headers include:

```text
cache-control: public, max-age=31536000, s-maxage=31536000, immutable
access-control-allow-origin: *
accept-ranges: bytes
```

Request the same file twice through Cloudflare and inspect:

```bash
curl -fsSI "https://media.apixbotai.com/uploads/${REL}" | grep -Ei 'cf-cache-status|age|cache-control|content-type'
curl -fsSI "https://media.apixbotai.com/uploads/${REL}" | grep -Ei 'cf-cache-status|age|cache-control|content-type'
```

The first request is normally `MISS`; a later request should become `HIT` with a positive `Age` header.

## Rollback

Remove or empty these two values in `.env` and redeploy:

```dotenv
STATIC_UPLOAD_PUBLIC_BASE_URL=
STATIC_UPLOAD_PUBLIC_URL_PATH=
```

The application will immediately return to `WEBHOOK_URL + STATIC_UPLOAD_URL_PATH`. Existing files and database rows are not moved or deleted.
