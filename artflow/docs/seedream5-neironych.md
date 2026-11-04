# Seedream 5 Pro routing

Both public model keys use the shared image service on site, mini_app and telegram_bot.
Neironych is the bootstrap primary (SEEDREAM_5_PRIMARY_PROVIDER=neironych);
an authenticated admin can select Neironych or KIE in the Telegram admin menu or
GET/PUT /api/web/admin/provider-routing/seedream-5-pro with
{"primary_provider":"neironych"} (or "kie"). Changes use the existing routing table and audit journal.
No schema, tariff, customer credit or public parameter changes.

Neironych contract: seedream-5.0-pro, POST /v1/images/generations or /v1/images/edits,
basic = 1k, high = 2k, one image, up to eight ordered references.
Existing advertised nine/ten-reference requests keep KIE. The previous KIE route remains selectable.
Transport and provider contract verified against KSU PR #577.

Before paid submission each surface commits a stable provider task identity. A definite
rejection allows KIE fallback; timeout/network/5xx/malformed results never trigger another
paid submission. Existing refund SLA, scheduled reconciliation and supplier review apply.
Completed images are decoded and persisted to APIX storage.
