# APIX lilac studio — backend preflight and execution

Baseline: `43c27c7e7015f06025ca4211b50e9af2f522a5ca`, branch `feat/apix-lilac-admin-studio`.

## Accepted scope

User approved the lilac UI concept and requested a complete implementation after auditing the backend, with a visible main-menu button initially limited to administrators. On 2026-10-24 the user explicitly selected **all existing APIX functions first**, excluding creation of missing PromptX products in this delivery.

The new interface is opt-in (`ux=3`). Existing default and UX2 interfaces remain available. Server membership in `ADMIN_IDS` is the sole preview authority; URL, browser storage and Telegram's unsigned user object never grant access. No public rollout, new tariffs, provider routing, financial policy or database schema changes.

## Backend audit completed before implementation

Read-only independent reviewer checked authenticated routes, typed frontend, ORM and legacy surfaces at baseline.

| Capability | Existing authority | Integration |
|---|---|---|
| Identity / permissions | `/api/v1/me`, `/me/permissions`; signed Telegram auth; `miniapp_ux2_available` | Add server-guarded preview admission; use existing membership, revalidate on core refresh |
| Photo / video / motion | `/models/image`, `/models/video`, `/generate/image`, `/generate/video/quote`, `/generate/video` | Keep current typed forms, uploads, limits, confirmation and submission handlers |
| Music and voice | `/models/music`, `/generate/music`, `/music/voices` and refresh/verify/source-audio contracts | Dedicated reachable music view using current model/voice API; preserve user balance/history refresh |
| Assistant / analysis | `/assistant`, `/photo-prompt`, `/video-prompt`, `/prompt/improve` | Fix history transport from `text` to `content`; dedicated task destinations |
| Feed / repeat | `/feed`, likes, share links, quotes/remix; existing signed runner | Reuse privacy-preserving runner; do not expose creator's hidden prompt |
| Templates / trends | `/trends`, upload, checkout, run | Reuse `TrendRunner`, not obsolete prepare-recipe assumptions |
| Pinterest | `/services/pinterest`, signed upload/run | Reuse installed service portal |
| Prompt library | `/prompts`, `/prompts/my`, detail, like/use/deactivate/submit/link | Expose actual moderated catalogue and own submissions; publication is explicitly public |
| History / results | `/history`, `/generations/{id}`, ownership/polling | Reuse complete pagination, result media and error states; add repeat/animate using authorized owner data |
| Billing | `/plans`, `/payment-methods`, `/topup/*`, `/api/web/billing/transactions` | Actual catalogue/active methods only; no invented fees/prices or fake success |
| Referrals | `/referrals`, withdrawals/exchange | Reuse current partner cabinet; server validates financial actions |
| Help / settings / admin | `/help`, language settings, existing authenticated admin routes | Real help and direct access to existing guarded owner tools |

Missing product APIs: saved reference collections, project DAGs, a full timeline editor, gifts/reward centre, promo HTTP redemption, astrology, jobs marketplace, influencer service. Existing image series, video trim inputs, welcome/referral bonuses and prompt marketplace must not be misrepresented as those products. Unmounted `provider_operations` routes are not usable product APIs.

Audit findings to repair in this delivery:

1. Assistant history uses `{role,text}` on the client but server expects `{role,content}`.
2. Existing “save prompt” label masks public publication; obtain explicit confirmation and label public action accurately.
3. Typed `/app` requires signed Telegram initData; standalone cookie auth is a different transport. Do not claim site support without testing that path.
4. Prepared trend descriptor intentionally omits hidden recipe; keep signed runner.

## Acceptance criteria

- Admin sees a prominent new studio button in bot main menu and current Mini App; ordinary user never sees it.
- Direct preview request is authenticated, admin-only and no-store; ordinary/unsigned/banned users cannot enter by query/storage edits.
- Repeated core identity refresh revokes preview immediately when permission disappears; existing UX2 remains isolated.
- Home, create, ideas, projects, profile form a clear five-item navigation at 320px–desktop. All supported functions remain reachable.
- Forms use existing model/capability/price responses and submission flows. No additional paid calls just for browsing.
- Prompts catalogue supports search, paging, own submissions and explicit public submission; hidden prompts remain server-side.
- Music, chat and tools have clear individual entrances and loading/error/empty states.
- Owner results preserve originals, multi-output media, existing polling, publication and public prompt library semantics.
- Native Telegram back navigation, dialogs, keyboard focus and reduced motion work.
- Focused Python auth/menu contracts, frontend unit/type/build, browser journeys, independent review, required exact-commit CI, protected PR and normal autodeploy verification.

## Design contract

Use approved deep plum `#171126`, raised plum `#241739`, lilac `#A98BFF`, pale lavender `#D8CCFF`, off-white `#F7F3FF`; consistent with approved boards. Existing font stack; semantic shared components; no new UI dependencies. Large visual task cards use real available feed/trend previews, never invented customer activity. Main actions named by result. Prices remain credits as reported by APIX, not fictional token/ruble conversion.

## Execution plan

1. [x] Current branch audit, contracts, permissions, skills and independent baseline review.
2. [x] Failing server preview/menu and transport regressions, then guarded admission and menu button.
3. [x] Opt-in lilac shell, home/catalogue/library/help/billing, dedicated creation destinations and current forms/runner reuse.
4. [x] Result actions, explicit public publication, chat history repair, music lifecycle integration.
5. [x] Browser regression journeys: admin/user, query denial, revoked capability, navigation, catalogue/library, generation success/failure, payments, assistant history, mobile overflow.
6. [ ] Focused/full applicable checks; independent standards/spec review completed with no remaining blockers; final exact-head CI pending.
7. [ ] Feature PR/native auto-merge; exact-head CI; merge-SHA autodeploy/health verification.

## Compatibility / risk decisions

| Tasks | Shared interface | Decision |
|---|---|---|
| 2 → 3 | Preview admission and capability | Server manifest required; no admission from client flag alone |
| 3 → 4 | Existing App callbacks / drafts | Integrate into the current typed App; do not fork charging, model or upload pipelines |
| 3 → 5 | `data-ui-version=3` | Scope all visual/navigation changes to opt-in preview; existing tests pin defaults |
| 4 → 5 | Public actions / data ownership | Explicit confirmation; no hidden-prompt reconstruction; all writes through existing server auth |

Backend business logic is reused. No migration. Site remains its existing standalone Studio; new Mini App link is available only in authenticated Telegram context. Telegram gets admin-only opt-in link, user menus unchanged. No customer secrets or private payloads in artifacts. No paid provider smoke without explicit budget; provider transport regressions and CI establish integration evidence.

## Skills and verification record

Read repository planning/TDD/review guidance, `Bambale0/skills/skills/engineering/to-spec`, `Bambale0/claw/AGENTS`, `wondelai/skills/working-with-legacy-code`, Anthropic `frontend-design`; audit runner privacy before integration. Production and test results will be appended as verified.

### Implementation and verification evidence

- Auth/menu regressions first failed (404/missing admin link), then passed after server admission and menu implementation. Latest focused Python run: **23 passed**, including default UX2/menu and accessible result contracts.
- Frontend unit **123 passed**; TypeScript checks/build pass. Vite warns about the existing >500kB main chunk; no new runtime dependencies.
- Full UX2 browser suite: **114 passed** before final two race/uncertain-outcome tests. Current new Studio suite: **23 passed**, including delayed admission versus user edits and committed-but-response-lost owner adjustment. Final desktop-width case and full exact-head CI remain required.
- Full Windows Python run with UTF-8 and an accessible explicit temporary directory: **3719 passed, 81 skipped, 7 failed, 4 errors**. All seven failures are Windows-only missing Bash/symlink privileges; four oversized parameterized test IDs exceed Windows's environment-variable limit. No tests removed or weakened; Linux CI is authoritative for the full release gate. Initial Windows runs also exposed default cp1251 and inaccessible system temp; these were resolved in the test environment, not in product code.
- Full Ruff and provider contract inventory pass. No paid-provider or real-payment calls were made.
- Independent read-only review found and verified fixes for draft loss, catalogue media loss, permission revocation on history failure, moderation dead ends, async admission edits, protected-series placeholders and ambiguous credit mutation retries. Final reviewer reports no blocking findings.
- Owner credit changes use the existing non-idempotent endpoint. A synchronous latch and owner-scoped tab-storage marker prevent blind replay after a lost response, including reload. Fresh target ledger review and explicit administrator acknowledgement are required before new mutations; this is manual reconciliation, not a promise of server exactly-once semantics.
- Source audio exposes cover/extend/vocals/instrumental using installed APIs and validates operation-specific title/style/position requirements before upload/launch. Voice verification submits multipart audio with the server phrase.
- Results preserve all original URLs, explicit public consent, visible-text reuse and image-to-video preparation without automatic paid execution. Active series restore respects prompt privacy and asks before replacing an image draft.
- Surface parity: **mini_app** new opt-in UI and guarded APIs; **telegram_bot** extra admin-only Web App menu entry, regular menu unchanged; **site** existing standalone Studio unchanged (this request targets Mini App), shared prices/caps/auth/payment rules reused. No public rollout, migration, new tariff or provider-routing change.
- First feature commit `784208d73dc54560a084772d1f9ff806d9d6576d`, PR **#297**: Linux backend-quality, bot-navigation, provider-contracts, pinterest-backend and all300user-journeys checks passed. Webapp gate still running at this checkpoint. Local300journeys were288pass/12fail because the live Telegram SDK replaced mocked start parameters behind the Windows proxy. Explicitly stubbing that external SDK in the test fixture restored all25shared-link scenarios without weakening any assertions. Product code unchanged by this harness repair; exact final commit must pass CI again.
