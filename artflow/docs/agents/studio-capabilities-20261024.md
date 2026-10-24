# APIX Studio capability completion

Baseline: `86d8c69b63f5f7be5b26dedced9aca1159f34e35`. Branch: `feat/apix-studio-capability-completion`.

## Approved specification

User approves existing lilac style, asks for a central Create button and full use of existing backend capabilities in the frontend. Keep admin-only admission and all existing default/UX2 behavior. No new products, provider policy, prices, database migrations or public rollout. Work within the existing Telegram Mini App; shared consumer contracts must remain consistent with site and text bot.

Design: retain plum #171126 / #241739, lilac #A98BFF and off-white #F7F3FF. Order is Home, Ideas, Create, Projects, Profile. Create is a prominent central tactile control, with a visible label, no new animations, safe-area spacing and keyboard focus. Secondary capabilities appear in task-focused screens or progressive disclosure, not a dense endpoint dashboard.

## Fresh backend preflight

- Mounted `/api/v1` and `/api/web` routers inspected at baseline, including import-installed routes. Existing photo/video/motion, templates/feed/Pinterest, source audio, library, payments and referrals are already connected.
- Profile is read-only despite existing signed-auth `GET /api/web/me`, `PUT /me/profile`, `PUT /me/password` and uploaded photo support.
- Owner result download exists at `/api/web/generations/{id}/download`; UI currently only opens media. Public result link exists but is not directly copyable from owner details.
- Voice creation supports description, independent voice style, language, vocal segment and singer skill; current UI hardcodes RU and 0–10 seconds. Validation requires a 3–60-second segment. No new Suno operations may be invented.
- Owner detail already returns stats, recent generations, payments, ledger and withdrawals; current UI drops most of those sections.
- Library supports catalog/top/popular/collections/tag/category; UI currently uses catalog/my only. Model-associated video prompts must not be forced into an image draft.
- Payment eligibility is per selected plan: Tribute needs positive USD pricing and Lava needs `lava_plan_keys` from `/payment-options`. Existing global filtering and ruble fallback can offer an unsupported plan. Stars are intentionally unavailable and must not be exposed merely because a handler exists.
- `/prompt/improve` intentionally preserves user text. Do not advertise it as a missing AI enhancement.
- Provider operations is not mounted; provider control-plane APIs are operational administration, not a new consumer product. Preserve existing guarded operational tools rather than inventing workflows or changing financial policy.

## Acceptance and implementation plan

### 1. Central navigation

- [x] Add browser regression: Create is third of five, geometrically centered at 320/390/768/1280px; visible label, >=44px target and existing focus primitive; clicking opens actual creation hub and keeps nested destinations selected.
- [x] Observe RED (all four widths), reorder only lilac navigation and add scoped central-button styles; focused navigation GREEN. Old menu behavior remains untouched.

### 2. Consumer capability completion

- [x] RED behavioral regressions reproduced missing profile/password, voice fields, protected download/link, video routing, owner detail and collections/moderation. Supplementary negative tests cover invalid segments, stale prices, unavailable models, HTML downloads and profile conflicts.
- [x] Add pure `billing-methods` eligibility/price helper, consume existing payment options, block unsupported checkout with inline guidance. Re-read current plans/methods/Lava mapping before checkout; changed credits/price require a new explicit review. No invented currencies or stale fallback prices; same-frame double clicks guarded.
- [x] Add `account-editor` using existing signed web API. Separate profile and password forms, no password storage/logging; fresh v1 profile refresh without losing preview capability; supported draft avatar upload/removal. Async updates use captured abort signals and owner-keyed screens.
- [x] Extend music voice fields with native validation and separate voice/track style; completed voice verification lifecycle stays intact. Segment 3–60s, language code, description/style/skill mirror the server contract.
- [x] Add result download via authenticated binary transport and public link copy only after actual publication; retain privacy, originals and no automatic paid launches. Reject empty/login/JSON bodies instead of downloading them as media.
- [x] Extend library sources/collections and route prompts to an available matching model kind; fail safely if source model is unavailable, never silently change its type. Trend tags use the existing signed runner; hidden music templates fail closed because the generic music DTO has no prompt_id contract. Ordinary image/video templates retain prompt_id. Pagination appears only for catalog because other backend sources do not paginate.
- [x] Expose owner detail stats/referrals/generations/payments/withdrawals/ledger already returned by the server; keep mutation reconciliation/confirmation unchanged. Existing pending prompt moderation now has a queue and explicit approve/reject confirmation with reason validation.

### 3. Verification and delivery

- [x] Update execution ledger. Local type/build/Ruff,126 unit,19 focused Python and135 full UX2/Studio browser scenarios passed. Central Create geometry checked at320/390/768/1280px; actual mobile screenshot visually inspected. Exact-head full Linux backend/smoke/user-journey CI and final report pending below.
- [x] Independent read-only review via project requesting-code-review skill. P2 found: template selection lost the active reference projection. RED browser regression confirmed reference_urls=[]; fixed via selectGenerationInputs before prompt_id. GREEN verifies only included photo is sent and reset restores both photos/selection/original text. Re-review reports no remaining actionable findings.
- [ ] Feature PR, native auto-merge with required exact-head checks, merge-SHA CI/autodeploy and fresh public health/bundle/auth verification.

Test seams: real React app with deterministic Telegram fixture and network-boundary API doubles; pure eligibility rules via Node unit tests; existing Python auth/ownership contracts remain authoritative. All invoices/generations/password mutations in tests use synthetic data and intercepted requests. Do not perform live paid tests.

## Surface parity, authority and observability

`mini_app`: navigation and missing consumer controls; `site`: existing profile/download/voice/billing implementations and server contracts are reused, no rebranding or policy changes; `telegram_bot`: existing admin launch and generation contracts retained. Any shared billing rule fix must be checked against site/bot eligibility. No migration or secrets/config changes. Existing request errors/statuses and owner ledger provide audit evidence; never log passwords, signed initData, private recipe text or binary uploads.

Guidance used: repository planning/TDD/review/verification, baseline-ui, Anthropic frontend-design, Bambale0/claw and engineering to-spec, working-with-legacy-code. Applicable constraints retained; upstream skill-repository contribution rules do not retarget this APIX PR away from main.

## Verification in progress

- TypeScript noEmit and Vite production build passed. Existing bundle-size warning remains (no new dependencies).
- All126 frontend unit tests passed, including new provider eligibility/price and attachment filename cases. Existing production API dependency harnesses extended with the real download module, not a permissive stub.
- Full Ruff and git diff whitespace checks passed. Focused Python admission, plan-method parity and web generation parity: 19 passed.
- Full UX2/Studio:135 passed in the final run (117 baseline +18 new capability tests). Earlier run under overlapping browser processes had one existing photo-upload policy timeout; isolated photo-upload rerun and final full run passed unchanged, without removing or weakening the regression. Exact-head Linux CI remains pending; do not reuse the previous release's gate result.
- No live invoices, password changes, uploads, paid generations, tariffs, migrations, secrets or provider-policy mutations were performed during verification. Browser writes are intercepted synthetic fixtures.
