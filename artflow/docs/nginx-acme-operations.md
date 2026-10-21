# Nginx certificate ownership and renewal

The HTTP-01 webroot is `/var/www/certbot`, mounted read-only in Nginx.
Certbot runs on the host via `certbot.timer`; never stop Nginx to bind port 80.
Use Certbot's `reconfigure --cert-name NAME --webroot --webroot-path
/var/www/certbot --non-interactive` to validate in staging and persist settings.
Then `certbot renew --cert-name NAME --non-interactive` renews a due certificate.
The existing host deploy hook checks `nginx -t` and reloads Nginx.

As of 2026-10-21 the locally owned lineages are:

| Certificate name | Covered names |
| --- | --- |
| apixbotai.com | apixbotai.com |
| media.apixbotai.com | media.apixbotai.com |
| testapi.chillcreative.ru | testapi.chillcreative.ru, apix.chillcreative.ru |
| alena.chillcreative.ru | alena.chillcreative.ru |
| tbank.apixbotai.com | tbank.apixbotai.com |

The old testapi/apix aliases remain served here. Root IDN and www, tanyapp,
alena IDN and api.happy-fox.online terminate on other servers. Do not change DNS
or renew those certificates from APIX. Preserve their local certificate files;
archive their renewal `.conf` files outside `/etc/letsencrypt/renewal` so the
local timer does not attempt impossible HTTP-01 validation. This action is
reversible by restoring the files after domain ownership is moved back. Existing
alena IDN local routes remain for compatibility but receive no public DNS traffic.
Root IDN and tanyapp virtual hosts have been retired from this configuration.

Before renewal, put a randomly named temporary nonsecret probe in
`/var/www/certbot/.well-known/acme-challenge/`, verify the exact content through
**public HTTP** for every certificate SAN, and remove only the probe you created.
A local Host-header request cannot establish public DNS ownership. For proxied
names, also verify origin TLS separately from the edge certificate.

Verify `certbot renew --dry-run --non-interactive --no-random-sleep-on-renew`,
`systemctl status certbot.timer`, and a real `systemctl start certbot.service`.
Check public TLS hostname/chain/expiry and `https://apixbotai.com/api/v1/health`.
Nginx missing-file ACME 404s alone do not prove a failed renewal: correlate them
with Certbot's exact challenge and service result.

Changes to tracked Nginx config go through protected PR CI and Production
Autodeploy; do not manually checkout/build production. Isolated regressions run:

```sh
APIX_TEST_NGINX_IMAGE=nginx:alpine pytest -q tests/test_video_prompt_nginx_config.py tests/test_media_cdn_config.py
```

Rollback Nginx through a revert PR. Restore archived renewal configs only when
this server again owns their public challenges. Never restore an expired
certificate over a newly renewed one.
