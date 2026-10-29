# Studio UI3 public release — 2026-10-30

## Goal and baseline

- User explicitly requests opening the updated interface to ordinary users after the feed/video repair.
- Main and production baseline: `57388f4d4755d2f4bbe8561597b8dd8311b76acc`, PR #326; tracked production checkout is clean.
- Isolated branch: `feat/ux2-public-studio-20261030`, in the existing clean QA worktree. Production is not edited manually.
- Skills/guidance: requested `.agents` and frontend-design, repository TDD, verification and independent review. Required tool repositories were refreshed with fast-forward-only pulls; project-local skills were inspected in the production source checkout because they are not tracked in the isolated worktree.
- The bundled Superpowers contributor guide concerns that upstream skill repository. APIX delivery follows the root AGENTS protected-main policy; platform attribution rules prevail.

## Current behavior

- The redesigned feed is already a shared component. The Studio/UI3 shell is still restricted by an admin-only capability and `/studio/preview` guard.
- Even a permitted account needs `?ux=3`; a fresh normal `/app/` session defaults to UI1.
- The UI capability is incorrectly reused for the owner screen and the “Управление APIX” entry. Those must use the separate server-supplied administrative role before widening UI admission.
- Existing auth checks validate Telegram/web identity, require a registered account and reject banned users. The separate permissions endpoint derives administrative status from server `ADMIN_IDS`.

## Product/configuration decision

- This is permanent completion of the temporary admin preview: UI3 becomes the standard interface for authenticated, registered, non-banned users.
- The existing capability and fixed UI version describe the installed application's interface contract. No configurable audience, rollout percentage or operational toggle is introduced; there is no new mutable business policy requiring a parallel DB control plane.
- Preserve explicit legacy-interface selection and the existing server capability/admission fallback. Do not modify `ADMIN_IDS`, provider/model audiences, prices, payment/generation authorization or database records.
- `site`: authenticated use of the shared `/app/` UI receives Studio by default. The standalone landing/web implementation remains a separate documented surface.
- `mini_app`: the ordinary bot `/app` link opens Studio without a query or stored opt-in.
- `telegram_bot`: the existing ordinary WebApp link already points to `/app`; actual administrative commands keep their guards.

## Acceptance

1. A normal authenticated, non-banned user receives the UI capability and Studio admission; no identity remains 401 and a banned account remains 403.
2. A fresh browser context opening `/app/` without `?ux` or storage selects UI3. Explicit classic UI selection remains available.
3. An ordinary user has `is_admin: false`, sees no owner/admin entry or administrator-only copy, and cannot access administrative APIs. Unknown/failed permissions do not grant administration.
4. Real administrators retain their owner entry and administrative functions. UI capability is never a substitute for administrative identity.
5. Feed, video previews, counters and existing generation/payment contracts remain covered by maintained gates; verification performs no paid production operations.

## Plan and evidence

1. [x] Fresh source/runtime audit, baseline and gating discovery; independent review of the permanent-release architecture.
2. [x] Add/update focused backend and browser regressions; witness expected failures before changing implementation.
3. [x] Apply the smallest admission/default/role/copy changes; pass focused checks and review affected existing scenarios.
4. [ ] Independent source review, exact-head CI and protected native squash auto-merge.
5. [ ] Exact merge-SHA autodeploy, public health/source verification and deployed-artifact regular-user entry checks.

Release identifiers and final runtime evidence will be recorded in the PR after they exist. Do not treat an API stub as proof of production authorization; test actual server handlers separately and verify the deployed source/artifact identity.

### Backend evidence

- New route/profile regressions were run against the unchanged baseline implementation: eight expected failures and fourteen passes. The failures exposed admin-only capability/admission and the missing independent role field.
- After the minimal implementation, all 22 focused cases pass. They cover actual authenticated route handlers for Telegram and signed web tokens, ordinary/admin profiles, uncached admission, unsigned and banned accounts, and ordinary-user rejection by administrative GET and POST routes.
- The profile now returns `is_admin` from the existing server membership check. This avoids a second permissions request and preserves a fail-closed role for clients receiving an older/missing role field.
- Ruff passes for all 617 tracked Python files. A first whole-mounted-directory invocation also picked up an ignored scratch verification script from the previous release; that file is outside the repository deliverable and the CI source inventory.
- Independent review confirms the only removed administrative guard is the former Studio preview admission guard. Actual administrative routes retain their checks.

### Client evidence

- Tests separate interface capability from administrative membership and exercise a fresh normal URL, explicit legacy choices, role loss, neutral user-facing copy, and admission failure.
- Authentication rejection (401/403) during Studio admission must close the application session. Non-authentication admission failure retains the classic-interface fallback.
- Existing administrative browser fixtures now state their role explicitly without weakening their assertions. Foundation fixtures model a real Studio admission response and verify UI3 by default instead of obtaining a false pass through an empty-array fallback.
- Before implementation: one expected unit failure and three passes; 13 expected browser failures and two passing explicit legacy-interface cases. The browser failures covered ordinary default entry, role/copy separation, role loss, admission fallback and 401/403 session rejection.
- After implementation: all 152 unit tests and 15 focused browser cases pass. The browser runner rebuilt the application, including TypeScript checks. Two absence assertions additionally wait for the profile to paint, preventing an early empty-DOM false pass.
- Independent review approved all six changed production files against the exact baseline: strict administrative roles, role-loss navigation, session rejection and stale-actor handling, public admission and the local reference checker. No unresolved P0/P1/P2 finding was identified.

### Additional rollout dependency found during review

- `/api/web/upload-media/check` still rejects ordinary users because it was introduced as an admin preview. UI3 enables the existing reference-availability submission check, so opening only the shell would prevent ordinary accounts from generating with uploaded photos.
- Include this authenticated, read-only local-public-upload inspector in the release. Preserve its URL/path allowlist, no-network behavior, symlink protection, response privacy and logging. It does not grant ownership, renew files, or change generation authorization.
- The historical E10 program remains separate from this explicitly authorized launch. Record this delivery and its evidence here; do not claim completion of research or roadmap items that have not been performed.
- The checker regression first produced two expected failures and 34 passes. After removing only the additional admin gate and unused import, all 58 combined backend cases and Ruff for all 617 tracked Python files pass.
