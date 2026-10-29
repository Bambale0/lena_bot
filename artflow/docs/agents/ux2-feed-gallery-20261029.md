# UX2 feed gallery redesign — 2026-10-29

## Goal and baseline
- User asks to redesign the feed UI/UX, with the supplied APIX Studio screenshot and explicit use of Bambale0/.agents and anthropics/frontend-design.
- Baseline main and production: `77d524a95b0a25de933dab8a8713542d7cc02add` (repeat counters already released).
- Branch: `feat/ux2-feed-redesign-20261029`.
- Reuse the canonical React `FeedScreen`, its API callbacks, paging, shared repeat runner, and existing theme tokens. Production work is isolated in a separate git worktree.
- Existing untracked operational files in the production checkout are unrelated and untouched.

## Evidence before implementation
The supplied screenshot and source agree: 8–10px card metadata, large actions over media, artificial shape/featured decisions by index, a mixed sort/type filter rail, and a desktop media-height cap compete with the actual work. The feed already has a stable-grid/WebKit guard in performance.css; this must be preserved and explicitly scoped when overriding breakpoints. Bottom-navigation overlap requires an actual scroll/hit-test, not a conclusion from a still image.

Original results and previews currently share a gallery array. The redesign separates display previews from selected source URLs, preserving bound output URLs and legacy fallback. The feed has no share handler; share counts must remain passive data. The standalone website and text bot use separate surfaces.

## Design decision and scope
Chosen direction: an image-led APIX gallery using the existing identity and quiet, readable captions. The content itself supplies visual variety; no new hero, fabricated editorial recommendation, model-name dictionary, provider branding, or business feature is added.

Alternatives considered:
1. Dense variable masonry: rejected because it repeats the crop/order/readability problems.
2. Stable gallery with separate metadata/actions: chosen for predictable order, visible media and touch targets.
3. Fullscreen reels-first navigation: rejected because mixed photo/video browsing and existing workflows are the requested surface.

Color roles reuse the current theme (Lilac examples): background #000000, surface #15101D, secondary surface #21172F, primary text #F7F3FF, secondary text #C1B4D3, action #B994FF. Typography inherits the existing app family; new remote fonts/dependencies are unnecessary. Left aligned captions, 13px+ author/model/counter text, 44px interaction targets, restrained transitions with reduced-motion support.

Layout: scoped stable grid, 1 column below 380px, 2 at 380–699px, 3 at 700–1099px, 4 from 1100px, bounded desktop width. Consistent 4:5 preview geometry without an arbitrary height cap. Author, measured counters and repeat action sit below the media. Sort and content filters form distinct semantic groups.

## Contracts and configuration
- Keep existing recent/top_day/top server sources, image/video filters, dedicated authenticated mine endpoint, DOM batches and API pagination.
- Preserve `onRemix(item, selectedOutputUrl)`, ownership, hidden prompts, quotation and explicit launch. Viewing/filtering must not submit a paid generation.
- Keep repeat counts as completed publication repeats and trend use counts as launches. Known zero is visible; missing/null is not fabricated as zero.
- Canonical output order wins over previews or legacy alternatives. Display posters do not become extra outputs.
- Viewer portal stays above navigation and below repeat sheets; keyboard/focus handling must respect the top modal.
- No schema, API, auth, price, provider, balance, dependency or runtime business-configuration change.
- No new analytics subsystem: verification inspects existing requests, UI effects, console errors and loading/error states without logging personal data.

## Surface parity
- mini_app: canonical React feed, UX2/Lilac desktop and mobile layouts, plus compatibility of the shared ordinary React feed.
- site: separate landing/Studio UI is outside this Mini App visual request; API and repeat business semantics stay unchanged.
- telegram_bot: visual gallery layout is inapplicable; shared business contracts and existing captions stay unchanged.
- Legacy `?legacy=1` is a rollback/debug entrypoint and is not redesigned.

## Acceptance and test seams
Public seams are the rendered gallery, toolbar, viewer, repeat-sheet handoff, and intercepted API requests. Verify:
- Filled layouts at 320/390/1440px; additional tablet/wide snapshots if useful. No page overflow, no covered final action, readable metadata, separate 44px targets.
- Mixed media, long authors/counts, known zero/missing count, broken previews, loading/empty/recovery states.
- Like stays independent; viewer is named and keyboard usable; focus restores; a repeat sheet above it remains operable.
- A two-output album with separate previews has two outputs, and repeating output two quotes that exact source. No hidden prompt leak.
- Existing paging/mine, repeat counter, source-selection and gallery portal regressions remain meaningful.
- Existing full CI remains intact; final release requires native squash auto-merge, exact merge-SHA CI/autodeploy, health and served-asset verification.

## Execution
1. [x] Fresh instruction/architecture/UI/test audit and baseline identification.
2. [x] Read frontend-design and .agents/frontend-ux-audit; compare design to the brief and independent review.
3. [x] Baseline build/typecheck and 149 unit tests passed. New responsive browser checks failed 3/3 as expected: 320px had two columns, 390px had three, and the 1440px media ratio was 1.335 rather than 0.8.
4. [x] Implement scoped gallery and viewer improvements.
5. [x] Focused unit/browser/WebKit checks and screenshot critique.
6. [x] Independent code review and secret/whitespace check.
7. [ ] PR #325, exact-head CI, native squash auto-merge after final verification.
8. [ ] Main CI/autodeploy and production asset/health verification.

## Skills materially applied
- User sources: `Bambale0/.agents` router and `frontend-ux-audit`; `anthropics/skills/frontend-design`.
- Project: scoped planning/brainstorming guidance, worktree isolation, regression and verification-before-completion.
- `Bambale0/claw`: frontend-react responsibilities; `wondelai/skills`: refactoring-ui hierarchy/spacing/typography; `Bambale0/skills`: behavioral TDD seams.
- Upstream Superpowers contribution rules bundled in .clinerules/Agents.md describe contributions to that plugin, not APIX delivery. APIX root protected-main delivery rules govern this repository.

## Verification evidence
- Baseline regression: the three responsive cases failed on the old layout at their intended geometry assertions, with successful application bootstrap.
- First implementation pass: production build/typecheck, all 149 unit tests, and nine Chromium scenarios passed (six new gallery cases plus three existing repeat-counter cases).
- The new scenarios cover 320/390/1440px, 4:5 geometry, readable counters including zero/unknown, last-card hit-testing, independent likes, exact second-output handoff for both originals and bound public previews, and focus restoration through the repeat sheet.
- Screenshot critique caught a Play decoration over the failed-preview message. A scoped sibling selector now hides it, with an assertion in the existing failure-state scenario.
- Existing e2e fixtures previously supplied four PNG signature bytes and left bound-preview media requests unhandled. They now serve decodable image fixtures (PNG CRC checked). Scroll-to-control precedes the original real hit-test and touch/mouse click; exact source, quote and submit assertions are retained. Native Back already passed on all four existing device configurations.
- Independent review found no remaining product P0/P1/P2 issues. Source binding, hidden-prompt handling, truthful counters, modal order, CSS scope and test adaptations were reviewed.
- Existing gallery e2e: 16/16 passed across the four configured Chromium device profiles. WebKit: 9/9 passed using Playwright's installed WebKit 27.2 engine, not a Chromium mobile emulation.
- Public-media visual QA: 5/5 passed at 320/390/768/1440/1920px, with screenshots of the filled gallery and viewer. Images actually decoded, viewport geometry and final-action hit-tests passed, and no paid write or runtime page error occurred. The temporary fixture and images stay outside git.
- Final mobile critique reduced toolbar whitespace by 44px without reducing touch targets. After this refinement, 9/9 Chromium scenarios, 3/3 WebKit responsive cases and the real-media 390px case passed again. A preceding browser-start crash was traced to the isolated QA container's process limit; restarting it and using one worker resolved the environment failure without changing product code or assertions.
- Final review approved the implementation with no open product P0/P1/P2. Whitespace and credential-pattern scan passed. Main remained at the baseline SHA before commit.
- Initial full backend CI found six legacy structural tests requiring the replaced mosaic, controls over media and exact old utility classes. Those six functions in `test_apix_production_trends_surface.py` now assert the new scoped grid, semantic controls, caption actions, lazy/eager preview boundary, portal and focus ownership. All 16 tests are retained; AST comparison confirmed the other ten tests and helper are unchanged. Independent review approved this eighth changed file. Direct execution of all 16 pure structural checks against the full worktree passed; fresh full CI is required on the updated head.
- The next full backend CI passed. A narrow journey audit also caught a real display regression before merge: stale previews could override canonical results on the card. Two new browser assertions reproduced it (wrong image source and wrong video request). `cardPreview` now uses the same first canonical output as viewer/card repeat; preview-only public payloads still use their bound aliases. After the fix, build, 149 unit tests, nine Chromium cases, nine WebKit cases and all 25 existing shared-link journey cases passed. Their canonical image assertion was not weakened.
- The 300-journey image fixture also had invalid PNG CRC/checksum data; its literal was replaced with a valid image. Remaining journey failures concerned only the intentionally changed empty-state copy. Its assertion now checks the visible heading and guidance plus zero cards; all five affected scenarios passed. The injected 503, application visibility, other error modes and canonical assertions remain unchanged. Independent review approved the final nine-file scope without product blockers. PR was temporarily returned to draft while the canonical-source correction was verified, preventing release of the known regression.
- Full CI on `ac147c1b1fdc3639642602c25051539614cff894` passed: backend quality, bot navigation, provider contracts, 149 unit tests, 392 Mini App smoke cases, 324 UX2 cases and all 300 user journeys. This head was not released: two subsequent automated review findings were reproduced before merge, and PR #325 was returned to draft.
- Review regressions reproduced RED 2/2 against that head: an explicitly typed video with an extensionless canonical URL was requested as an image, and trend usage was labelled as completed repeats. The video branch now preserves the authoritative media type and excludes the canonical video URL from poster candidates. Trend usage has its own `Использований: N` label, retaining known zero and hiding unknown values. The shared completed-repeat component is unchanged. New browser checks inspect the actual video request resource type and trend values 7/0/null/missing; existing second-source, bound-URL, quote and keyboard scenarios are unchanged. Independent review approved both fixes and their regressions.
- Final review-fix GREEN: build/typecheck, 149 unit tests, 10 Chromium cases and 10 WebKit cases passed. WebKit reports the intercepted video request as `other`, so the portable regression captures actual DOM before the fixture abort: canonical URL must be a `video.src`, never `img.src` or `video.poster`. The actual canonical request, no-stale-request and no-image-request checks remain. Independent review approved this stronger media-semantics check. Fresh exact-head CI remains required before native merge.
- The optional local backend container snapshot failed before tests could start because an old image digest was unavailable. Backend code is unchanged; the required full backend CI remains the release gate and is not claimed as locally executed.
- The only build warning is the existing Vite chunk-size warning. No new dependency or code-splitting change is included in this visual task.
- Final merge-SHA CI, deployment and runtime evidence will be appended to the PR description, avoiding a documentation-only redeploy. Browser-engine QA does not claim physical iPhone/Telegram-device testing.
