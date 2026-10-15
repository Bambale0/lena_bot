# Wan 3.0 / Wan 3.0 Prime - Neironych primary, KIE backup

## Verified: 15 October 2026

- KIE IDs: wan/3-0-video, wan/3-0-video-prime.
  Source: https://docs.kie.ai/market/wan/3-0-video
  and https://docs.kie.ai/market/wan/3-0-video-prime .
- Live Neironych GET /v1/models (using APIX credentials) returned 13 models;
  neither Wan 3.0 nor Prime is currently available to APIX.
- No invented Neironych IDs: environment fields WAN30_NEIRONYCH_MODEL_ID
  and WAN30_PRIME_NEIRONYCH_MODEL_ID are empty by default.
- With current availability, any successful Wan video would run via KIE
  backup. It cannot truthfully be described as Neironych execution.

## Implemented contract and routing layer (not yet a user-visible feature)

- api/wan30_contract.py: all 14 KIE fields, model IDs, mode semantics,
  durations, ordering, max refs, seed=0, audio=false, edit, file, link.
- wan30_max_billable_seconds computes video input seconds + output seconds;
  Auto reserves max 30 seconds.
- api/wan30_routing.py: Neironych first only with documented fields and
  verified live catalog availability, KIE backup for absent model or
  definite pre-admission rejection; never fallback after ambiguous payment.
- api/wan30_neironych_transport.py: one paid POST with stable idempotency
  headers and durable before_submit callback, no POST retry.
- api/wan30_provider.py: dual-provider orchestration.
- api/kieai_client.py: Wan requests use safe single POST, unlike the legacy
  3-attempt POST retry policy.
- New unit tests run against isolated mocks. No live paid requests sent.

## Release blockers / work remaining

This provider SDK is NOT yet a complete paid-user integration. Before
production activation:

1. Neironych must enable the two specific Wan models and advertise their
   approved IDs in GET /v1/models, or owner must accept temporary KIE-only.
2. Owner/admin must confirm APIX retail prices for both models at 480p,
   720p and 1080p. KIE credits are not APIX retail credits.
3. Add inactive model registry and price rows, then activate with admin
   approval. Ensure web, Mini App, Telegram bot share the same controls.
4. Wire scenario editor for text/first/first+last/reference/edit/file/link,
   media ownership and URL security, measured video+audio reference lengths,
   upload and file role ordering.
5. Quote, atomic balance reserve, actual-duration settlement and exactly-once
   refund for Auto; preserve existing user balances/history.
6. Expand durable Neironych admission journal, read-only reconciliation and
   polling worker; handle missing callback or restart.
7. KIE callback/polling, durable local MP4, Telegram delivery, history,
   retry/duplicate protections.
8. Full backend/integration/concurrency/browser E2E and ONE explicitly
   approved paid live generation before reporting release success.

Until these checks complete, keep Wan 3.0 OUT of the active public models.
No pricing migrations, provider POST, or production modifications in
this stage. Existing Seedance, Wan 2.7, and Nano Banana are untouched.

Rollback: revert the branch/PR; no financial or data migrations included.
