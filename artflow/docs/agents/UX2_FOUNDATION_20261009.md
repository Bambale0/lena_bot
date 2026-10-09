# APIX Mini App UX2 foundation execution

Baseline: `2f86ee13e3600f76bf46b2844c65f744f12567cf` (PR207).
Branch: `feat/apix-miniapp-ux2-foundation`. Scope authorized: Mini App only.
Production checkout is clean and is NOT used for edits/builds.

## Slice and acceptance
- Admin opt-in preview using a server-computed profile capability and session preference. Normal users keep the current UI; query parameters never grant capability.
- Five primary destinations: Feed, Trends, Create, Works, Profile. All fit at 320 CSS px. Existing photo/video/motion/services/settings remain reachable.
- Works uses existing authenticated history and task detail actions, distinguishes review state, does not invent percentages or refunds.
- Ordinary drafts survive reload within the current browser tab, scoped by authenticated user. No initData, billing data, or hidden-template drafts are stored. Storage failures must not crash the app.
- Preserve PR207 repeat/checkout/provider behavior; no new paid requests, migrations, provider, price or business-config changes.

## Current architecture and reuse
`main.tsx -> App.tsx`, existing AppShell, GenerationScreen, profile/services/settings and task/balance sheets. Profile currently lacks a preview capability. Existing ADMIN_IDS is authoritative; no new IDs or global rollout switch. Existing history paginates, refreshes with a bounded merge. Existing generation drafts are in React state only.

## Explicit limitations
This slice does not implement the complete UX2 generator, lifetime durable media storage, model-switch compatibility parking, feed-state preservation, broader cohorts, or production paid E2E. SessionStorage is NOT persistent cross-device storage or a promise that provider URLs stay valid.

## Guidance
Read root and artflow AGENTS; project frontend-developer, verification-before-completion, clinerules test-driven-development; Bambale0/claw frontend-qa; wondelai/refactoring-ui; anthropics/frontend-design. Bambale0/skills inspected via GitHub.

## Verification plan
1. RED browser regression for five destinations and backend profile capability.
2. Implement the smallest reusable shell/create/works/draft foundation.
3. Unit tests: draft schema, owner isolation, malformed/unavailable storage, no hidden prompts.
4. Playwright: legacy/unauthorized/admin preview, 320/390/430 widths, dark/light, all destinations, reload, editor Back, payment return, task state and no paid request on navigation. Chromium and available WebKit.
5. Existing unit, browser and backend maintained checks; review diff and secrets; PR to main with exact CI evidence.

## Progress
- [x] Fresh baseline, instructions, runtime path and isolated clone verified.
- [x] RED: original browser navigation had 8 destinations instead of 5; backend profile omitted the preview capability (3 failing assertions).
- [x] Foundation implemented in isolated branch: opt-in shell/create/works/session drafts.
- [ ] Verification and review.
- [ ] PR, CI and release status.

## Surfaces
mini_app: changed behind preview capability. site: visual UI unchanged; additive profile field only. telegram_bot: unchanged; shared business/provider contracts unchanged.

## Interim evidence
- TypeScript and Vite build passed (existing 500 kB chunk warning remains visible).
- 19 new Chromium tests passed: 320/360/390/430/768px, dark/light routes, native Back, owner isolation, prompt/format/media reload, balance-sheet return, history error/recovery and horizontal overflow.
- 37 frontend unit tests passed (25 existing + 12 UX2 tests).
- New backend profile capability tests: 3 passed.
- Existing Chromium smoke suite: 144 passed across iPhone SE, iPhone 13, Pixel 5 and Desktop emulation. Backend focused regression: 43 passed. Both used test credentials and no production data.
- Screenshot files were captured by Playwright. Remote media reader cannot access the isolated /tmp workspace under its current file_ops policy; no policy was broadened. CI artifacts are configured for visual review of a fresh CI run.

## Review findings addressed
- Rehydrating a no-longer-available model fails closed rather than silently showing the first model.
- A changed model capability set now blocks an ordinary restored draft until explicit parameter refresh. The browser regression first failed with an enabled launch button, then passed; updating parameters preserves prompt and media.
- Enabling preview does not replace an active template draft with an ordinary saved draft.
- A successful core refresh clears a transient history-unavailable indicator.
- Changed preview media URL resets the tile's failed-thumbnail state.

## Remaining release checks
Draft PR is appropriate until exact-commit CI and screenshot review finish. No production change is claimed. Real Telegram iOS/Android WebView, paid provider requests, and cross-device storage are outside this preview verification.
