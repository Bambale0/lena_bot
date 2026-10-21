# Nginx / ACME repair — 2026-10-21

Baseline: `9f7bff637ee8112aeee880d475a867db339d3e4c`.
Branch: `fix/nginx-acme-renewal-20261021`; isolated worktree.

User outcome: eliminate obsolete-host upstream failures, restore certificate
renewal for active APIX hosts, and verify live TLS and HTTP-01 without downtime.
The owner confirmed that the root IDN domain (including www) and tanyapp have
intentionally moved to other servers. DNS/new servers must remain unchanged.

Evidence: the root IDN HTTPS location proxies to container loopback with no
listener. Both migrated domains serve challenge probes locally, but public DNS
reaches different servers and returns 404. testapi/apix's shared certificate
expired September 28; its standalone authenticator conflicts with port 80
owned by Docker. Public HTTP-01 probes for testapi, apix, APIX and media work.
APIX's certificate is valid through December 6. PostgreSQL/Redis are healthy.

Scope: Nginx infrastructure, host Certbot configuration and operational docs;
no schema, prices, provider calls, auth or application configuration changes.
site and mini_app retain their application routes; telegram_bot retains its
webhook/API. Active Banano subdomain routes remain; only owner-confirmed migrated
vhosts are retired. Unknown hosts must never fall through to an application.

Reuse: mounted Certbot webroot, existing certificate lineages, deploy reload hook,
official-Nginx synthetic-TLS test fixture, protected PR CI/autodeploy.
Risks: default-vhost changes; certificate renewal must retain SANs; no private
keys/config credentials in Git or output. Keep retired renewal files outside
Certbot's scan glob for reversible rollback; do not delete/revoke certificates.
Observability: nginx -t, HTTP probe body/status, TLS SAN/expiry, timer/service exit,
new error logs. No test sends notifications or incurs provider charges.

Test seams: actual isolated Nginx HTTP-01 and TLS virtual-host selection; existing
canonical config syntax test; live Certbot staging validation and production
renewal; public health and active-host TLS after exact-SHA autodeploy.

1. [x] Audit instructions, docs, Compose, CI, Nginx, tests, DNS and renewal state.
2. [x] Owner confirms migrated domain ownership; preserve DNS/new services.
3. [x] Reproduce isolated unknown-host routing / explicit active HTTP-01.
4. [x] Remove retired vhosts, add safe defaults and explicit APIX HTTP host.
5. [ ] Local regression/syntax checks and open code review.
6. [ ] Reconfigure/renew testapi; archive obsolete renewal configs with backup.
7. [ ] Protected PR checks, auto-merge and Production Autodeploy exact SHA.
8. [ ] Verify live TLS/HTTP-01/health, timer renewal, logs; record evidence.

Runtime progress: Certbot 2.9 reconfigure successfully validated testapi/apix with
staging and saved webroot. Production renewal succeeded; both public HTTPS names
now verify with expiry 2027-01-19. Existing deploy hooks validated and reloaded
Nginx without downtime. User clarified to renew all certificates hosted here,
including old aliases; alias routing remains unchanged. Further public TLS/DNS
inventory shows alena IDN and HappyFox API also terminate on the separate
89.125.51.145 host with independently newer public certificates. Their local
lineages are obsolete too; retain files, exclude local renewal, no remote write.
Local regressions: RED retired root returned 301; after removal/safe defaults,
20 HTTP/TLS/config tests passed using isolated official Nginx and synthetic TLS.
Ruff and git diff --check passed. OCR delegate preview excludes config/docs/tests
by defaults; all five changed files will additionally receive manual review.
