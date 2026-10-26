# Trend category shelves — approved design (2026-10-26)

## Understanding summary

- Replace category icon/filter chips with full category folders presented as shelves.
- Each shelf shows 3–5 live media tiles and a clear **Смотреть все** action.
- A user can open a category and browse its complete paginated catalog.
- Administrators can create, rename, reorder, hide, publish, and populate categories.
- Category configuration is database-backed and shared by web, Telegram Mini App, and the text Telegram bot.
- Existing trends and links must survive migration without data loss.
- Mobile Telegram WebView is the primary layout; desktop remains responsive and polished.

## Assumptions and non-goals

- Live previews autoplay muted only while visible and respect reduced-motion preferences.
- Empty or hidden categories are not shown publicly, but remain visible to administrators.
- Hiding is reversible. Destructive category deletion is outside this release.
- Existing pricing, generation providers, model admission, and payment behavior do not change.
- This release does not introduce multi-category membership for one trend.
- Server-side authorization is authoritative; hiding admin controls in the UI is not security.

## Approaches considered

1. **Database category entity with an explicit trend relation — selected.** Provides integrity, ordering, safe visibility control, and one source of truth for all surfaces.
2. Keep categories encoded only in tags. Rejected because orphaned or duplicate categories cannot be prevented reliably.
3. Many-to-many curated collections. Deferred because it adds unnecessary API and admin complexity before there is a confirmed need for a trend to belong to several folders.

## Architecture and data

- Add a `trend_categories` entity with an immutable ASCII key, mutable title, sort order, visibility state, and timestamps. Existing seeded keys are retained; new keys are server-generated opaque `cat_...` values and are never derived from a Cyrillic title or editable by clients.
- Add an explicit nullable category relation for trend records. Existing category tags remain readable during one compatibility release and every writer mirrors the stable key back to the legacy tag. The relation is authoritative when present; a recognized legacy tag is the fallback only for unbackfilled rows.
- Seed the current category set and backfill existing trend relations deterministically in an idempotent expand-only migration. Unknown legacy values keep their original tag unchanged, receive the seeded fallback relation, and are included in an administrator-visible migration report/audit until manually resolved. Dual-write must not replace an unresolved original tag.
- Roll out in two backward-safe phases. Phase A deploys the expanded schema, dynamic readers, fallback handling, indexes, and read APIs while custom category creation stays disabled. Phase B enables writes and the new UI only after Phase A production verification. A Phase B rollback targets the Phase A reader, never the pre-migration hardcoded reader; schema contraction is deferred beyond this release.
- A shelf endpoint returns a paginated category catalog with at most 24 visible non-empty categories per page and at most five preview items each from one bounded query/batch, avoiding N+1 requests. The service enforces at most 100 total categories and titles of 80 Unicode characters.
- Preview and folder ordering is stable by real `UserPrompt.created_at DESC, UserPrompt.id DESC`. Add a composite index covering category relation, public state, `created_at`, and ID for these access paths.
- A category detail endpoint uses a composite `(created_at, id)` cursor over the same stable ordering and enforces a maximum page size of 48.
- Admin APIs return paginated categories and grouped item counts in bounded queries, and support create, rename, reorder, hide/publish, and trend reassignment.
- Stable keys keep deep links valid when a title changes. Seeded keys preserve existing URLs; generated keys fit Telegram callback limits. API payloads retain current trend fields during the transition.
- Administrative writes use server-side authorization and validation. Reorder accepts the complete ordered category set plus the last catalog revision; one transaction locks catalog state, rejects stale revisions with `409`, writes a unique contiguous order, increments the revision, and records a dedicated immutable category audit event atomically.
- Hiding a category makes its trends unavailable through public trend list, detail, checkout, and run routes, including direct links. The underlying trend records remain intact and become available again when the category is republished.
- Hiding blocks list/detail/checkout/run requests admitted after the hide commit. Run rechecks category visibility in the same transaction immediately before the financial claim. A paid operation already claimed before the hide commit is allowed to finish and is never silently cancelled or charged twice.

## User experience

### Trends landing

- Render vertical category shelves on the approved black/red visual foundation.
- Each shelf has a prominent title, a **Смотреть все** action, and 3–5 horizontally scrollable live tiles.
- Tiles show preview, title, available duration context, and a persistent **Повторить** action. They do not show a speculative price; the existing repeat flow calculates the exact authenticated quote only after the user chooses duration and inputs.
- A skeleton is shown while loading. A failed preview falls back to a poster/placeholder and does not collapse the shelf. The title and **Повторить** remain usable; retrying media is a secondary action and never blocks generation.
- Videos are muted, inline, reduced-motion safe, and mounted/played only while intersecting the actual browser viewport.
- Shelf titles clamp to two lines on narrow screens; the full folder heading can wrap naturally within a bounded three-line mobile header. Tests include long Cyrillic text and emoji.
- If the entire catalog is empty, show a friendly explanation with **Обновить** and a route-appropriate **Назад**, rather than an empty canvas.

### Category folder

- Provide a clear back action, category title, and a responsive full catalog grid.
- Preserve scroll position and relevant repeat preferences when returning.
- Support refresh, direct links, browser back/forward, loading, empty, error, and retry states.
- Public users never enter an empty/hidden folder through catalog navigation; administrators receive an actionable empty state.
- Folder and catalog pagination use an explicit **Показать ещё** action with separate loading, retry, disabled, and end-of-list states. Already loaded shelves/tiles remain visible if a later page fails.

### Admin manager

- Show category title, status, order, and trend count.
- Allow create, rename, reorder, hide/publish, and safe reassignment from the trend editor.
- Warn before hiding a populated category. Prevent duplicate submissions and preserve form values after errors.
- A category containing trends cannot be destructively deleted in this release.
- Concurrent/stale edits retain the administrator's form state and offer an explicit refresh after a `409`; they never silently overwrite a newer catalog.

## Reliability, performance, and security

- Avoid N+1 category/trend requests and bound shelf payloads and category pagination.
- Lazy-load media, stop/unmount off-screen video, and keep the existing reduced-motion behavior.
- Reject duplicate keys, invalid ordering, stale/conflicting admin writes, and unauthorized mutations server-side.
- Do not expose raw backend errors. Keep retryable failures local to the affected shelf or form.
- Record administrative category changes in a dedicated immutable audit table atomically with each mutation, without private content or secrets.
- The text Telegram bot first presents visible category folders, then opens its existing carousel within the selected folder. Its admin category picker reads the same database catalog; no hardcoded category buttons remain.
- Telegram paginates category keyboards in groups of eight, so the bounded catalog never exceeds callback/message limits.
- Telegram category pages provide **Назад**, **Вперёд**, and **Назад к категориям** controls. Returning from a carousel restores the selected category page instead of restarting the flow.

## Verification strategy

- Migration seed/backfill, downgrade/rollback safety, unknown legacy category handling, and API compatibility.
- Public/admin authorization, validation, conflict behavior, ordering, visibility, counts, and reassignment.
- Landing shelves, folder navigation, deep links, history/back behavior, and repeat-duration handoff.
- Zero/one/many categories and trends, long Cyrillic titles, broken media, slow/error responses, and retries.
- Mobile Telegram WebView, representative phones/tablets/desktop, keyboard/focus/touch, contrast, and reduced motion.
- Network/console inspection and proof that off-screen previews stop and unnecessary requests are absent.
- Parity checks for site, Mini App, and Telegram bot category selection/labels.
- Exact-head required CI, independent code review, protected PR auto-merge, production autodeploy, and exact-SHA live smoke verification.

## Decision log

1. Categories are full shelves/folders rather than icons or filter chips — explicitly requested by the user.
2. The database is the category source of truth — required for administrator control and surface parity.
3. One category per trend for this release — simplest model that satisfies the approved workflow.
4. Hide/publish replaces destructive deletion — prevents accidental content loss and permits recovery.
5. Existing keys and payload fields remain compatible — protects old trends and deep links.
6. Live tiles reuse viewport-aware preview behavior — preserves performance and avoids the previously fixed preview regression.
7. Hidden categories disable public list/detail/checkout/run access — visibility must not be bypassable by a saved link.
8. Exact price remains in the repeat confirmation flow — shelf tiles cannot quote accurately before duration and inputs are chosen.
9. Shelf previews are returned in one bounded catalog contract with stable ordering — prevents N+1 requests and uneven global-limit results.
10. Category writes use an atomic catalog revision and dedicated audit event — concurrent administrators cannot silently overwrite one another.
11. The compatibility release dual-writes stable legacy tags and retains the expanded schema on code rollback — prevents surface drift and destructive rollback loss.
12. The text bot exposes folders before its category-scoped carousel — parity applies to browsing as well as admin creation.
13. Delivery uses a Phase A compatible reader followed by Phase B write/UI enablement — rollback never targets code that collapses custom keys to `featured`.
14. Catalog size, title length, shelf pages, folder pages, and Telegram keyboards are bounded — administrator growth cannot create an unbounded response or message.
15. Ordering uses `created_at` plus ID and a matching composite index — the contract relies only on real immutable fields and remains cursor-stable.
16. Unknown legacy tags remain unchanged until manual resolution — migration and retries cannot destroy the original classification evidence.
17. Hide/run uses a pre-claim visibility recheck while already claimed paid work completes — visibility changes do not cause free work, duplicate charges, or cancellation ambiguity.
18. Empty and paginated catalogs always expose a clear next action — novices do not encounter dead ends or silently truncated content.
19. Every tile retains an explicit **Повторить** action even when its preview fails — media playback is decorative, generation remains primary.
20. Telegram folder navigation includes previous/next/back controls and state restoration — category browsing cannot trap the user.

## Structured review record

### Skeptic / Challenger

Disposition: **REVISE**, accepted. The review identified hidden-category deep-link bypass, an incomplete migration cutover, an underspecified shelf query, speculative shelf pricing, missing concrete audit storage, reorder races, undefined key generation, and incomplete text-bot browsing parity. Decisions 7–12 and the revised architecture/UX sections resolve these objections without adding unrelated product scope.

### Constraint Guardian

Disposition: **REVISE**, accepted. The review identified unsafe rollback after creation of custom keys, unbounded category/media responses, an undefined/non-indexed ordering field, destructive handling of unknown legacy tags, an ambiguous hide-versus-paid-run race, and possible count-query N+1 behavior. Decisions 13–17 and the revised architecture/reliability sections make the rollout staged, bounded, indexed, idempotent, and financially explicit.

### User Advocate

Disposition: **REVISE**, accepted. The review identified a missing whole-catalog empty state, invisible pagination behavior, an ambiguous tile action, a preview failure that could obscure the primary flow, incomplete Telegram back/page navigation, and long-title risks on narrow WebViews. Decisions 18–20 and the revised UX sections add explicit actions, progressive loading/retry states, resilient cards, stateful bot navigation, and bounded mobile typography.

### Integrator / Arbiter

Disposition: **APPROVED**. All reviewer objections are resolved in the architecture, UX, reliability, rollout, and decision-log sections. The approved revisions preserve the locked product goal and introduce no unrelated feature scope. There are no unresolved design blockers before implementation planning.

## Approval record

The user approved the understanding, selected approach, architecture/data design, user UX, and admin/reliability/testing design in the conversation on 2026-10-26.
