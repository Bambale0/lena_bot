# UX2 video repeat counters — 2026-10-29

## Baseline and scope

- Repository: `Bambale0/lena_bot`; baseline and live checkout:
  `1161d1ecc397b6725de5e36d3b6d5cab8bd27237`.
- Isolated branch: `fix/ux2-video-repeat-counters-20261029`.
- User report: UX2/APIX does not show video repeat counts. Screenshot identifies
  the profile's Works tab in the lilac Studio layout.
- Intended outcome: accurate completed-repeat counts on published work cards and
  details, including video, plus restored existing trend usage counts in the
  current category shelf/folder UI.
- No pricing, rewards, provider routing, visibility policy or generation submission
  changes. No paid generation, production data repair, new migration or settings.
- Existing APIX count visibility is retained; unrelated admin-only rules from
  other applications do not apply.

## Evidence and hypotheses

1. Confirmed repository gap: feed aggregation groups only by
   `parent_generation_id`, while video feed repeats store
   `source_feed_gen_id` and a null parent.
2. Confirmed UI/contract gaps: history/detail `GenerationOut` lacks `remixes`;
   WorksScreen and task detail cannot display it. ShelfTrendTile omits
   `uses_count` that API already returns. Feed media viewer omits available
   `remixes`.
3. Alternative genuine-zero/stale-response scenario: preserve real zero, distinguish
   missing/null data, and include counts in both history and detail refresh so
   refresh does not remove them.

Read-only production SQL on 2026-10-29 confirmed completed video and image
rows with a feed source but no parent. Bounded published-video samples showed
that the old counter omits existing completed repeats. Rows with both source
fields present and different also exist, so precedence must be verified against
the writers and covered by regression tests. Production row identifiers and
business volumes are intentionally omitted from this public repository ledger.

## Design and acceptance criteria

- `remixes` keeps its existing completed-generation semantics; pending, failed,
  and processing children are excluded.
- Source precedence must represent the explicit feed publication and retain the
  legacy parent fallback, with each child counted once.
- Use one shared repository aggregation for feed and bounded history/detail
  enrichment; no query per item and no unbounded feed preload.
- History/detail expose a nullable count only where applicable. A published card
  with no completed repeats gets real zero; absent data is not presented as zero.
- Profile, work detail, and feed viewer retain the count for image/video and on
  media failure and refresh.
- Trend `uses_count` retains accepted-launch semantics and is not replaced with
  successful feed-repeat counts; shelves/folders show nonzero and zero values.
- Mobile layout is checked at narrow widths.
- Existing ownership and authentication checks remain in force.

## Surface parity

- `site`: shared Studio/React UI and common feed repository affected.
- `mini_app`: primary reported path, same React cards and authenticated APIs.
- `telegram_bot`: trend caption already displays usage count including zero.
  Feed repository correction applies to shared data; bot UI is outside the
  user's explicit application display change.

## Execution plan and progress

1. [x] Read repository instructions, relevant architecture/contracts and skill
   guidance; update local skill sources using fast-forward pulls.
2. [x] Confirm live baseline and public health; inspect real counts using an
   explicitly read-only transaction with a 5-second statement timeout.
3. [x] Backend regression RED: video source-only, image legacy fallback, equal/
   differing sources, terminal states, history pagination/detail/ownership.
4. [x] Implement minimal shared count/enrichment fix and verify GREEN.
5. [x] Browser RED/GREEN for profile/detail/viewer/trend shelves and real zero.
6. [x] Independent review of source semantics, bounded querying, and full diff.
7. [ ] Focused checks, lint/typecheck/build, required exact-head CI.
8. [ ] Protected PR native auto-merge; exact merge-SHA Production Autodeploy.
9. [ ] Read-only live repository counts, public health and deployed assets.

## Skills and verification approach

- Bambale0/skills `diagnosing-bugs`; Bambale0/claw debugger guide.
- Repository `systematic-debugging`, `test-driven-development`,
  `verification-before-completion`, and isolated worktree guidance.
- wondelai/skills characterization/legacy testing guidance.
- anthropics/skills `webapp-testing`; existing repository Playwright harness is
  the primary browser seam.

Implementation is verified locally in isolated test containers; release remains pending.

## Live reproduction before the fix

An independent read-only check compares completed children in PostgreSQL with
`GET /api/v1/public/feed/{id}` for five existing published video samples.
The command exited 1: all five HTTP responses returned zero while each database
count was nonzero. The same bounded check will be repeated after deployment.
No provider call, authentication mutation, or database write is involved.

## Implementation and focused verification

- Shared repository count uses canonical feed source, falling back to legacy
  parent, with done-only counting and no duplicate attribution.
- Mini App and web history/detail serializers receive nullable real counts from
  one bounded per-page query. Ownership checks precede counting.
- Published work tiles, task detail, feed viewer and trend shelves/folders show
  the existing applicable count through a shared display component.
- Baseline backend RED: 11 failures and 4 passing boundary checks. After two
  additional private-page checks, the focused repository/history/web suite is
  GREEN: 140 passed, one existing Starlette warning.
- Baseline browser RED: all four new count scenarios failed on missing labels.
  GREEN: six scenarios passed (four new plus two existing shelf/admin scenarios),
  including 320/390 px, video failure, true zero, unknown values and refresh.
- Full Ruff and git diff whitespace checks passed. Playwright production server
  build includes successful TypeScript validation and Vite build; the existing
  bundle size warning remains.
- Unit harness initially rejected the new real component import. Its strict
  dependency map now loads the actual RepeatCount module; existing assertions
  and the source-selection behavior are unchanged. Unit rerun passed: 149 tests.
- Independent whole-diff review found no blocking P0/P1/P2 issue. Optional
  screen-reader description of the visual work-tile count is a follow-up.
- Runtime checks use disposable Docker containers with synthetic credentials
  and SQLite; production containers/data were only read.

Visual QA after the passing rerun inspected the actual mobile Works grid:
video count 7, video count 0 and photo count 3 are readable at 390 px, while
private/unknown counts are absent. The test also asserts 320 px without horizontal
overflow. All three work/profile/viewer scenarios passed again after capturing
the relevant scrolled viewport.
