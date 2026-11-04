# Nano Banana Pro / Neironych admin lab — 2026-11-04

Baseline: c2094922dd076f3283507296d5cf97911a15f759.
Existing: admin Provider Test Lab, IsAdmin filters, safe synchronous Neironych image transport, status reconciliation by client UUID.
Missing: Nano Banana Pro Neironych lab entry and request builder.
Reuse: existing HTTPS transport, bounded timeout, base64 verification/persistence, Telegram public media mirror, Redis NX claim.
Contract: upstream Bambale0/ooo app/api/partner_reference.py image-nano-pro example; live authenticated GET /v1/models returned nano-banana-pro (200).
Scope: telegram_bot admin-only; site and mini_app not applicable to this isolated Telegram lab. Public routing and APIX balances unchanged.
No migrations. Credentials/base URL/timeout/Redis from existing settings. Protocol model ID and reviewed capability subset in adapter, no copied tariffs.
Seams: menu callback, builder validation, transport contract, handler authorization and duplicate submission.
Plan: (1) failing menu/contract regression (observed 8 failures), (2) adapter+router+registration, (3) focused regressions/security/concurrency/error cases, (4) exact-head CI and normal PR autodeploy.
Risks: ambiguous provider outcome must never automatically resubmit; Redis unavailable fails closed. Permanent per-request claims prevent duplicate costs; new UUID requires explicit changed input/new test. Status recovery retains correlation.
Verification: 96 focused tests passed (13 new lab tests, existing Seedance admin/Seedream/Nexus/callback regressions). Ruff passed. Existing python_multipart deprecation warning only. Exact-head CI/deploy pending.
Matrix: unit/contract/authorization/idempotency/bot handler delivery covered; database/migrations and site/mini_app N/A (isolated admin lab, no persistence schema or public behavior changes). Existing transport supplies timeout, image decoding, and persistence. Redis claim is atomic NX and fails closed. Logs include request/admin IDs, no prompts/references/keys. Rollback: revert PR; no data migration.
Guidance reviewed: primary TDD; project-local TDD/FSM conventions; claw FSM_USER_FLOWS; wondelai clean-architecture adapter separation; Anthropic webapp-testing inspected, browser checks not applicable to Telegram-only lab.

