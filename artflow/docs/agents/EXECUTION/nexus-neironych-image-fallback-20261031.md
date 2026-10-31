# Nexus E-294 → Neironych image fallback (2026-10-31)

## Execution baseline

- Repository: Bambale0/lena_bot, `artflow/`; branch `fix/artflow-nexus-neironych-image-fallback-20261031`.
- Baseline: `37e454ab50eb15c025ace5f2c0fb64425103cf8a`.
- Production diagnosis: Artflow image failures on Nexus, including generation 67807; canonical Nexus GET returned `failed` with `E-294`. The separate Neironych gateway was not the source of these failures.
- No changes to prices, customer credit charges, past generations, provider credentials, or model visibility.

## Requirements and safety contract

- Primary provider remains Nexus. Only a **canonical, task-ID-matched, terminal** Nexus image failure containing `E-294` triggers fallback.
- Exact model map: Nano Banana Pro → Nano Banana Pro, Nano Banana 2 → Nano Banana 2, GPT Image 2 T2I/I2I → GPT Image 2.
- VIP variants and unrelated models are excluded. Content-policy rejections, generic errors, ambiguous 5xx submissions, and network timeouts do not trigger another paid request.
- Model routing defaults enabled as requested and is independently switchable in authenticated admin API:
  - `GET /api/web/admin/provider-routing/image-fallbacks`
  - `PUT /api/web/admin/provider-routing/image-fallbacks/{model_key}` with `{"enabled":false}`.
- Uses existing `provider_routing_settings` and `provider_routing_audit` (model keys prefixed `image-fallback:`); no DB migration or raw SQL toggle.
- A PostgreSQL row lock and `task_id` comparison reserve one fallback per generation; original Nexus task ID and reason are stored with the deterministic fallback ID.
- The Neironych POST uses `Idempotency-Key` and `X-Client-Request-Id` derived from the persisted generation.
- On ambiguous Neironych status, **do not retry any paid POST**. A scheduled, read-only provider GET reconciles the original fallback request; the existing Neironych SLA refund policy applies from fallback start time.
- Keep the original customer reserve; complete the same generation or refund once through `fail_generation_and_refund`. No second user charge.
- Never log image content, prompts, references, credentials, or bearer headers.

## Surface parity

- Site: shared generation status and existing updates; provider transitions are internal.
- Mini App: shared generation status/history and image session final output.
- Telegram bot: same provider path, existing success/failure notifications.
- No user-facing provider branding or cost information.

## Verification and rollout gates

- Isolated unit tests: 19/19 passed against source worktree; adapters/conditions/duplicate claim semantics.
- Python compileall: passed on changed backend tree.
- Existing integration/regression suites, GitHub PR checks, deployed SHA, and public health: verify before calling production shipped.
- No paid smoke in live production without explicit budget authorization; a read-only Neironych model catalog reports all three models as production with prior smoke status.
- Rollback: admin-disable routes individually, then revert PR via protected main CI if needed.
