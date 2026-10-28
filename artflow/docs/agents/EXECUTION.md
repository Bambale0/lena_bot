# Execution ledger — Studio capability completion (2026-10-24)

## Active 2026-10-26 — Trend category shelves

Baseline `179d7a01e5a6328d9cb0642fa8fe9523e12fbafe`; Phase A implementation head
`55d5f796d0441796717db2a12638084d0de46761`; branch
`feat/admin-trend-categories-20261026`. The approved design and decision log is
[trend category shelves](trend-category-shelves-20261026.md); the binding staged
plan is [trend category shelves plan](../plans/2026-10-26-trend-category-shelves.md).
Mobile Telegram WebView is primary; site, Mini App, and text bot parity remains
required. Pricing, provider routing, payments, and paid generation are outside
this change.

Phase A implementation commits are `8c40d17` (expand-only revision 052, catalog,
relation, audit and backfill), `3a7156d` (bounded shelf/folder reads and typed
clients), `de6a9f5` (review-driven dual-write repair), `103107d`
(hidden-category admission plus the final `FOR SHARE` pre-claim recheck),
`840820f` (dynamic Telegram tag mirror), and `55d5f79` (database-filtered,
bounded, set-based migration backfill). The
preceding approved design commit is `080efe3`. RED tests were introduced for the
schema/backfill, bounded read contracts, and hide/run boundary before their
respective implementation slices. GREEN evidence is the focused Phase A run
below. Task 1 passed spec and quality review; Task 2 quality review found missing
legacy-tag dual-write, which `de6a9f5` fixed before reapproval; Task 3 passed spec
and quality review. Final whole-diff review found dynamic Telegram keys mirrored
as `featured` and an unbounded migration read; `840820f` and `55d5f79`
respectively fixed them with RED/GREEN regressions. Final re-review is APPROVED;
no unresolved Critical or Important finding remains.

Phase A intentionally exposes compatible readers only: revision 052 seeds seven
categories, backfills the nullable relation without deleting unknown legacy tags,
adds bounded catalog/folder queries and cursor validation, keeps existing writers
in sync with stable category tags, blocks hidden categories across public entry
points, lets already-claimed idempotent work remain retrievable, and teaches the
bot/admin picker plus web client types to consume dynamic metadata. Custom
category mutation endpoints and the new shelf/folder UI are **not** enabled;
those remain Phase B after Phase A production verification.

Local release-preparation evidence on Windows, using repository-maintained CI
commands and the pinned environments:

- Ruff: `python -m ruff check .` — passed.
- Provider inventory/readiness/smoke manifests — 100 contracts validated; the
  provider pytest bundle passed `474`, with one existing Starlette deprecation
  warning. Validation was dry/non-charging.
- Exact bot-navigation CI bundle — `371 passed`, one existing Starlette warning.
- Focused trend/migration/API/admin/visibility/reliability/routes set —
  `182 passed, 1 skipped`, one existing warning. The skip is the disposable
  PostgreSQL migration smoke because `APIX_TEST_POSTGRES_URL` is unavailable.
- Full backend with `PYTHONUTF8=1`, CI placeholders, disabled repository addopts,
  and a controlled `--basetemp` — `3827 passed, 87 skipped, 7 failed, 4 errors`,
  four warnings in 57.53s. The seven failures and four setup errors are existing
  Windows-only limitations: four Bash/Unix production-env tests, one
  Bash/OpenSSL nginx-config test, two symlink-privilege failures
  (`WinError 1314`), and four oversized parametrized temp-path setup errors. No
  Phase A test failed. Warnings are existing Starlette/anyio deprecations and two
  unawaited `AsyncMock` warnings.
- Web unit tests — `148 passed`; TypeScript `tsc --noEmit` — passed; Vite build —
  passed (`1674` modules) with only the existing approximately 760 kB chunk-size
  warning.
- Playwright Mini App smoke — `56 passed` across iPhone SE, iPhone 13, Pixel 5,
  and desktop. Focused Studio/UX2 consumer-completion plus fast-repeat coverage —
  `70 passed`, including preview viewport/reduced-motion behavior and repeat
  duration/quote/top-up/idempotency. The local `npm` launcher was absent from
  `PATH`, so the pinned Node runtime invoked unit/type/build and Playwright
  directly against a temporary local Vite preview; no browser failure occurred.

Migration head is `052_trend_categories`. The dedicated migration test is defined
to exercise an idempotent double upgrade, all seven seeds,
known/unknown/no-category backfill, unresolved audit evidence, revision state,
and the composite access index on a disposable PostgreSQL database; it was
skipped locally because that database was unavailable. PostgreSQL DDL for the
three new tables and composite index, plus representative shelf, ranked-preview,
folder, and `FOR SHARE` visibility queries, compiled successfully with SQLAlchemy's
PostgreSQL dialect. A real PostgreSQL migration run is still required in Linux CI.
The repository's full SQLite Alembic chain cannot reach revision 052 because the
pre-existing revision 001 uses PostgreSQL cast syntax (`::generationtype`);
therefore that failure is an environment/dialect limitation, not Phase A proof.

Before production migration, perform a read-only row-count preflight for total
`user_prompts`, rows tagged `trend`, and trend rows that will need
`trend_category_id` backfill. Revision 052 filters exact trend tags in SQL, reads
keyset batches of at most 500, performs grouped set-based recognized-key updates,
and batch-inserts unresolved audit evidence. The PostgreSQL test covers multiple
1105-row recognized/unresolved batches and an idempotent second upgrade; runtime
execution remains an exact-head CI gate. No production query, migration,
configuration, pricing, provider, payment, or generation was executed during
this preparation.

Release status: **READY_FOR_PROTECTED_PR**. Phase A is locally and independently
review-approved, but the
protected PR has not been opened and no exact-head GitHub CI, native auto-merge,
production autodeploy, migration/read smoke, public health check, or exact-SHA
Mini App verification has occurred. Phase B must not start until all of those
Phase A gates pass.
## Active 2026-10-26 — WAN native edit, P1 reward settlement release

- Base production main at preflight: `179d7a01e5a6328d9cb0642fa8fe9523e12fbafe`.
  Isolated PR branch: `fix/wan3-neironych-native-edit-20261026`, PR #306.
  Original commit: `d10fe0731ed7c3398dbbb6378c6bc4120804dec9`.
- Scope: repair native Standard WAN Edit route and actual-output settlement
  without changing admin pricing/routes, KIE-only incompatibilities or
  downstream acceptance semantics. No migration, manual SQL or paid test.
- Review P1 verified: Mini App prompt royalties were committed immediately
  from all reserved credits, while completion refunded unused duration. This
  could exceed net customer charge and create undeserved account credits.
  Additionally, existing use_prompt/add_credits helpers commit independent
  transactions, so they are unsafe inside atomic generation settlement.
- Fix: retain prompt use count on successful launch, mark pending author and
  referrer rewards in stored WAN billing, and pay from final bounded settled
  charge under the same Generation lock/transaction as result, customer
  refund, credit_ledger and notification. No payout on provider failure,
  no repeated payout for concurrent callbacks; a sub-one-credit charge
  cannot trigger a one-credit author bonus. Generation source id is included
  in reward ledger. Existing fixed-price model reward policy unaffected.
- Tests: new real disposable PostgreSQL schema reproduces RED P1, GREEN with
  deferred accounting (5 competing callbacks); successful completion/refund,
  race against failure, mid-reward ledger error rollback and retry, and
  no reward on failed generation. SQLite atomic rollback, routing and
  Mini App quote tests retained. Focused 45 passed / 0 failed; final full backend after fractional-credit test exit 0.
- Release gates: [x] complete full-suite Ruff/pytest/provider checks (exit 0; provider 100 contracts);
  [ ] publish amended PR HEAD; [ ] reviewer P1 addressed and resolved;
  [ ] exact-head required GitHub CI green; [ ] protected squash auto-merge;
  [ ] exact main SHA CI and Production Autodeploy; [ ] production
  running-container/version/health/errors verified read-only;
  [ ] final report and monitoring cleanup. No manual production restart.

## Active 2026-10-25 — Release remaining audited backend capabilities

PR302 merged through protected native auto-merge at f8779fb6c377479c456c512568982ccd3f20b94b, but exact-main CI40211783118 stopped deployment:392smoke passed,274/275Studio passed; held-preflight test read the intentional pre-response transactionId:null before response identity55. Backend/PostgreSQL,bot,provider and300journeys passed; Production Autodeploy was SKIPPED, not released. Separate test-only follow-up c534da5 deterministically reproduces the race with a held invoice response, then waits for persisted55 before releasing global preflight. Original exact identity, raw marker preservation, one POST and pending UI assertions remain; explicit zero-generation assertion added. Focused1/1 and full44fastrepeat/build/diff checks pass. No product, timeout, retry or backend change. Independent scoped review APPROVED with no findings (postmerge-ci-review.md); protected follow-up CI/main autodeploy/live verification remain mandatory. This is a new CI maintenance task, not a second final product fix wave; no blind rerun or manual deploy bypass. Cost if diagnosis is wrong: further investigation before any product change, never accepting null as a finished invoice.

Final whole-branch review completed over99files/19commits at46804dc; oneImportant curated failed-duration quote recovery was reproduced (selector vanished, close lostphoto/fields). Sole finalfix6326c44 retains only safe durationmetadata apart frompayablequote, invalidates oldprice, allows explicitretry/defaultreset withsamephoto/fields, noautoPOST. ActualRED422/503/defaultresetedge, final148units/typebuild/48fourdevice+44fastrepeat GREEN. Independent scoped finalre-review confirms ADDRESSED/no newCriticalImportant and code-reviewgateYES. NonblockingdenseadminJSX/chunk/dependency/toolchain warnings remaintracked; ordinaryMOVfixture observation notestablishedregression and historicallegacycheckout staysdisclosedoutsidecurrentAppguard. FullCI46804dc alreadygreen(364smoke/275UX2/300journeys/fullLinuxPG/bot/provider/Pinterest); amended-headCI required again beforeprotectednativeautomerge. Final proof belongs to exactmergedSHA mainCI+ProductionAutodeploy+readonlylive source/bundle/health verification, no paidproductionrequests/settingswrites.

Tasks1–6 are independently accepted. Task6fix4b56a59 scoped re-review confirms all3findings addressed/no new Critical or Important: post-preflight shared invoice claim, direct401/403 actor-lifetime revocation across payment roots with unresolved markers retained, and explicit photo launch assertions in300journeys. Actual RED reproduced race2POST/directauth9cases/methods403; final148units/type/build,44Task6browser and25domain10journeys pass. Integrated earlier e656528 fullLinuxPG/bot/provider/Pinterest and fullwebapp364smoke+254UX2 pass; separate300journeys275/300 oldphotoexpectation is now corrected, renewed exact-head CI mandatory. Fresh merged compatibility35pass4PGskips, diff check and known-key/token/sensitive-path scan clean. Final broad whole-branch review, exact amended-head fullCI/native protected auto-merge/main deploy and live source/bundle/health verification remain controller gates. No production paid work or live settings edits.

Release integration preflight: remote main advanced to e0f260ac0a1fdbef3cf909c0d9a21078030a1e54 through PR300/301 while Task6 was in progress. Preserve the independently landed Kling4/Qwen operations and migrations050/051 with a normal merge after the worker commits. This Studio task adds no migration or live policy change. Final integrated-head review, Linux/PostgreSQL migration checks and exact-SHA autodeploy remain mandatory; earlier production baseline is historical, not current proof.

Task6 implementation5020eec complete, independent task review pending. Fast preset/photo flow now requires one deliberate priced launch, hides optional controls, preserves same-actor drafts and refreshes exact quotes after top-up. Shared current-App/curated/feed invoice marker prevents blind duplicate checkout across close/reopen/reload; attributable receipt, balance and manual acknowledgement remain distinct. Finite invoice/status requests preserve uncertain post-dispatch outcomes. Actual148 unit/380 backend/type/build,23 final Task6 browser,52 four-device corrected-path cases plus4 final source-edit cases passed. Earlier full UX2252/253 and E2E205/240 failures were old UI/fixture expectations, documented and covered by final named reruns; do not relabel them as full-suite green. Full exact integrated-head CI remains mandatory. Historical separate ?legacy=1 checkout is unchanged and outside the current-App marker; new navigation does not send users there. Final task/whole-branch review and protected release still pending.

Newest user scope25October overrides previous lilac palette: black background and luminous red typography/actions, supported Telegram fullscreen, persistent actual balance+explicit Top up, profile owns work/history and prominent bottom Top up replaces duplicate Projects while central Create stays. Added sequential Task5 visual/fullscreen/navigation and Task6 short preset/photo/repeat+insufficient-credit recovery to bindingplan after current Task4 duration review. Fresh audit: scoped Studio CSS/AppShell reusable; Profile already has work/history, shell balance lacks explicit topup label; Telegram only ready/expand (no fullscreen/types/inset events), official8.0+ API verified; feed/curated runners have inline payments and preserved recipes, main video insufficiency currently text-only. New UX preserves exact quotes, explicit paid confirmation, actor/privacy guards and uncertain-launch reconciliation; no auto charge/payment on upload/topup. New Studio remains admin-only; website standalone palette/text-bot CSS outside app-specific redesign, applicable shared flow parity retained. No migration/config/price/model-admission change. Source plan is authority; earlier style statements below are historical.

Task5 black/red foundation f514f03 independently approved: no Critical/Important. Actual RED/GREEN fullscreen duplicate request, revoked stale balance action, purple canvas/nav and short-screen hidden header; clean browser152/152 plus separate persistent-phone-header hit-test1/1, four-device20/20,143units/type/build. Controller inspected actual home320/390, profile390/1280, repeat/topup; final distinct phone capture proves visible/clickable balance after works scroll/topup cancel. Profile owns full existing works/series; central Create retained, Top up is an action. Shared immutable balance bridge and topmost Sheet focus ownership preserve drafts and pending-payment guards, revoke on actor/access loss. Both active modern/legacy entries use best-effort fullscreen; disconnected AppV4 excluded after import audit. Actual Telegram hardware may reject fullscreen; no hardware guarantee claimed. Build marker20261025-studio-black-red-r1. Task6 must refresh exact runner quotes after global topup/resume, not treat header balance as a payable quote; short preset/photo/shortage journey remains next. Final exact-HEAD CI, broad review and protected production release still pending.

Task4 duration35a3043 plusfix344dd19: currentserver/backend/bot/OpenAPI202focused+459security tests,137units,40initialbrowser andactualstandalonesite6 green. IndependentreviewfoundImportantquote-error recoverylock andSeedance2.5siteadapter injection; actualRED reproducedboth. Fixnowretainscapabilitiesapartfromprice, duration-onlyauthordefaultreset/photo/source-editrecovery; exactsiteadapter skipsforbiddencontrols whileordinarygenerationkept. Fix265+59backend,137unit,228fullfourdevicebeforelasttinyreset then36finalfourdevicesafety,8actualsite/admin,type/build/Ruff pass. Scopedre-reviewapprovedallthreefindings/no newCriticalImportant. EarlyLinuxCI40198034681 exact35a3043 backendfullPG/botSUCCESS,Studio215PASS,smoke344PASS4FAIL oldvideo102auto-launchtestcontract; amendedtestnowassertszeroPOSTthenexplicitquotedlaunch, fullcoveringrunpasses. FailedoldCIisnotrelease; finalexactHEADCI/protecteddeployrequired. Newblack/redTask5nowimplementingfromea21d84; fastjourneyTask6followsreview. MOVcustomdropdownfixtureobservationoutsidechangednormaladapterbranchnotedforfinaltriage, notpaid/provideradmissionevidence.

Baseline main `6d84c0288c9a7ba16e663b7305c44ba77946e187`; clean feature branch `feat/studio-release-20261025`. Approved scope/style and implementation plan: [release completion](studio-release-20261025.md). Fresh backend preflight confirms atomic manual refund helper is reusable but endpoint currently splits commits; fix before exposing action. Pricing has no server CAS; changed-fields and fresh-state check mitigate, not eliminate simultaneous races. Existing supplier row-lock and Tribute per-product CAS retained. Admin-only rollout unchanged; no new migration, production config, pricing or paid calls authorized for tests. Consumer tasks followed by operational admin then system settings; independent task/final review and protected exact-SHA release required. Baseline frontend units126pass. Progress: preflight/spec complete; implementation/review/CI/deploy pending. Runtime observability reuses server ledger/audit/actor, safe UI errors and network diagnostics without private payload logging. Scratch artifacts under task work/studio-release-20261025; source ledger remains here.

Ruling: user asked explicitly for new Mini App frontend, so site/bot existing full controls remain; shared refund fix and truthful outcome copy apply to existing website too. No new standalone text-bot control plane or public feature launch. Current clean task clone and new feature branch reused without creating/deleting a worktree.

2026-10-25 progress: consumer task committed d513e49; independent native-typing review found focus loss, reproduced RED then fixed shared Sheet latest-callback/focus lifetime in96457f2. Final130unit/65browser/typecheck/build GREEN; scoped re-review approves, no new high/medium issue. Actual390px series screenshot inspected. Global admin-only route/menu/App gates and central48px Create at320/390/768/1280 remain verified by included tests. Remaining known non-CAS series replacement race is disclosed; fresh read/confirmation mitigate, no fictitious revision. Next admin operations/settings; user additionally explicitly requested duration choice beyond10s in BOTH curated Trends and feedvideo Repeat, fresh preflight ongoing. Local full backend baseline found7Windows-only failures(missingbash5,symlinkprivilege2) and4pytestlongparameterenvironment setup errors; no gate altered. ExactnewSHA LinuxCI required before release.

Admin operations task514a228 reviewed independently: no Critical/Important findings. Atomic manual refund/lost-transition409, whole-owner auth revocation, per-tab lifetimes, bounded reconciliation, changed-only fresh-checked pricing, ledger and published-prompt deactivation; site truthful outcome/cache identity aligned. ActualRED SQLite ledger failure proved split-commit problem; focused43pass54PGskips,11newpass4PGskips,134unit,40browser(inclsite+old),14finalaffectedbrowser,type/build/Ruffpass. Early feature-only CI40192572711 at514a228 is running real PostgreSQL/full maintained gates; production disabled for feature ref by existing policy. Reviewer Minor: dense new JSX and existing warning noise, tracked for final review. No new migration/live config/financial writes.

Duration scope now fully specified as Task4 after fresh backend/capability/admission audit: saved default preserved, explicit supported override in both curated and feedrepeat, strict validation/quote/claim identity/legacy hash compatibility; source-length edits explained locked; no new model access/tariff or durable-admission migration. Telegram admin options use installed runtime caps, not universal5/8/10; all applicable surfaces tested. Task3 provider/recovery/supplier/Tribute/content controls remains next after Task2 PG gate.

System settings taskd3d633d complete and independently approved: Wan/Qwen/Nano routes, recovery seconds, image/Seedance supplier reconciliation, Tribute product CAS/immutable economics, Kling audience and private feed identity editor. ActualRED/GREEN covered historical product disable after planchange, Unicode bounds and stale success notice. Final137unit/96browser/type/build pass,320px screenshot inspected. No new backend endpoint/migration/dependency or live policy/price change. MandatoryPUTfields preserved per actualDTO (Qwenprimary+backup; Wan/TributeCAS), PATCHchanged-only guidance does not erase requiredcommandfields. Supplieropenqueueabsence never automaticallyproves settlement. Non-CAS simultaneous-admin limitation and safeJSint bound explicit. Independentreview noCritical/Important; inheritedwarningnoise deferred. EarlyCI40192572711 at514a228 fullygreen: backendfullPG,botnav,340smoke174Studio browser; nofeaturebranchdeployment. Task4 now executing, finalnewHEAD+mergedSHAprotectedreleasechecks required.

GitHub follow-up review: initial-head CI passed all gates (332 smoke,135 Studio,300 journeys), but an unresolved P2 correctly blocked native auto-merge. Cached music library text could resurrect on return. Reproduced RED, added one-shot parent handoff consumption;19 focused capability tests, type/build GREEN. New head must pass fresh CI before merge; no bypass.

Baseline `86d8c69b63f5f7be5b26dedced9aca1159f34e35`, branch `feat/apix-studio-capability-completion`. User approved lilac style and requested Create centered plus existing backend frontend capability coverage. Fresh mounted-route preflight completed. Central CTA, plan-aware checkout/preflight, profile/password/avatar, voice segment/language/metadata, protected download/public links, library sources/type routing and owner detail/moderation implemented. Independent review P2 active-reference regression reproduced RED, fixed and verified GREEN; re-review has no actionable findings. Local unit126, focused Python19, full UX2/Studio browser135, type/build/Ruff passed; mobile screenshot inspected, central geometry checked320/390/768/1280px. Exact-head CI/deploy pending. Specification, decisions, gaps, test seams and progress: [capability completion](studio-capabilities-20261024.md). No new products, migrations, tariff/provider-policy changes or public rollout. Test-first vertical slices use synthetic intercepted writes, never live paid calls.

# Execution ledger — lilac admin Studio (2026-10-24)

Baseline `43c27c7e7015f06025ca4211b50e9af2f522a5ca`; isolated feature branch `feat/apix-lilac-admin-studio`. User authorized backend audit followed by complete frontend integration behind an admin-only main-menu entry, and explicitly narrowed the first release to all existing APIX functions. Fresh independent read-only audit completed. Scope, capability matrix, acceptance, plan, risks and live evidence: [lilac studio execution](lilac-studio-20261024.md). No public rollout or new business policies.

Implementation: five-section lilac shell; task-oriented home/create; models, prompt library/moderation/public consent, assistant, music/source audio/voice verification, tools, help, billing, owner cabinet; current generation forms and signed runners reused. Server admission and bot/Mini App launch entries are admin-only. Focused Python23pass, frontendunit123pass, currentnewbrowser23pass, previousfullUX2browser114pass, fullRuff/providerinventorypass. Full Windows backend3719pass81skip with7Bash/symlink failures and4oversized-test-ID environment errors; exact-head Linux CI required. Independent review reports no remaining blockers after fixes; native protected PR/autodeploy pending. No migrations or paid provider/payment tests.

# Execution ledger — private Studio catalog ownership (2026-10-22)

Baseline `9d3b92f542bfe2d2780c95a68c3c06eb902455bc`, branch `fix/kling4-private-catalog-20261022`. Original integration and observer fix deployed through protected PRs #290/#291; exact-SHA CI/autodeploy successful, server audience admin. Final spec audit confirms boot concurrently loads public/private data; delayed public landing overwrites private admin models, hiding Kling. Same public refresh occurs after sharing. Fresh audit: actual boot/loadPublic/loadPrivate/applyModelPayload/clearPublicData/logout call paths inspected; no backend/schema/config changes needed. Acceptance: delayed public payload or public fallback never replace a successfully loaded same-owner private catalog; logout clears private model snapshot; server remains authority. Add deterministic browser regression with real prototype script and controlled API response order, minimal per-owner catalog ownership marker, focused checks and independent review, feature PR/native auto-merge, exact-SHA CI/deploy and unmodified production Studio/browser/API check. No paid calls or public rollout.

Catalog fix evidence: actual prototype boot + delayed landing regression failed before implementation. Same-owner private catalog now survives public landing/fallback; logout clears the snapshot. Review exposed a late-private logout race, independently reproduced with anonymous state and old admin models. Auth generation now increments on login/logout and rejects stale /me, core catalog/history and extra-private results, including relogin to the same ID. All52Studio scenarios across4devices pass in an isolated output directory; initial parallel review/test artifact collision caused one ENOENT at trace cleanup, no assertion failure, rerun clean. Both independent reviewers passed focused regressions and report no blockers. JS syntax/diff checks pass; cache version bumped. Full backend3735 and frontend119 unit evidence unchanged; exact newcommitCI and final unmodified production checks pending.

CI amendment: strict existing Python gate rejected Studio-only cache-version bump. All nine HTML references now use the same new prototype runtime version, and the gate's exact expected value was advanced; the all-pages assertion remains unchanged. Fresh full local backend:3735passed/zero skips/3existing warnings; full Ruff and diff pass. Runtime JS unchanged since independent approval. New exact-head CI required.

GitHub review amendment: per-category successful private precedence replaces whole-catalog ownership; normalized public snapshot supplies failed private category fallback. Logout invalidates auth, restores public snapshot and re-renders cards/selects. Three regression cases cover failed image/video/music private requests followed by delayed successful public payload and DOM cleanup on logout. All64Studio scenarios across4devices passed; both reviewers independently passed3Desktop cases and found no blockers. Existing auth-epoch and delayed-public regressions remain green. Runtime pricing, backend and policy unchanged; exact final SHA CI and production checks still pending.

# Execution ledger — Studio observer recovery (2026-10-22)

Baseline `a402fb17bcfe50c82fd07429180d2a7d13f5d73e`; branch `fix/kling4-studio-observer-20261022`. Post-deploy production API/Mini App and admin gate pass, but actual Studio freezes while initializing default MiniMax H3. Evidence: Chromium renderer exceeds 100% CPU; diagnostic observer counter disconnects repeated observers, then both Kling controls become usable. `minimax-h3-studio.js::configureH3Controls` rebuilds select options and label text on every child-list observation, triggering its own observer indefinitely. Existing H3 behavior predates Kling but blocks the requested integrated Studio. No model/backend/tariff changes required; preserve other model choices and reference controls. Acceptance: observer converges at default H3 and supports H3→Kling Reference→Kling Keyframe with original scripts loaded; no polling/mutation masking in final production verification. Regression first with diagnostic cap only to prevent a hung test, then minimal idempotent DOM updates, focused/full applicable checks, review, new PR/native auto-merge, exact-SHA autodeploy/health and actual site check. No paid POST or public rollout. Main PR #290 merged/deployed successfully; policy remains admin, quote 3s720p=85.5, 10 prior live KIE outputs cost1073credits.

Verification before follow-up PR: new regression failed before patch (observer loop cap hit) and passed after patch; all24Studio scenarios across4devices passed. Both independent reviewers found no blockers, each reran Desktop regression successfully. JS syntax and diff checks pass. Studio script version bumped to bypass600secondassetcache. Production browser preview with only H3 JS replaced by reviewed local patch (no observer instrumentation) passed both actual Studio Kling editors; authenticated API stilladmin, publiccataloghidden, quote85.5, no paid submissions. Final production check must remove the local script override after normal CI deploy. Backend unchanged; full3735pass backend evidence remains applicable, exactnewcommitCI required.

# Execution ledger — Kling 4 admin preview (2026-10-22)

Baseline `2457849` on `main`; branch `feat/kling4-admin-preview-20261022`. User requests full KIE Kling 4 integration, live API smoke and Playwright verification; only administrators may see or submit it until an explicit later release command. Untracked diagnostics and root error.log are pre-existing and excluded.

Preflight: root/application AGENTS, README, CI, KIE transport/specs/webhook, video service, shared site/Mini App quote/launch, bot capabilities/FSM/billing, DB pricing and runtime policies inspected. Tool repositories refreshed: Bambale0/skills, Bambale0/claw, wondelai/skills, anthropics/skills. Local TDD/verification, backend-integration, clean-code and webapp-testing guidance apply. Supplied guide is the originating spec; official KIE Markdown schemas and current pricing successfully fetched independently. Reference and keyframe are two model IDs; 6 resolution/video-input tariff combinations. Official keyframe callback documents first_frame required for middle/last frames despite permissive request schema: fail closed pending smoke evidence.

Outcome/acceptance: both model routes, 3–30 integer seconds, 720p/1080p, typed validated references/keyframes/elements/voices, measured input duration and exact DB-backed quote, shared existing generation/history/refund/recovery/delivery path, no ambiguous POST retry; server-side admin gate on discovery/quote/submission/repeat and all applicable product surfaces. Authenticated audited DB rollout control defaults to admin preview; no public release performed. Existing admin pricing remains the price authority; no secret in ordinary settings. Additive migration and rollback preserving task/audit evidence. Logs use local/provider task IDs and safe failure classes, never full prompts/media/secrets.

Test seams: strict contract/quota/tag validation; KIE MockTransport single POST/unknown outcomes; real quote/access handlers, pricing and media probes; Telegram navigation/authorization; migration on disposable DB; frontend forms and browser admin/user parity. Live smoke bounded to six minimal 3-second tariff cases, no blind retries; record task IDs, provider credit usage and result validity. Additional capability smokes only within a recorded budget. No user-wide broadcast or public enabling.

Steps: 1. [x] fresh audit and skill discovery; 2. [x] contract, rollout policy, tariff migration and RED tests; 3. [x] common API/worker/Telegram integration; 4. [x] site/Mini App controls and browser tests; 5. [x] live provider smoke and full checks; 6. [x] standards/spec/OCR review; 7. [ ] PR + exact-head required CI + native auto-merge; 8. [ ] merge-SHA Production Autodeploy and public health. Follow-ups and evidence updated during execution.

Progress evidence: contract/access/quote regressions RED→GREEN; first focused gate 176 passed. Full initial suite exposed new model inventory/label assumptions, now fixed without weakening existing expectations. PostgreSQL real tests confirm concurrent duplicate admission, wallet rollback on intent-insert crash, single-use submission across fresh sessions, and terminal CAS. Full blank-database Alembic upgrade through 047 passed. Live KIE: six tariffs succeeded; corrected character/voice tests succeeded; mixed/fractional probes succeeded. All 10 outputs downloaded and ffprobe/preview validated; total provider task charge 1073 credits, initial two capability failures 0. Billing amended from conservative guide hypothesis to observed ordinary-video-only accounting; 3.125-second input is rounded to the next second. Smoke report/runbook: docs/kling4-admin-preview.md. No customer balance used for direct provider smokes.

Standards/Spec review found intent-payload mismatch, image-element edit invalidation, recovery starvation, legacy result replay and missing guided bot advanced edits. Regressions added and repairs applied; amended review pending. OCR delegate inventories 44 source files; per-source rules loaded, excluded tests/docs checked manually. Playwright Mini App 3/3 passed (admin quote/material submit, ordered frame UI, ordinary catalog hides model); standalone Studio harness tests and full amended checks running. Existing generic feed recipe cloning is explicitly unsupported/hidden for Kling because it cannot safely preserve this model’s typed roles and ownership; own bot result repeat is supported through the dedicated editor. Source uploads are user-scoped. No public rollout or manual production rebuild performed.

Final amendment: shared existing six-active-task admission limit and explicit Telegram refund receipt preserved. Account changes now clear typed drafts/remount Mini App material controls, cancel Studio upload batches, and stop subsequent files; authenticated upload checks captured owner before reading/storing bytes. Server no-read regression and delayed two-file browser regression pass. Automatic material names remain unique after deletion across character/voice namespaces. Independent amended Standards and Spec reviews report no blockers. Full backend re-run before last owner-admission test: 3728 passed, zero skips, 3 existing warnings; final full backend: 3729 passed, zero skips, 3 existing warnings (48.42s); full Ruff passed. Frontend typecheck/build and 116 units pass. Broad Playwright: 248 main + 88 UX2 scenarios passed; latest amendment focus: 16 Studio across four devices + 3 Mini App passed. PR #290 previous head required checks all green; final amendment requires fresh exact-head checks. Native auto-merge temporarily disabled while publishing amendment; re-enable after push. No public rollout performed.

GitHub review amendment: all eight original-commit findings addressed before merge. Public landing now applies audience policy; native Telegram `.oga` voice works; structured draft storage uses a validated allowlist and owner envelope; effective Kling input projection excludes parked generic media/Omni IDs from UI validation and checkout without exposing hidden removal controls. Site restores prompt maxlength on exit and failed recipe recovery no longer blocks unrelated models. Cheap balance/active admission precedes KIE staging; financial reservation locks/revalidates the exact tariff afterward, rejecting changed/disabled rates before debit. New API, PostgreSQL, storage and browser regressions pass. Latest full backend: 3735 passed / zero skips / 3 existing warnings; full Ruff, diff and JS syntax pass. Frontend typecheck/build + 119 units; Studio 20/20 and Mini App 4/4 pass. Independent amended backend review found no blockers; final frontend review found no blockers after canonical v2 storage was made mandatory for Kling drafts (parked legacy inputs survive reload). Fresh exact-head CI remains mandatory; no public rollout.

## 2026-10-22 — Wan feed photo collection

Baseline `636fcf111d74f3538d1d5ec04dd9ae34a01db386`; isolated branch `fix/wan-feed-photo-upload-20261022`. User authorized repair after read-only diagnosis. Wan edit recipes require multiple photos; Telegram asks for one and leaves upload state immediately. Synthetic reproduction retained one reference; existing 64 checkout tests miss upload navigation. Relevant source hashes match production.

Acceptance: Telegram collects multiple reader photos for video-reference repeats, announces the recipe-derived minimum and refuses early Done; site/Mini App expose the same safe count and prevent premature quote/launch. Private inputs, auth, pricing, exact quote and pre-debit validation remain authoritative. No migrations, runtime/admin configuration or paid smoke. Counts derive from stored recipe, never source/account IDs. Existing safe logs/journals retained; progress makes rejection actionable without logging media.

Preflight: instructions, local skills, README, feed schemas/routes, bot FSM/upload, shared runner/legacy entry, tests, CI and prior Wan PRs #282/#283/#284 inspected. Sources: local debugging/TDD/verification, claw review checklist, wondelai legacy-code guide; Anthropic webapp-testing inspected; Bambale code-review for independent review.

Steps: 1. [x] baseline/audit; 2. [x] seven Python failures reproduced lost uploads/early Done/missing public count; both new browser cases failed before implementation; 3. [x] shared count and site/mini_app/telegram_bot parity; 4. [x] 152 initial focused Python checks, full pytest 3579 passed / 76 environment-dependent skips / 0 failures (3 pre-existing warnings); 114 frontend units, fresh typecheck/build and all 40 Desktop repeat browser scenarios passed; full Ruff/compile/diff passed; provider inventory/readiness/dry smoke valid for 98 contracts. Exported OpenAPI: 195 paths, artifacts unchanged because feed cards use existing dictionary responses. Independent Standards and Spec reviewers found no blocking findings. Existing exact first/last-frame excess-photo UX remains server-rejected, outside this four-photo edit fix; no acceptance rule weakened. Existing per-FSM event isolation covers sequential album processing. 5. [ ] PR/exact-head CI/auto-merge; 6. [ ] autodeploy/health. No production mutation or paid render. All 8 Wan/Prime browser cases across iPhone SE, iPhone 13, Pixel 5 and Desktop passed. CI must cover local environment skips.

## 2026-10-21 — Prompt / Pinterest / Telegram media fixes (active)

Baseline `7b037621a3c418b3b1add1a5e523fcc8ef5ef230`. Diagnosis, acceptance, numbered plan and live progress: [execution details](prompt-reference-media-20261021.md).

## 2026-10-21 — Nginx / ACME repair (active)

Baseline `9f7bff637ee8112aeee880d475a867db339d3e4c`. See [execution details](nginx-acme-20261021.md) for preflight, acceptance, risks, progress and verification.

## 2026-10-20 — provider rejection reasons and Seedream reference admission (active)

Baseline `07dc84a140b9bf71119af7894249ebef51b3bf3b`; isolated worktree `/tmp/apix-provider-rejections-20261020`, branch `fix/provider-rejections-media-20261020`. User requests fixes for the three highlighted production failure groups. Read-only production evidence: two Seedance 2.5 GET statuses explicitly report `provider_rejected_request`, `retryable=false`, without a detailed cause; two Seedream text tasks report output copyright restriction; one Seedream edit used an unreachable former-domain URL with no matching local file. Existing guarded refunds worked. No customer prompts/media/identifiers are copied here.

Outcome/acceptance: reject missing or unreachable Seedream references before paid provider submission; upload accessible external Seedream references to KIE file storage and preserve ordering; surface safe, actionable copyright/reference/rejection reasons consistently in site, mini_app and telegram_bot without exposing hidden prompts. Never automatically resubmit terminal moderation/nonretryable jobs. Existing prices, provider routing, authorization, task correlation and once-only refunds stay authoritative. No migration or new mutable business setting; this repairs adapter transport and existing public error projection.

Preflight: README, root/application AGENTS, Compose, CI, upload/config paths, image service, KIE callbacks, video recovery/outbox, public serializers, tests and production provider GET/ledger evidence inspected. Reuse local KIE stream upload and the official free KIE URL Upload API for external references; APIX never fetches user-provided remote URLs on this new path. Require image MIME, positive bounded size and HTTPS staging output; finite upload retries. Risks: expired original media cannot be reconstructed; provider moderation/rejections cannot be eliminated by client code; download failures must not submit paid jobs or leak URLs. Observability: log only model and safe failure class during reference admission; preserve raw provider diagnostics server-side and return allowlisted explanations. Test seams: shared generate_image transport boundary, public site/Mini App serializers, KIE callback notification, durable Seedance notice and privacy/refund regressions.

Steps: 1. [x] fresh audit and provider/DB diagnosis; 2. [x] relevant skill discovery (local systematic-debugging/TDD, claw backend integration, wondelai clean-code; Anthropic webapp-testing inspected, browser workflow only if needed); 3. [x] RED regressions reproduced paid submissions with missing/unreachable media; 4. [x] minimal adapter repair and KIE staging; 5. [x] RED public reason tests, site/Mini App/realtime parity, protected KIE notices and Seedance failure notice; 6. [x] independent Standards and Spec reviews (initial local gate: 3580 passed, 3 existing warnings, zero skips; independent review identified DNS rebinding, invalid local media, and non-atomic Mini App reference refunds. Revised adapter uses official KIE URL staging without APIX fetch, local decoding, and a typed admission failure settled through the existing atomic wallet/ledger transition. New HTTP/financial regressions cover those findings; amended full local suite: 3591 passed, zero skips, 3 existing warnings; full Ruff/compile/diff/98-provider checks pass; both amended review axes report zero remaining findings; Spec independently ran 14 focused tests successfully; GitHub review also identified the need for a whole-batch deadline: RED stalled-upload regression reproduced the issue, a typed 30-second default (validated 1–45 seconds) now cancels preparation before paid submission, independently re-reviewed with no blockers; protected CI pending); 7. [ ] PR #285 created; exact-commit protected CI, native auto-merge, autodeploy and public health pending. Skills: `.clinerules/skills/systematic-debugging/SKILL.md`, `.clinerules/skills/test-driven-development/SKILL.md`, `/root/bambale-skills/skills/engineering/code-review/SKILL.md`, `/root/claw-tools/.agents/skills/backend-integration/SKILL.md`, `/root/skills/clean-code/SKILL.md`; Anthropic webapp-testing inspected, browser workflow not needed for shared API-only changes. Pre-existing production diagnostics/error.log left untouched. No manual production mutation or paid provider test.

## 2026-10-16 - Complete remaining audit findings

PR #279 review amendment: five independent P2 findings reproduced and fixed (Lava eventType, partial-refund net revenue, safe rejection correlation/reasons, ledger-proven legacy failed payments, partial/full refund bot copy). New tests initially failed on each cited behavior; all seven pass after repair. Full amended local release gate: 3461 passed, zero skips, three existing dependency/mock warnings; full Ruff/compile/JS/shell/diff checks pass. No schema change beyond already tested 045/046. Awaiting amended-head independent review, protected CI and autodeploy; no manual production mutation.


Final local pre-PR: 3454 pytest passed with disposable PostgreSQL and official Nginx, zero skips (3 nonblocking pre-existing warnings); 58 Desktop Playwright tests and 114 frontend units passed. Independent OpenAPI exports match (195 paths); provider inventory/readiness/dry manifest report 98 contracts. Actual 045/046 migration roundtrip and guarded rollback pass. Full Ruff/compile/JS/deploy syntax/diff checks pass. All original runtime/fixture findings are implemented and classified; no paid API call or manual production mutation. Next gate is independent PR review plus exact SHA CI/autodeploy and running-source verification.


Progress: refund/cumulative/event-order implementation and immutable Tribute catalog are complete in the isolated branch. Additional real defects in legacy menu parity, Seedance registry synchronization and lowercased trend quality were reproduced/fixed. A full PostgreSQL-backed run reached 3414 passed/2 Nginx-environment skips; financial/catalog/migration hardening subset is 114 passed. Actual 045/046 migration roundtrip and accounting-preserving downgrade guards passed. Catalog browser editing/auth/conflict scenarios (3) and frontend unit tests (114) passed. Full Ruff/compile/JS syntax pass. Some larger tool requests were rejected before execution and were not counted as verification; subsequent independently scoped source edits/checks have explicit outcomes. Full CI is now the release gate. Pending: final all-tests with Nginx enabled, full browser checks, immutable docs export, independent PR review, protected merge and exact-SHA production proof.


Baseline `0da8798d42dafbe2ba721bebcb85fe186605026b`; branch `fix/audit-completion-20261016`; isolated worktree. User explicitly requests completion of every remaining audit finding, not re-verification of PR #278 alone. Existing refund draft is evidence, not releasable code. Production checkout/configuration/customer balances are not edited manually. Local container has no GitHub DNS; connected host has supported test environment and remote GitHub tooling.

Acceptance: atomic refund status/wallet/ledger/referral accounting across T-Bank and Tribute, cumulative partial refunds only under verified provider semantics, monotonic statuses and duplicate/concurrent/out-of-order protection; typed audited DB Tribute catalog with authenticated admin operations and matching checkout across site/Mini App/bot; classify and repair all historical failures without weakening safety expectations; full pytest/Ruff and relevant browser/provider/migration tests pass; independent review and protected-main auto-deploy verified on exact SHA. No paid provider call or customer compensation is authorized by this code task. Mutable settings reuse the admin/control plane; credentials never enter the DB catalog. Additive schema migration tested on disposable PostgreSQL; forward-fix production rollback to preserve financial evidence.

Test boundaries: signed HTTP callback -> real disposable PostgreSQL -> wallet/ledgers; provider response parsers; payment status checker; catalog admin auth/validation/concurrency; shared checkout consumers; full historical suites with isolated mocks; browser admin/trend/checkout smoke. Observability: provider, transaction ID, safe failure class and immutable refund/audit records, no full payload/media/token. Main release #278 remains unchanged until reviewed commit is deployed normally.

Steps: 1. [x] fresh instructions, main/open PR/draft inventory; 2. [ ] official provider semantics and RED regressions; 3. [ ] refund fix and migration; 4. [ ] Tribute catalog/admin/surface parity; 5. [ ] classify/fix full pytest; 6. [ ] full checks and review; 7. [ ] PR, exact-head CI, merge/autodeploy/runtime verification. Existing unrelated PRs are left untouched.

## 2026-10-16 - Audit runtime contracts remediation (active)

Branch `fix/audit-contracts-20261016`, baseline `1f64429d`, isolated worktree `/tmp/apix-audit-contracts-20261016`. User requested all audit findings. This independently releasable slice covers bot trend entry, callback log privacy, provider exposure/readiness, OpenAPI security and historical test/Ruff contracts. Prices, payment behavior, credentials, permissions and production DB remain unchanged.

Financial fixes are NOT included: the separate `/tmp/apix-audit-remediation-20261016` workspace contains the three confirmed refund rollback failures and an initial six-test-green full-refund draft. Further partial/late/referral tests fail and the next financial write was blocked before execution. It was not retried or moved here. That draft must not be deployed; P1 refund/partial handling and Tribute business configuration stay explicitly open.

Evidence/plan:
- [x] Repository instructions and four updated engineering skill repositories inspected in the initial task; preserve unrelated PRs and production checkout.
- [x] Historical baseline reproduced all 44 pytest failures and 27 Ruff findings (log paths `/tmp/apix-audit-baseline-*`).
- [x] Bot photo callback bypass and raw callback logging reproduced; all image/video trends now open the shared Mini App runner, with four passing bot navigation tests. Four callback privacy tests pass without changing signature validation.
- [x] Catalog public exposure derives from actual operation registry, removing stale independent flags; two tests pass.
- [x] Exporter/CI consistency, explicit auth metadata and nonbillable readiness semantics; generated dashboard strict check passes for 98 contracts.
- [ ] Full suite classification remains OPEN (3305 passed / 47 failed / 13 skipped on pinned local run). Full Ruff is fixed and enforced in CI. Blocked test-update batches did not execute; no historical assertion was suppressed.
- [x] Generated artifacts and explicit open-item matrix updated; two independent OpenAPI exports identical. Full Ruff/compileall, maintained backend gate and bot-navigation pass locally. Callback/payment subset: 47 passed; frontend unit: 114 passed; build and 2 mocked-browser direct-link cases passed. Provider inventory/readiness/dry smoke pass.
- [x] Reviewed bot path end-to-end: the legacy App trend branch is unreachable because parseStartTarget deliberately excludes trend; the existing portal owns deep links. No production frontend change was needed. Added image/video browser regressions rather than rewriting correct routing.
- [ ] PR/exact-head CI, native auto-merge and merge-SHA deploy verification. Financial and full historical-suite findings stay explicitly open; this is not completion of the entire audit. Browser suite beyond the two direct-link cases is running as job_2017f2846413, not yet claimed green.

External patterns: FastAPI supported OpenAPI customization; OAS security OR alternatives and optional empty requirement. Existing authentication checks remain the only runtime authority. No live paid/provider operations are part of verification.

# Execution ledger — video to prompt integration

## 2026-10-15 — Qwen 3.8 through Neironych

Baseline `49b39a05cfc0aed91f1f970d78025684ecb10dfa` on `main`; isolated branch `feat/neironych-qwen38-20261015`. User-supplied reference is `Bambale0/banano_kling` `tanyapi` SHA `a7a498044f7f40eaac07b38d7e56c7c49caec026`. Current APIX text assistant routes KIE then Comet, photo prompt routes KIE then Comet, and video prompt calls Comet only. Telegram, Mini App and site already share photo/video service functions; video prompt has precharge and refund on failure. Neironych credentials/base URL exist for other models, but Qwen chat, image, video, JSON and reasoning contracts are not yet verified. Live Comet video diagnostics timed out; the user was refunded for the reported failure. Existing provider routing admin controls only Nano Banana 2.1 and cannot express LLM capability routes. The Qwen branch must remain separate from video-reference pricing and Wan PR #265.

Outcome: one typed Neironych Qwen 3.8 adapter for text, image and video; route ordinary assistant, photo prompt and video prompt through it only when corresponding capability has real contract evidence, with verified KIE reserve and safe errors. Preserve current prices, authorization, histories, one charge/refund, and no automatic second potentially paid request after an ambiguous first. Do not enable Qwen for moderation, web search or tools. Admin-selected routing must be typed, audited and authenticated. No secret in logs or DB. Provider traces need mode, model, request ID, latency and failure class without prompt/media. Acceptance includes HTTP mock contracts, response validation, surface tests, real paid smoke only after the explicit user permission required by the supplied spec, exact-head CI, PR, auto-merge and public production health.

Risks: catalog presence does not prove Neironych image/video support; KIE supports photo through existing Responses contract but no proven native video-to-prompt path. Provider timeout is an ambiguous paid outcome and cannot trigger automatic fallback. Any unsupported capability must stay disabled until a real test proves it. No production data mutation is planned except normal audited admin routing and existing customer billing.

Steps: 1. [x] repo instructions, reference SHA and existing APIX surface/provider/DB audit; 2. [x] RED contracts and capability probes; 3. [x] adapter, admin routing and surface integration; 4. [ ] focused tests, Ruff, review; 5. [x] authorized minimal paid smoke; 6. [ ] PR/CI/auto-merge/deploy/health. The user explicitly authorized one minimal real request for text, photo and video plus necessary KIE fallback. Neironych `GET /v1/models` lists `qwen3.8-max`; chat requires an `Idempotency-Key` (the first unbilled validation attempt returned HTTP 422). With that header, text returned the requested digit and a red-square image returned the correct color. The full photo-to-prompt service returned a 1,221-character Russian prompt for the synthetic red square. Neironych's `video_url` request returned HTTP 200 but answered “Неизвестно” for a synthetic red 2-second MP4; sending the MP4 as `image_url` returned 422. KIE `gemini-3.1-pro` accepted the video URL inside `image_url`, identified red correctly, and the full video-to-prompt service returned a 640-character structured prompt with an audio-not-analysed note. Therefore default video routing is verified KIE only; authenticated admin validation rejects Neironych video until a future visual contract passes. No user wallet or production generation was touched. The synthetic MP4 was placed under a diagnostics-only public upload path for the probe and will be removed after checks.

The adapter now has a wall-clock deadline, request correlation, strict completion parsing and no automatic retry. `qwen_routing_settings` and `qwen_routing_audit` are an additive migration; admin GET/PUT is authenticated and initial persistence is audited. A definitive Neironych 4xx can invoke one KIE backup; timeout, transport, empty or ambiguous completion stops before a second paid request. Ordinary assistant, photo prompt and video prompt share these services across bot, Mini App and site; advanced tools, moderation and web search retain their existing verified routes. KIE photo backup is restricted to the existing verified `gpt-5-2` chat call to prevent a second ambiguous paid request. No model price or user-facing tariff changed. `alembic heads` reports migration 042 as the sole head; compilation and focused tests are pending final review.

Local review and verification: 147 tests across assistant, prompt services, Telegram/web/Mini App surfaces and provider contract registry passed; another 36 focused surface/adapter/routing tests passed after correcting the download-error copy to distinguish no spend from refund. Ruff and `git diff --check` pass. `alembic heads` has one head (`042_qwen_routing`), and an offline revision-range SQL render from 041 to 042 contains both tables and the audit index. A full-history offline render is unavailable because legacy migration 003 introspects a live connection; the exact-head CI migration gate will exercise it online. Supplier-review case #59049 still requires a read-only status check before final delivery.

The synthetic 1,895-byte contract MP4 was removed from the production upload directory after the probes. Supplier-review case #59049 remains a separate incident liability audit; no customer balance change is authorized by this Qwen feature.

Review follow-up: admin can reverse text/photo provider order, so both services now honor KIE-primary → Neironych-backup only after a definitive KIE 4xx; 429, 5xx, transport and timeout still stop. Qwen and KIE multimodal extractors discard reasoning blocks, truncated/filtered completions are errors, and a short KIE photo answer is not accepted as a generated prompt. Regression tests cover reverse fallback and refusal classification. Production read-only incident check found #59049 failed with one 35-credit customer refund and an open supplier review after 96 `unknown` polls; #59570 failed with one 105-credit refund. A supplier invoice/usage fact is still needed to settle #59049; this feature does not change those rows.

Rebased onto video-pricing merge `e2bc43a8263e36caae84e539eea73bb787b1429f` without mixing its code into the Qwen PR. All 309 focused rebased tests pass, including pricing and prompt-security regressions; Ruff, diff check and single Alembic head pass. PR #271 targets `main` with native squash auto-merge enabled; exact-head CI, automated review, merge-SHA Production Autodeploy and public health remain pending.

## 2026-10-15 — PR #270 review fixes

Automated review found four valid gaps after the first green exact-head CI: Telegram motion-control repricing used an uninitialized rate; the separate site lacked a direct video quote and confirmation; flat-tariff references were counted but not measured; and model-specific Seedance/H3 file panels added videos after the Mini App quote decision. This amendment initializes the model tariff before the motion branch, measures flat-tariff source duration while keeping its billable total flat, adds authenticated web quote and a site price confirmation, and runs quote through the same Seedance/H3 enrichment as launch. The site parity layer now enriches quote as well as launch. All Mini App video jobs request a read-only quote, including Midjourney's flat tariff. Evidence: 59 targeted tests pass; TypeScript typecheck and Vite build pass; Ruff and JavaScript syntax checks pass. A separate legacy `test_video_reference_support.py` assertion expects KIE's removed `reference_video_urls` field and still fails when added to the focused suite; this change does not alter that provider adapter. Next: exact-head CI, review resolution, auto-merge, main-push deployment, public health.

The next backend CI found four prompt-security tests that used an external video URL without an owned file; flat tariffs now measure that URL before any spend, so the old test fixture could not create a quote. A dedicated measured-duration seam in that suite keeps its private-prompt and once-only-charge assertions intact. The full prompt-security suite now passes locally (153 cases); exact-head CI rerun pending.

The subsequent backend CI was green. The shared prompt-security fixture initially hid Seedance's real probe; routing only owned test media back to the actual measurement restored 217 passing prompt-security, Seedance feed and confirmation cases. User-journeys CI then found 25 video launch cases missing the new confirmation in its mocked API and steps; the E2E route now returns a quote and confirms before checking that launch carries `quoted_credits`. Typecheck and all 25 targeted Playwright Chromium journeys pass locally after installing the workflow's test-only dependency without changing package manifests; exact-head CI remains the release gate.

## 2026-10-15 — Video reference pricing and preflight quote

Baseline `d7e03268419bc2a03c86873cd37f939c1b44ccce` on `main`; isolated worktree `/root/agent-work/apix-video-billing-20261015`, branch `feat/video-reference-billing-20261015`. User requires all video models with video input to measure the reference video(s) and actual normalized provider payload first, then show and charge the model tariff for combined input and output seconds where the tariff is per second. Flat video-input tariffs remain flat according to their database tariff. Current code charges output seconds only for most per-second models, while Seedance 2.5 edit substitutes source duration; studio web UI estimates from duration without probing source media, and only feed remixes have a server quote. Production model-cost rows are database-managed by authenticated admin; Seedance 2.5 720p currently resolves to 7 credits/second. KIE's official Seedance 2/2.5 docs confirm combined source-video and output seconds with a lower reference-mode rate; the APIX database currently has no reference-mode rate variants, so tariff configuration needs an explicit seam rather than hardcoded supplier rates. Existing public upload paths and `probe_local_media` can measure owned files without a paid supplier request. Multiple Seedance 2.5 video refs are normalized from control tokens into `reference_video_url`; MiniMax H3 likewise normalizes refs from `character_ids`. Protected prompts, ownership, precharge validation and refund semantics must remain intact. No customer identifiers or media URLs belong in the ledger.

Acceptance: for a video draft with references, all supported surfaces show a server-calculated quote with measured input seconds, requested output seconds, model rate and total before the paid launch. Paid launch recomputes the same billable payload and rejects stale prices before charging. Multiple video refs sum once after deduplication; image/audio refs add no video seconds. No reference leaves existing billing unchanged. Provider-specific flat products use their flat DB rate. Unmeasurable video refs fail before charge. Audit records measured seconds and tariff source without exposing media. Tests cover provider adapters, quote/launch parity, bot confirmation, site/Mini App, auth, idempotency and exact-tariff lookup; CI required checks and automatic deploy must pass. Steps: 1. [x] repository/model catalog/admin and runtime audit; 2. [x] official provider billing docs checked; 3. [x] regression billing/quote tests; 4. [x] shared calculator uses active DB model tariff; no new tariff variant or migration is needed because the requested price rule is input-plus-output seconds at the configured rate; 5. [x] site/Mini App/bot preflight UI; 6. [x] 207 focused tests, Ruff and diff check passed; [ ] review, wider gates and rebase; 7. [ ] PR, exact-head CI, auto-merge, production health. Risks: remote provider URLs may be unmeasurable; auto output duration may be an upper-bound quote; provider tariffs are not identical across products.

## 2026-10-15 — Nexus image failure copy

Baseline `4cc3d7d9ece5369354bfbfa19b9edf8083a5053e` on `main`; branch `fix/nexus-image-failure-copy-20261015`. Existing untracked diagnostics and `error.log` are unrelated. The customer's screenshot task maps to a failed `nano-banana-pro` generation at 11:13 Moscow time. A read-only Nexus GET confirms `failed` with only the generic Russian error "Не удалось сгенерировать контент...сид, промпт" and no result or further diagnostic. Two failed generations each have exactly one +1.5 generation refund ledger row. A later generation succeeded using the same prompt hash. The two failures used 2:3 aspect ratio while successes used 4:5/3:4 and reference counts varied, but 2:3 succeeds in other production requests, so the root cause cannot be attributed to ratio or prompt. No paid retry or production data mutation was performed.

Outcome: clearly report supplier failure and actual refund without showing raw provider boilerplate, suggesting unproven seed/prompt edits, or filling the Telegram message with a UUID. Keep a short APIX generation number for support. Normalize the same generic failure in site/Mini App history and realtime data while preserving raw diagnostics in the database/admin. Protected prompts stay hidden. No migration, price, provider route, secret, or permission change; this is presentation of an existing terminal failure, not a new policy. Test seams: shared public-error projection, KIE/Nexus bot notification with mocked callback and verified refund, existing parity/security/refund tests. Steps: 1. [x] provider/DB/ledger diagnosis; 2. [x] repo and skill audit; 3. [x] RED regressions reproduced raw Nexus boilerplate in realtime and bot; 4. [x] shared public-error translation and short Telegram notice; 5. [x] six focused suites, Ruff, compile and diff checks passed; 6. [x] read-only review found Mini App history omitted error entirely; RED test reproduced and the shared projection now reaches Mini App, all six suites plus Ruff, compile and diff checks passed again; [ ] PR/CI/auto-merge/deploy/health. A broader first test run found the legacy protected KIE notification contract still needs the provider task ID, so the short-number format now applies only to Nexus image failures; KIE/Midjourney notices retain their existing IDs.

PR #267 merged as `d7e03268419bc2a03c86873cd37f939c1b44ccce` after all required checks passed. Automated review arrived after merge. Follow-up branch `fix/nexus-error-review-followup-20261015` removes customer identifiers from this ledger, caps escaped provider text before Telegram delivery, and matches only the exact Nexus boilerplate so extra diagnostic detail survives. RED/green regressions cover long HTML-escaped errors and specific provider causes. The review also requests database-managed notification microcopy; this needs an admin control-plane design across bot, realtime, site and Mini App and is tracked as a separate product-system change rather than being folded into this incident repair. Main-push CI passed, but Production Autodeploy failed at `git switch main`: the shared checkout was on the new follow-up branch with uncommitted tracked edits. Commit the follow-up and let its main-push deploy run against a clean checkout; do not manually deploy. Six focused suites, Ruff, compile and diff checks passed for this follow-up.

## 2026-10-15 — Telegram video prompt download timeout

Baseline `db75d6e4f610af7d2d7a18c82f250035970be972` on `main`; branch `fix/video-prompt-telegram-download-timeout-20261015`. Pre-existing untracked diagnostics and `error.log` are unrelated. At 11:20 Moscow time the production app log shows `TimeoutError` from aiogram's `bot.download_file` while the bot handled the reported video. Aiogram's default total download timeout is 30 seconds; provider analysis was not reached. A read-only ledger query found zero `video_prompt_spend` or `video_prompt_refund` entries for that user in the incident window. No sample video or file size is available, so actual Telegram transfer duration after a larger deadline remains to be verified.

Outcome: allow legitimate video downloads up to the bot's 20 MiB cap enough time before analysis; preserve pre-charge validation and once-only refund semantics. Site and Mini App share the provider service but do not use Telegram download, so their upload handling is unaffected. No schema, tariff, permission, or provider change. Technical download timeout is a typed bounded setting (default 180 seconds, range 30–300); no secret or business control-plane change. Observability: existing exception stack and user ID identify download failures without logging media or Telegram file path. Test seam: fake bot records the `download_file` timeout and holds a download open to prove billing waits for completion, plus existing cross-surface billing/provider tests. Steps: 1. [x] production log and ledger diagnosis; 2. [x] tool and repository guidance; 3. [x] RED regression showing aiogram's 30-second default was used; 4. [x] minimal fix; 5. [x] three focused test modules passed, Ruff, compile and diff checks passed, read-only review found no blocking defect; 6. [ ] PR, required CI, auto-merge, deploy and health. Review noted that the 300-second FSM lock can expire if a download and 180-second provider call both approach their maxima; no overlapping request was observed in this incident, but lock lifetime merits a separate reliability review.

PR #266 review follow-up: all four required checks passed on the first commit, but automated review identified two valid findings before merge. The Redis FSM lock was only 300 seconds while maximum download plus provider wait is 480 seconds, allowing a second update to enter the same paid flow. The bot's auth middleware also opens a database read transaction before the handler, and the original handler read the price before downloading, so slow downloads could retain a pooled connection. RED tests reproduced the lock timeout and connection-release expectations. The lock is now 600 seconds, and the handler commits the auth read transaction before download, then reads the current price and charges only after file validation. Focused video/dispatcher tests, Ruff, compile and diff checks passed after revision. Exact-head CI and deploy remain pending.

## 2026-10-15 — first user photo anchors face in feed image repeats

Baseline: `f146602` on `main`; branch `fix/feed-photo1-face-priority-20261015`. The main checkout has pre-existing untracked diagnostics and `error.log`, left untouched. Previous production read-only evidence: Nano Banana Pro repeat #59492 used the creator prompt verbatim and one reader photo, with no creator image sent; its face still resembled the creator's output. The user now requests a stronger instruction that explicitly labels the first user reference “Фото 1 — лицо”.

Current state: original-recipe feed repeats require reader photos, preserve their order, and send only reader images. Site and Mini App use `/feed/{id}/remix`; the text bot has a separate launch path. The October 1 rollback removed the identity directive from both paths. A validated, audited database-backed identity policy and authenticated admin GET/PUT already exist but are not read by these launches. Existing version-4 provenance can bind a policy string for safe continuation.

Outcome and acceptance: for every compatible image model/provider, the first image actually sent to the provider is designated “Фото 1 — лицо” and is the sole facial identity anchor; later reader images may clarify the same person. Keep the original creator recipe for the scene and send no creator result or original reference. Quote and paid launch use the same rule; site, Mini App and bot agree. Continuation must replace old authenticated policy text without stacking instructions. Fail before charging if the required policy is unavailable. Do not promise pixel-exact likeness.

Risks/dependencies: provider may not follow identity guidance; overly long or conflicting instructions can reduce quality or trip filtering. Use a concise first-photo contract, preserve reference order, and avoid logging prompts/media. The existing admin policy remains editable and audited. Migration 041 updates only the unedited seed and records the change in its audit table; admin edits remain authoritative. No tariff/provider/permission change; no new secret. Observability: existing source generation, model, provider task ID and reference count; no private media in logs.

Test seams: shared prompt composer; API quote/launch with mocked provider transport for Nexus and Neironych; bot launch; saved continuation; provider reference ordering; admin policy; rollback/migration behavior. Planned steps: 1. [x] tool repositories, repo instructions, CI, code, schema, control plane and prior production evidence audited. 2. [x] RED tests for first-photo binding and pre-charge policy failure. 3. [x] Shared prompt composer, API and bot policy reads, conditional migration and docs. 4. [x] Focused provider/security tests and the maintained backend gate (85 CI selections) passed locally; PostgreSQL migration roundtrip passed on a disposable PostgreSQL 16 container; Ruff, compile and offline Alembic SQL passed. 5. [x] OCR delegate identified 5 reviewable source files, all 5 reviewed; 11 excluded docs/tests reviewed manually, with no unresolved high-severity finding. [ ] PR, auto-merge, exact merge CI, production health. No paid provider generation was launched during verification; visual face fidelity needs a post-deploy user result.

PR #264 review follow-up: GitHub review found that the seeded identity rule could override an explicit reader request for clothing, pose or hair color. A RED regression reproduced the missing precedence clause. Migration 041's default now gives explicit reader edits priority for non-facial details while Photo 1 remains the facial identity anchor. Focused recipe/contract tests passed; the revised migration roundtrip passed on disposable PostgreSQL 16. The audit-preserving rule still updates only an unedited seed. Exact-head CI and merge/deploy verification remain pending.

## 2026-10-14 — derived feed photo keeps creator's face (#59323)

Baseline `fe40d22aecd8e2d7091ba127e7d581b5586c6a7b` on `main`; branch `fix/feed-prompt-only-nano21-20261014`. Production read-only evidence: task `neironych-image:8836daba-9f60-58db-b18b-cb4c407b61c6` is completed generation 59323, Nano Banana 2.1, derived public source 59320. Source 59320 itself points to feed source 58419, so the original-recipe route correctly rejected it and the v3 public-scene fallback submitted two images: author's finished portrait first, the reader's same multi-view collage from generation 59292 second. The saved prompt is the concise scene-first edit header; it lacks explicit facial replacement instructions. Visual inspection shows the result kept the source person's facial features while adopting the reader's red hair and black clothing. The previous PR #253 only changed original-recipe v4, so it could not affect this v3 path. No provider request body is logged; persisted image reference ordering and adapter contract reconstruct the effective input. No production DB changes or paid retries were made. Chat imagegen produced a separate preview for the reader; it is not an APIX generation or proof of provider behavior.

User correction supersedes the first crop plan: pass the author's original prompt and only the reader's exact references, never the author's output or original photos. The preview crop did not preserve likeness and was discarded. For Nano Banana 2.1, direct, older and derived public image posts use recipe replay; derived posts resolve a bounded public image lineage to the original prompt and fail before charge if it is unavailable. At least one reader photo is required. Site, Mini App and Telegram bot share the server policy. Existing database-backed identity instruction is reused. No new dependency, migration, tariff or secret. Regression seams: synthetic Neironych request, bot request, hidden-prompt response, absent lineage, no-photo precharge, and older model compatibility. Risk: provider output still cannot guarantee an exact face match, especially from a small collage. Steps: [x] production trace and visual comparison; [x] tools and debugging/QA guidance; [x] API/bot prompt-only routing; [x] two focused test modules; [ ] broader checks/review/PR/CI; [ ] merge SHA deploy/health.

Read-only production lineage check: 59320 is a public Nano Banana 2 image derived from 58419; 58419 is a public Nano Banana 2 image with a nonempty 2678-character author prompt and one original image input. The 59320 saved prompt is a 3865-character derived edit, so using it as the creator recipe would be wrong. The new resolver finds 58419 without returning its prompt to the client. The web feed card previously omitted image-recipe capability entirely; the web and Mini App cards now expose Nano Banana 2.1 availability separately so a derived Nano Banana 2 post offers the correct user-photo capacity when 2.1 is selected. The Nano Banana 2.1 rollback flag now rejects repeats before charge rather than falling back to an author-image edit. Four relevant pytest modules plus web schemas passed after the change, as did Ruff, Python compile, webapp typecheck/build and diff check. Two unrelated pre-existing `test_web_api_contract.py` cases fail when that wider module runs (referral session fake and closed event loop); no gate was weakened. OCR delegate listed eight changed source files; excluded diagnostics and logs are pre-existing untracked files. Review and CI pending.

## 2026-10-14 — feed image face transfer regression

Baseline `6aaed3efa302fe067f0fad5c60c805692170f7d7` on `main`; pre-existing untracked `artflow/data/diagnostics/` is unrelated. Production read-only evidence: task `neironych-image:cdb0608d-967f-58b2-ac17-5326d11bc0ea` is generation 59292, Nano Banana 2.1, source feed generation 59257. Bot log records `feed_photo_recipe_bot ... identity_refs=1`; the generation stored one reader reference, reused the creator prompt exactly, and sent neither the published scene nor creator original photo. Neironych completion log confirms the task ID, though request body logging is deliberately unavailable. Visual check: the uploaded collage shows a red-haired woman; the result resembles the source witch's facial styling more than that reference. User clarified that original-recipe mode is intended; the failure is identity fidelity. An initial attempt to disable recipe mode was reverted before delivery. Outcome: retain original recipe and only reader photos, instruct the provider unambiguously to take face and identity from the reader reference; preserve author prompt secrecy and add no paid request for the incident. Acceptance: API site/Mini App and bot use the same identity instruction; provider payload has one reader photo, no creator original/result; repeat does not duplicate the instruction; quote/launch behavior and protection remain. Migration `040_feed_recipe_identity_policy` adds a single validated instruction row and audit table; authenticated web admin GET/PUT can tune the instruction without redeploy. Price, permissions and secrets remain unchanged. Observability: existing source generation and task IDs trace the path without logging media or prompts. Test seams: core prompt composition, API synthetic transport, bot launch and restore, existing security suite. Steps: [x] tool repos and relevant guidance; [x] read-only production diagnosis and visual check; [ ] RED regression; [ ] code; [ ] local checks/review; [ ] PR/CI/auto-merge/deploy health.

Progress: [x] RED regression; [x] shared recipe identity instruction in API and bot; [x] seven focused identity/security/feed/Nano 2.1 test modules passed; [x] Ruff, Python compile and diff check; [x] OCR delegate review of all three changed source files, plus manual review of docs and tests, with no high-severity finding; [ ] PR/CI/auto-merge/deploy health. Creator prompt is retained server-side. PR #253 initial review found two P1s; the user explicitly chose face guidance for all photo repeats, and an audited DB/admin prompt policy addresses the mutable-prompt concern. Auto-merge was disabled during revision. Offline SQL for migration 040 passed from revision 039; full historical offline upgrade fails at pre-existing migration 003 inspection. OCR also listed two pre-existing untracked diagnostics files, excluded from this change and review.

Revision verification: user explicitly chose identity transfer for **all** photo recipe repeats despite the reviewer concern about non-portrait recipes. Migration 040 seeds the instruction in a database singleton; authenticated admin GET/PUT validates 100–3000 characters, locks the row and audits first and later writes. Quote and launch fetch the same instruction before charge; bot does likewise. v4 lineage stores the instruction and an authenticated digest to replace it on a later repeat. Ten focused Python test modules, Ruff, compileall, Alembic single-revision offline SQL/head and webapp typecheck/build passed before merging current main. OCR delegate listed 11 changed source files (11 reviewed), docs/tests were manually reviewed, with no remaining code finding; initial reviewer P1 on broad role is an explicit user product decision. Main commit d74cf61 (#252) added a related static recipe instruction while this branch was under review. The merge retains its legacy policy unwrapping and improves the database seed for hair and conflicting monochrome descriptions; the shared composer now uses only the database policy. Focused API/bot/admin policy tests passed after conflict resolution; exact-head CI and autodeploy remain pending.

## 2026-10-14 — Seedance repeat API 500 after supplier review gate

Baseline `73501c1885303a404cfb0e81d846f13c01556fc1`, branch `fix/apix-seedance-preflight-charge-20261014`. User report: Mini App exact creator video repeat displayed API 500 and then an indefinitely queued task. Production evidence: generation 59203 belonged to the reported account, was `pending` with 70 charged credits, no provider task ID, no Neironych/KIE submission marker and no callback marker. Earlier refunded generation 58339 has supplier review `needs_admin_resolution`, so the account-scoped provider liability gate is active. The callback registration path checks this gate only after `spend_credits` and `create_generation` have committed. On normal rejection it rolls back the SQLAlchemy session, expiring the ORM user; the generic exception handler then accesses `user.id` before refunding, which reproduces an unhandled 500 and a charged pending row. The original HTTP traceback was unavailable after normal container replacement; this is a code-and-state-supported diagnosis, reproduced with a rollback-expired user test.

Incident action: generation 59203 was verified as pre-submit and refunded through `repo.fail_generation_and_refund` with its missing-task guard. Postcheck: `failed`, exactly one 70-credit `generation_refund` ledger row, balance 173. No provider POST was attempted by the intervention.

User correction during PR #251: an unresolved old supplier review must never prevent a new paid task. Acceptance: new Seedance quote/launch/remix and bot launch/regeneration proceed independently of old review; a single generation still has one durable callback/submission identity and cannot be submitted twice; callback-registration failure after charge atomically fails/refunds only when no submission identity exists; API returns a meaningful status and no expired ORM access. Supplier review 58339 remains unresolved pending provider/finance evidence; customer wallet must not be debited to settle it. No migration or runtime secret/config change. Observability: log generation ID and refund amount without prompt/media/credentials. Test seams: API quote/launch/remix behavior, bot launch, repository callback/submission state, fallback refund, existing provider submission and refund regressions. Steps: [x] production DB/root-cause audit; [x] 59203 refund/postcheck; [x] first patch and 556 focused tests; [x] user correction and removal of account-wide gate from all surfaces and repository; [x] 314 revised focused tests across seven modules, Ruff, compileall and diff check; [x] manual PR diff review, no open high-severity finding; [ ] exact-head CI; [x] PR #251 with native auto-merge enabled; [ ] exact-SHA Production Autodeploy and health. First PR CI run failed because old account gate reached fake bot sessions and a static reliability test still expected the older two-step refund; both causes were removed. The next backend run exposed an older regression test asserting that the account-wide gate blocks a fresh submission; it now checks that the new submission succeeds once while the old supplier review remains open.

## 2026-10-14 — stalled generation incident and customer refunds

### Follow-up after PR #248 auto-merge

Baseline `c76683e7f7346c7ee535c211996c3b9a64310002`, branch `fix/apix-stalled-recovery-review-20261014`. The asynchronous Codex review completed after auto-merge and found three P1 gaps and one P2: image SLA lacked authenticated audited admin configuration; missing-ID KIE callback correlation could be refunded without supplier review; permanently skipped marker rows could starve the fixed expired batch; web-origin missing-ID jobs could receive Telegram notices. User outcome is unchanged: customer refunds stay final, with no extra paid POST. Acceptance: all four findings reproduced with RED tests and fixed; provider review remains durable for callback-correlated KIE tasks; batch drains; admin can change typed SLA without redeploy; exact-head CI, normal auto-merge and deploy health. No direct production balance edit. Migration is additive and applied only by normal production autodeploy. Risks: provider late costs remain supplier review, not customer wallet mutation.

- Follow-up implementation: provider-scoped, typed image SLA persisted in `image_recovery_policies` with actor/change audit in `image_recovery_policy_audit`; authenticated web admin GET/PUT controls it without redeploy. Migration `039_image_recovery_policy` adds both tables and bounds. Missing-ID KIE callbacks keep a virtual task identity and supplier review in the same refund transaction; web-origin callbacks do not queue Telegram notices. Expired batch excludes missing-ID rows carrying submitted paid work, so these rows cannot starve eligible later rows.
- Follow-up verification: 182 focused tests passed across nine modules, including late callback after atomic refund and live SLA override; Ruff and `git diff --check` passed; Alembic head and offline upgrade SQL checked. PR, exact-head CI, review, auto-merge, migration and production health remain pending.
- PR #250 first backend-quality run found one old image-routing test whose fake `session=object()` lacks the new policy read seam. The test now supplies a policy stub; the routing/recovery subset (37 tests) and Ruff passed locally. The exact-head backend gate must rerun after this amendment.
- Codex review of PR #250 found a P2 initial-write audit gap: persisting the same value as the environment bootstrap wrote a database override without actor/audit. Auto-merge was paused before merging. The setter now records actor and audit for first persistence regardless of numerical change; a focused regression test and Ruff pass. Re-enable auto-merge only after the amended exact-head gates pass.

- Baseline `6a4754ed99a79a048f93a045399b81c3bd92df1e`; isolated branch `fix/apix-stalled-generation-recovery-20261014`. Production main checkout had only pre-existing untracked diagnostics.
- User outcome: return credits for all 35 old active jobs identified at 16:00 Moscow time, then prevent known reconciliation gaps from leaving future paid jobs active indefinitely. Acceptance: exactly one refund per incident generation; active old count zero; no second paid provider POST; scheduled reconciliation handles all Nexus image models and missing-ID videos; focused tests and required CI pass.
- Production evidence before repair: 35 active jobs across 20 users, 279.5 recorded spent credits, zero prior generation refunds. Breakdown: 28 Neironych images, 4 Nexus images, 3 Seedance videos lacking provider task IDs. Provider GET: 14 Neironych `not_found`, 11 `reconciliation_required`, 3 `completed` without URL; Nexus 2 completed with URLs and 2 failed. Image scheduler selected only Nano Banana 2.1; Seedance scheduler counted missing IDs but never settled them.
- Authorized incident action completed via `repo.fail_generation_and_refund` using row locks, expected task identity, and a short incident note. Read-only postcheck: 35 `failed` rows, 35 unique `generation_refund` ledger rows, 279.5 credits returned across 20 users; no active job older than 10 minutes. Telegram video notices were persisted for the 3 videos. No paid provider submission or manual SQL balance edit.
- Risks/dependencies: some provider states were ambiguous or completed without recoverable media. Customer refunds are final; late supplier cost must be investigated separately. New policy does not infer free provider failure from 404. No schema migration. Existing pricing/admin model settings remain unchanged. `IMAGE_AUTO_REFUND_SECONDS` is a typed, bounded environment setting (default one hour) for incident recovery; moving the SLA to the authenticated, audited admin control plane remains a follow-up. A provider completion cannot overwrite a refunded final job.
- Observability: incident note in ledger and `refund_applied` marker; scheduler logs provider/state and generation ID without prompt, URL or credentials. Test seams: scheduler selection, expected-ID atomic refund, timeout outcomes, no paid re-submit, and notice behavior.
- Steps: [x] preflight/current-production audit; [x] customer compensation and verification; [x] RED regression tests; [x] minimal reconciliation fix; [x] focused tests (159 passed), Ruff and compile checks; [x] OCR delegate preview/rules plus manual review of all 5 reviewable source files (standard OCR could not use an LLM endpoint); [x] PR #248/required CI/auto-merge to `c76683e7f7346c7ee535c211996c3b9a64310002`; [x] exact-SHA Production Autodeploy run 38571232363 succeeded and public `/api/v1/health` returned HTTP 200.


Baseline: commit `31a91c6`; working tree had no tracked changes at task start.
Date: 2026-09-16.

## Current state
- Photo to prompt exists in `api/photo_prompt_service.py`, `/api/v1/photo-prompt`,
  `/api/web/photo-prompt`, text bot flow, and Mini App/Web services UI.
- Photo to prompt is free and has no `ModelCost` billing row.
- Model costs are database-backed through `model_costs`, seeded in `db/seed.py`,
  and editable through `/admin -> Стоимость моделей`.
- Comet config already exists in `core.config.settings` through
  `COMET_API_KEY`, `COMET_BASE_URL`, assistant model fields, and related
  photo-prompt fallback wiring.
- Video to prompt is implemented through Comet/Qwen3.8-Max for web, Mini App,
  and the text bot. Uploaded source videos use unique temporary public files
  and are removed after the synchronous provider response.
- `docs/agents/AGENT_CHANGELOG.md` is registered but missing from the repo.

## Intended outcome
- Add a user-facing "Видео -> промпт" feature beside "Фото -> промпт".
- Default function cost is 3 credits, controlled by the existing admin model
  cost editor via a `ModelCost` row.
- All applicable surfaces are covered:
  site/web: services UI and web route;
  mini_app: `/api/v1/video-prompt` and services UI;
  telegram_bot: text bot upload flow from the same prompt tools area.

## Acceptance criteria
1. Provider service sends video URL to Comet/Qwen3.8-Max and extracts text.
2. Backend validates file kind/size before provider call.
3. Backend spends the configured credits before provider call and refunds once
   on provider failure.
4. Seed creates `llm.video-prompt` at 3 credits and admin model editor can see it.
5. Web/Mini App UI exposes the feature next to photo prompt.
6. Text bot exposes the feature next to photo prompt and returns the ready prompt.
7. Focused tests cover service payload, endpoint validation/billing/refund, seed,
   and bot/UI wiring where practical.

## No-hardcode / control plane
- `llm.video-prompt` default cost is seeded as 3 credits.
- Runtime cost is read from `model_costs`, so admins can update it without code.
- Provider credentials stay in existing settings; no secrets are added.

## Observability
- Provider success logs provider/model metadata only.
- Provider failure logs user id and error without file body or secrets.
- Credit spend/refund operations are recorded in `credit_ledger` with a short
  source identifier that fits the database column.

## Test seams
- Service tests monkeypatch `httpx.AsyncClient`.
- Route tests monkeypatch provider call, repository cost/spend/refund methods,
  and public file saving.
- Seed test inspects `DEFAULT_MODEL_COSTS`.
- Frontend surface test checks API client and services UI strings.

## Steps
1. [x] Preflight: tool repos updated; relevant skills/instructions read.
2. [x] Repository/photo-prompt/admin-cost audit.
3. [x] Added tests for service payload, file validation, billing/refund,
   temporary-file cleanup, seed/admin wiring, menus, and frontend surfaces.
4. [x] Implemented backend service, routes, billing, refund, and seed.
5. [x] Implemented text bot flow; Bot API download limit is 20 MB, while web
   and Mini App retain the 100 MB product limit.
6. [x] Implemented Web/Mini App UI in the current TS app and legacy/V4 apps.
7. [x] Verification: 14 focused tests passed; Python compilation passed;
   frontend typecheck/build passed; focused Ruff checks passed. The broader
   touched-module run exposed 15 pre-existing failures unrelated to this diff.
8. [x] Open-code-review attempted; external LLM configuration was missing.
   Delegate review then covered 23/23 reviewable files and prompted fixes for
   temporary-file retention, unpaid storage, file-signature validation,
   Telegram's 20 MB download limit, and blocking filesystem I/O.
9. [x] Parity verified for `site`, `mini_app`, and `telegram_bot`.

## Final verification and follow-ups
- No migration is required: startup seed inserts the missing `ModelCost` row.
- No live Comet request was made because no acceptance-test credential/video
  was provided. The provider-specific `video_url` contract remains the main
  rollout risk and should be smoke-tested before production enablement.
- `docs/agents/AGENT_CHANGELOG.md` remains registered but absent.
- Repository-wide tests are not green at baseline; unrelated failures remain
  in older menu/feed/model/video normalization expectations.
- The exact maintained backend PR gate plus the new tests passed locally:
  204 tests. CI was updated to include the new service, bot handler, public-file
  helper, and focused tests in its Ruff/pytest gates.
- Local Playwright could not launch Chromium because the host lacks
  `libatk-1.0.so.0`; GitHub Actions remains the authoritative E2E check.

---

# Execution ledger — video result publishing to feed

Baseline: commit `cad3c5b8`.
Date: 2026-09-20.

## Current state
- Public feed already renders both image and video cards.
- Modern web/Mini App feed publish endpoint already allows publishing own ready image/video media while keeping remix prompts hidden.
- Text-bot video completion UI coupled feed publication to prompt/library visibility, so feed-derived videos lost the `📤 В ленту` action.
- Repository `share_to_feed` also rejected all feed derivatives, so adding the button alone would fail.

## Intended outcome
- Every completed own video can be added to the public feed.
- A video derived from another feed post may be published as new media.
- The source post's prompt remains private and cannot be copied or saved to the user's prompt library through this flow.

## Acceptance criteria
1. Completed video result keyboard includes `📤 В ленту`.
2. Feed-derived video keeps `📤 В ленту` but hides copy-prompt and library actions.
3. Bot callback publishes the user's own video and returns the feed deep link.
4. Repository allows video derivatives while retaining the source guard for images.
5. Legacy Mini App `/generations/{id}/share` follows the same video rule.
6. Feed rendering remains unchanged and supports video.
7. Focused regression tests and CI pass before merge.

## No-hardcode / security
- No model/provider-specific whitelist was added; the rule is based on `GenerationType.video`.
- Ownership, done status, and result URL checks remain enforced server-side.
- Prompt/library protections remain unchanged for hidden source prompts.

## Steps
1. [x] Audited bot result keyboard, KIE/webhook completion, share callback, repository guard, feed renderer, and web/Mini App publish paths.
2. [x] Split feed publish permission from prompt-library/copy permission in result keyboard.
3. [x] Enabled video derivative publication in bot and repository.
4. [x] Added legacy Mini App parity for video `/share`.
5. [x] Added focused regressions for keyboard, bot callback, repository SQL guard, and Mini App route.
6. [x] PR #153 CI: APIX backend-quality, frontend build + Playwright Mini App smoke, Feed Security Contracts, Provider Contract Compliance, Pinterest Backend Contract, and Photo Prompt Integration all passed on the implementation SHA.
7. [ ] Merge / production autodeploy / production smoke.

---

# Execution ledger — per-user unlimited image models

Baseline: commit `9773b96e`.
Date: 2026-09-23.

## Current state
- Image model prices are database-backed through `model_costs` and editable in Telegram `/admin`.
- Image charging existed independently in text-bot image sessions, Midjourney image flows, and Mini App/Web image/remix handlers.
- Early balance checks existed before the final spend in several text-bot image flows.
- Generation failure/refund logic uses `Generation.credits_spent`, so unlimited generations must persist zero charged credits to avoid phantom refunds.
- Video, music and analysis tools have separate billing paths and are out of scope.

## Intended outcome
- Admin can enter a Telegram ID or internal user ID and toggle unlimited access for selected active image models.
- Entitled users can generate with the selected image models even with zero balance.
- Unlimited applies only to the selected image model roots, including their pricing-quality variants.
- All other models and media types retain normal billing.

## Data model and control plane
- New table `user_image_model_unlimited` with unique `(user_id, model_key)`.
- Foreign keys use cascade semantics; admin actor and creation timestamp are recorded.
- Admin callbacks use numeric `model_cost_id` to stay under Telegram callback limits, while persistence stores normalized base `model_key`.
- Only active `GenerationType.image` base rows are selectable in the admin keyboard.
- No user IDs or model allowlists are hardcoded.

## Billing contract
- `charge_image_generation()` is the shared image-only charge boundary.
- Entitled generation: `allowed=True`, `charged_credits=0`, no credit ledger spend.
- Regular generation: existing atomic `spend_credits()` path is preserved.
- Every migrated generation path writes the actual charged amount into `Generation.credits_spent`.
- Existing failure/refund paths therefore refund zero for unlimited work.
- Video/music billing is unchanged.

## Surfaces
- `telegram_bot`: image session, default/advanced image wizard, Nano Banana flows, Midjourney image/imagine/action/blend/describe.
- `mini_app` and `site/web`: primary image generation and image remix/feed-repeat paths share `miniapp_routes` billing.
- Admin: Telegram `/admin -> ♾ Фото-безлимит`.

## Observability
- Entitlement enable/disable/clear logs include user id, normalized model key and admin Telegram id.
- Unlimited billing bypass logs user id, model key and nominal credits without secrets or prompt/media content.

## Verification evidence so far
- TDD schema RED: `UserImageModelUnlimited` missing test failed before implementation.
- Schema test GREEN after model/migration implementation.
- Admin selector RED: missing `bot.keyboards.admin_unlimited` failed before implementation.
- Admin selector GREEN: 2/2.
- Python compile succeeded for all touched Python modules.
- Focused integration run: 35/35 passed, covering Midjourney, admin entry/FSM, repository charge contract, selector contract, schema contract, and zero-credit generation record.
- A broader local `test_image_gen_references.py` run has one pre-existing unrelated signature mismatch (`cb_image_model` test omits current `db_user` argument); the new unlimited node itself passes.
- Local isolated repository tests can hit a pre-existing circular-import collection issue; exact-head GitHub CI remains the authoritative full gate.

## Steps
1. [x] Preflight: repository instructions, local project skills, tool repos and billing/admin architecture audited.
2. [x] Implementation plan written before production changes.
3. [x] RED/GREEN tests for schema and admin selector.
4. [x] Schema, migration and repository entitlement/charge helpers implemented.
5. [x] Telegram admin control plane implemented.
6. [x] Text-bot image billing and early balance checks migrated.
7. [x] Mini App/Web primary image and remix billing migrated.
8. [x] Focused tests added to the maintained PR CI gate.
9. [ ] Diff review and exact-head CI.
10. [ ] Merge, Alembic production upgrade, autodeploy, health and log smoke.

---

# Execution ledger — Seedance 2.5 video-reference transport and preflight

Baseline: commit `b83aac15`.
Date: 2026-09-24.

## Production evidence
- Video references are not being lost. Production runtime recorded Seedance requests with `videos=1`, and KIE task records contain `reference_video_urls` after APIX uploads them to KIE storage.
- Successful example: generation `49967`, KIE task `ea78d8083b86fc88ea153bee7d26b899`, one image + one MOV video reference, provider state `success`.
- Failed edit example: generation `50328`, KIE task `9b51ee472ce0e0a8d14a334d426d40d2`; KIE received all three image refs plus the MP4 video ref, classified the prompt as video editing, and required `aspect_ratio=adaptive` plus `duration=-1`.
- Failed media examples showed missing local preflight: videos longer than 30 seconds and low-pixel media reached the provider before being rejected.

## Root cause
The transport path was correct. The failures came from two separate gaps:
1. Seedance 2.5 reference videos were accepted without provider-specific media validation.
2. Prompts explicitly asking to replace/edit people in the supplied video were still sent with manually selected output ratio/duration, while KIE's edit scenario requires adaptive ratio and automatic duration.

## Fix
- Preserve and regression-test `reference_video_urls` in the final KIE payload.
- Web uploads accept MP4/MOV video refs and ffprobe them before persistence.
- Telegram validates its video metadata before mirroring.
- Runtime validates local video refs before KIE upload.
- Provider-safe limits enforced from live provider behavior: duration 2–30s for references, 4–30s for explicit edit source video, width 300–6000, pixel count 407696–8295044, aspect ratio 0.4–2.5.
- Explicit video-edit prompts with one reference video use KIE-required `aspect_ratio=adaptive` and provider `duration=-1`.
- Billing for a local edit source is calculated from the probed source duration before credits are spent; multiple edit-source videos and unprobeable external edit URLs are rejected before charge to avoid ambiguous/incorrect billing.
- Small local image refs can be safely upscaled without cropping to Seedance's minimum provider dimensions/pixel count.
- Mini App file picker no longer advertises MKV for Seedance reference video.

## Verification
- TDD confirmed the old upload path lacked metadata validation and accepted MKV.
- TDD confirmed the old edit request sent `9:16` instead of `adaptive`.
- Focused Seedance/video suite: 43/43 passed.
- Python compile passed for touched backend/bot modules.
- Ruff passed for touched provider/runtime/bot/test files and import ordering in Mini App routes.
- Provider Contract workflow now explicitly gates the new video-ref payload test and small-image upscaling regression.

## Pending delivery
1. [ ] PR review and exact-head CI.
2. [ ] Merge to main.
3. [ ] Production autodeploy and health/log smoke.


## Follow-up — dedicated Genjutsu create-hub entry

Date: 2026-09-25.
Baseline: `664f6f92baf897d80be304502a54895a23f0bfd6`.
Branch: `feat/genjutsu-create-hub-entry`.

### User outcome
- Telegram create hub gets a full-width `🥷 Genjutsu` shortcut in the location requested by the operator.
- The shortcut opens a dedicated two-choice screen: Motion Transfer or Object Swap.
- Choosing either configured model enters the existing Genjutsu reference → source video → params → prompt flow.
- Regular users only see the entry when Higgsfield credentials are configured.
- Admins can preview the screen before credentials exist, but launch buttons fail closed with a clear provider-not-configured alert.

### Scope / parity
- `telegram_bot`: updated because the request is specifically for this Telegram menu.
- `mini_app`: no change; Genjutsu model flow already exists there.
- `site/web`: no change; Genjutsu model flow already exists there.
- This is a navigation shortcut, not a capability or pricing change.

### Verification
1. [x] Added create-hub contract coverage for the Genjutsu entry.
2. [x] Added handler coverage for configured flow and admin preview fail-closed behavior.
3. [x] Python compilation and focused Ruff checks passed for all touched Python files on an isolated branch checkout.
4. [x] Focused regression tests passed locally: 3/3.
5. [x] Exact-head PR CI passed: APIX CI/CD #941 and Provider Contract Compliance #882.
6. [x] Diff review completed with no unresolved high-severity finding.
7. [ ] Merge / production autodeploy / production smoke.




---

# Execution ledger — Higgsfield Genjutsu integration

Baseline: commit `5399541afeeb530eafded3f2e353518870d5c6e4`.
Date: 2026-09-25.
Branch: `feat/genjutsu-integration`.

## Current state / audit
- APIX video generation is capability-driven: runtime `VideoModel`, `VIDEO_CAPS`, DB-backed `model_costs`, Telegram FSM, Mini App/Web model metadata, provider contract catalog, operation registry, smoke manifest and reconciliation.
- Local APIX uploads are stored under the public upload surface and can be probed with ffprobe through `api.media_gateway`.
- Provider results can be mirrored into APIX storage with SSRF-safe `public_files.mirror_url`.
- No Higgsfield/Genjutsu provider code existed at baseline.

## Verified provider contract
- Motion Transfer endpoint: `higgsfield/genjutsu/motion-transfer/v1.0`.
- Inputs: `prompt`, `video_url`, `image_urls`, `resolution`.
- API-safe surface implemented: source video 1–30 seconds, up to 8 image references, 480p/720p.
- Higgsfield V2 auth: `Authorization: Key KEY_ID:KEY_SECRET`.
- Async lifecycle uses `request_id` and authenticated `GET /requests/{request_id}/status`.
- Object Swap endpoint remains config-backed because current Higgsfield pages have published inconsistent `higgsfield` / `higgsfiled` spelling.

## Intended outcome
- Add Motion Transfer and Object Swap as first-class video models.
- Keep source video + reference images intact on Telegram, Mini App and site/web.
- Measure source-video duration server-side before spend; client duration is UX-only.
- Keep prices editable through existing `model_costs` admin control plane.
- Persist completed provider video to APIX storage rather than treating Higgsfield CDN as canonical.
- Do not trust unsigned provider webhook payloads; use authenticated polling/reconciliation.

## Acceptance criteria
1. Both models appear in text bot and shared Web/Mini App model metadata.
2. Both require one source video and at least one reference image; max 8 refs.
3. Source duration is verified from APIX-owned upload and limited to 1–30 seconds.
4. Resolution supports 480p/720p and price is resolved by DB-backed per-second variants.
5. Provider create returns `request_id`; terminal statuses and failures map into normal APIX finish/refund paths.
6. Completed videos are mirrored to `provider-results`.
7. Provider catalog, operation registry and smoke manifest remain structurally complete.
8. Relevant backend tests, provider contract checks, frontend build and CI pass before merge.

## No-hardcode / control plane
- Credential, base URL, retry policy and both endpoint paths are environment settings.
- Default pricing rows are seeds only; runtime pricing remains `ModelCost` and admin-editable.
- No secrets are committed or logged.

## Observability / failure semantics
- Submit log: model, request_id, reference count, resolution.
- Retry log: method/path/attempt/backoff; credentials and media payloads are excluded.
- Reconciliation is idempotent through existing generation terminal-state checks/refund helpers.
- `failed`, `nsfw`, `canceled/cancelled`, auth/credit/validation errors are terminal failures and use normal refund semantics.
- Missed callbacks are irrelevant to correctness because completion is reconciled through authenticated status polling.

## Progress evidence
1. [x] Repository instructions and relevant backend/Mini App/frontend/release skills reviewed.
2. [x] Official Genjutsu and Higgsfield V2 SDK contracts verified.
3. [x] Dedicated Higgsfield HTTP client and Genjutsu provider adapter added.
4. [x] Dynamic video models, capability metadata, DB pricing seeds and canonical labels added.
5. [x] Mini App/Web validation and authoritative source-duration billing added.
6. [x] Telegram reference-images → source-video workflow added.
7. [x] Provider catalog, operation registry and smoke templates added.
8. [x] Focused regression run: 68/68 passed after correcting one test-only variant-key assumption.
9. [x] Release audit found production has no `HIGGSFIELD_CREDENTIALS`; added a credential feature gate so Genjutsu is hidden from user surfaces until server credentials are configured.
10. [x] Re-verified current official provider pages: Motion Transfer publishes `higgsfield/genjutsu/motion-transfer/v1.0`; Object Swap currently publishes `higgsfiled/genjutsu/object-swap/v1.0`. Both remain env-configurable.
11. [ ] Exact-head provider/backend/frontend/E2E CI after rollout-safety fixes.
12. [ ] Merge/autodeploy, production credential configuration and paid-provider smoke.


## Follow-up — Genjutsu admin pricing control

Date: 2026-09-25.
Branch: `feat/genjutsu-admin-pricing`.

### User outcome
- Telegram `/admin` gets a dedicated `🥷 Genjutsu цены` control.
- Admin can edit Motion Transfer and Object Swap independently for 480p and 720p.
- Values are credits per source-video second.
- 480p updates its base fallback atomically with the explicit 480p variant.
- Runtime source of truth remains `model_costs`; changes apply without redeploy across Telegram, Mini App and site/web.

### Control plane / parity
- Telegram admin: dedicated Genjutsu pricing screen.
- Web admin: existing `/admin/pricing` / `/admin/model-costs/{id}` already exposes the same ModelCost rows; no parallel pricing store is introduced.
- End-user Telegram / Mini App / web resolve prices from the same DB-backed video pricing keys.

### Verification
1. [x] Added dedicated admin pricing regression coverage.
2. [x] Added atomic repository helper for resolution tariff updates.
3. [x] Ruff and Python compilation passed for touched Python files.
4. [x] Focused tests passed: 8/8, including non-finite input rejection and rollback on incomplete tariff rows.
5. [ ] Exact-head CI / review / merge / production smoke.


## Follow-up — Genjutsu provider poll budget (false 10-minute timeouts)

Date: 2026-09-25.
Baseline: `512e86f` (`feat(admin): manage Genjutsu prices (#163)`).

### Incident
- `16:19 UTC` — user 6 (`@Chillcreative`) launched Genjutsu Motion Transfer (#51015, «повтори все четко», 14.7s source, 2 refs, 480p, 240 credits).
- `16:30 UTC` — Telegram bot sent `❌ Ошибка: Время ожидания истекло. Попробуй снова.` and refunded 240 credits.
- Root cause: `bot/handlers/video_gen.py` calls `api/polling.py:poll_until_done` without a timeout, so every provider shared `POLLING_TIMEOUT=600` (10 min). At 16:32 the Higgsfield task (`request_id 243b2eac-ee0f-4e47-9ff9-2ee017db6047`) was still legitimately `in_progress` on the provider side — the render simply outlived the shared budget. Debugging confirmed the failure is not provider- or credential-related; the key is valid (a status probe returns HTTP 200, an invalid key returns HTTP 401).
- Later provider status: `nsfw` — the exact render would have failed anyway, but with the true reason (rejected content) instead of a false timeout.

### Scope / parity
- `telegram_bot`: both launch paths (`_launch_video_generation_from_state`, `_regenerate_video_from_previous`) now start polling through `_start_video_polling`, which forwards `result.provider` so the provider-scoped budget applies.
- `mini_app` / `site`: reconcile (`api/genjutsu_adapter.py` wrapping `miniapp_routes._reconcile_generation_status`) keeps long renders alive via the Genjutsu stale guard instead of failing them at the shared 20-minute mark.
- Web frontend has no own generation timeout (checked `webapp/src`); it follows backend status.

### Change
- `core/config.py`: `HIGGSFIELD_POLL_INTERVAL_SECONDS=5.0`, `HIGGSFIELD_POLL_TIMEOUT_SECONDS=1800` (30 min), `HIGGSFIELD_STALE_TIMEOUT_SECONDS=2400` (40 min, strictly above the poll timeout so reconcile never refunds a task that is still being polled).
- `api/polling.py`: `poll_budget(provider)` resolves per-provider (interval, timeout) from settings at call time with clamps; `poll_until_done(..., interval=None, timeout=None, provider=None)` honors explicit values and adds a timeout warning log with task/provider/duration context.
- `bot/handlers/video_gen.py`: one helper `_start_video_polling`; 4 call sites use it, passing `provider=result.provider`.
- `api/genjutsu_adapter.py`: `genjutsu_stale_timeout(routes)` = `max(STALE_GENERATION_TIMEOUT, HIGGSFIELD_STALE_TIMEOUT_SECONDS)`.
- `.env.example`, `README.md`: documented the new settings.

### No-hardcode / control plane
- All budgets are env settings with in-code defaults; admin can tune intervals/timeouts without redeploy-code changes (only a container restart to pick up `.env`).

### Observability / failure semantics
- Polling timeouts log `task/provider/timeout/interval` before failing.
- Terminal provider failures (`failed`, `nsfw`, `cancelled/canceled`, auth/credit/validation) keep existing refund semantics.
- The previously failed generation #51015 stays failed+refunded (terminal provider state `nsfw`); no un-billing recovery is possible or needed — the user just retries.

### Verification
1. [x] Focused tests: `tests/test_genjutsu_integration.py` + `tests/test_video_gen.py` → 54 passed (5 new: provider budget map, stale-guard ordering, reconcile keeps 25-min render alive, reconcile refunds 45-min render with `reconcile:higgsfield_timeout`, bot forwards provider into polling).
2. [x] Runtime wiring check: `poll_budget("higgsfield") == (5.0, 1800)` on real settings; `poll_until_done(provider="higgsfield")` provably routes through `poll_budget("higgsfield")`.
3. [x] Ruff clean on all touched files (repo baseline list included).
4. [x] Full-suite comparison vs pristine HEAD worktree: failure sets identical except one order-dependent rate-limit test that failed in the pristine run and passed in the fixed tree (flake; all 43 remaining failures are pre-existing at HEAD, unrelated: image caps, veo, feed).
5. [x] Production container rebuild/recreate + health + live Genjutsu budget verification.
6. [ ] Commit/push (needs operator decision: push to `main` triggers CI autodeploy).

## Follow-up — Suno music generation reconciliation

Date: 2026-09-25. Baseline: `541dd6e59c48df1d2af1b910aa4dfcd443264616`.

### Incident and outcome
- Three Suno v5.5 music generations (#40721, #40719, #37933) remained active for 28–41 days after missed KIE webhooks. Operator polled KIE `jobs/recordInfo`, found terminal `fail` with `413 This audio matches an existing recording in our catalog`, and manually failed/refunded them (30 credits total).
- Ensure active Suno music generations can finish or fail from authenticated KIE polling without a callback. Terminal failure must use the atomic, idempotent `fail_generation_and_refund`; nonterminal/provider transport errors must not be treated as content failures.

### Current state and scope
- `scripts/reconcile_stuck_generations.py` already scans active generations, but `api/miniapp_routes.py:_reconcile_generation_status` returns unchanged for music. User-triggered history reconciliation uses the same function. Webhook has separate Suno result parsing and refund handling.
- `site`, `mini_app`, `telegram_bot`: all use the same generation record and webhook; no surface-specific text, price, or parameter change is intended. Check status behavior on all three.
- No schema, migration, permission, or pricing changes. KIE credentials and finite retry policy already live in the existing client. Provider response fields are verified from current client/webhook code and the incident report.

### Plan and verification
1. [x] Red regression tests reproduced terminal failure and successful audio staying unprocessed; later tests cover in-progress, poll error, ambiguous response, and final-state no-op.
2. [x] Music polling uses authenticated KIE status and Suno record-info, with an in-process periodic scan. Existing repo transitions handle completion and refunds; refund row refreshes under lock to honor concurrent webhooks.
3. [x] Focused tests: 19 passed (`test_music_reconciliation.py`, `test_music_webhook.py`, `test_generation_refund.py`, web stale-task test). Ruff passed for new scheduler/config/main/repository/tests and import order in the touched API module; Python compilation and `git diff --check` passed. Open review checked provider ambiguity, transient errors, refund race, scheduler lifecycle, and shared surface state. CI exists but cannot verify an uncommitted working tree; the broader local `test_webapp_routes.py` run has 13 unrelated failures in feed, image caps, text, and pricing expectations. Full Ruff on `miniapp_routes.py` reports pre-existing `_anonymous_user` F821 at line 2027.

### Observability and risks
- Record generation/task/model and provider state/error without payloads or credentials. Refund only on terminal KIE failure and timeout after a valid nonterminal response. Poll errors and malformed/ambiguous responses remain active for later retry. Scheduler runs in the single-worker FastAPI container; it must be deployed to become active.
- No migration or admin change. Interval/minimum age are validated operational settings in `.env.example`; existing price and model configuration is unchanged. Site and Mini App read the same backend status; the text bot receives a webhook notification when one arrives, while scheduler recovery currently updates shared DB state without a proactive bot message. Existing user-owned `nginx.conf` changes were left untouched.

## Follow-up — retire APIX-hosted HappyFox reverse proxy

Date: 2026-09-25. Baseline: `c84a9515208991df5fce52934558c8a7f4c859e3`.

### Outcome and current state
- HappyFox has moved to its own server. Remove the obsolete reverse proxy from APIX so the APIX Nginx container no longer depends on the Fox Docker network or presents the HappyFox TLS/webhook relay.
- `nginx.conf` had a `happyfox_backend` upstream, a `/happyfox/telegram/webhook` relay, `api.happy-fox.online` HTTP/TLS hosts, and HappyFox-backed paths under `tanyapp.chillcreative.ru` and `alena.xn--e1aikcel5c5a.online`. `docker-compose.yml` attaches Nginx to the external `foxgen_backend` network, which is also needed for the separate `banano-miniapp` frontend. No application DB/schema or auth change is involved.
- Two pre-existing uncommitted IP edits in `nginx.conf` and an untracked Nginx backup are present. Backups were copied outside the repository before editing. Scope of Tanya/Alena host removal is being confirmed because those hostnames differ from the HappyFox domain.

### Acceptance and verification plan
1. [x] Remove HappyFox proxy paths, host blocks, and upstream while preserving the separate Banano frontend and its required Compose network. The Tanya/Alena virtual hosts remain, but no longer route APIs/webhooks to HappyFox.
2. [x] Move the untracked Nginx backup out of the workspace; ensure only intended project changes appear in source control.
3. [x] `docker compose config --quiet`, `docker compose exec -T nginx nginx -t`, `git diff --check`, and a scan for stale HappyFox upstream/domain/relay references passed. Diff review confirms other virtual hosts and Banano frontend routes remain. Production certificates, DNS, and containers were not deleted.

### Risks and rollout
- Removing the relay stops HappyFox traffic on the APIX host; user reports HappyFox has moved and no longer needs it. Keep unrelated model `HappyHorse` and Banano frontend routes intact. Because Banano still uses the `foxgen_backend` Docker network, that external network remains in Compose. Production config changes take effect only after deployment/reload; no prices, admin settings, or migrations.

## Follow-up — Genjutsu face identity investigation

Date: 2026-09-26. Baseline: `5e4a9b66160c0d64eaec09d15f81911eaaaea08f`.

### State and acceptance
- User requires the face from photo references to appear in the output video. Recent bot Object Swap generation #51189 completed with both photo and source video in persisted inputs, but output kept the source face while adopting the reference hair color.
- Existing bot → video service → Higgsfield adapter forwards `image_urls`, `video_url`, prompt, and resolution according to the published Genjutsu API contract. The reference is a single collage containing multiple views. A 29.2-second source produced a 480p output.
- Read-only comparison found prior successful KIE Seedance 2.5 generations for the same user with the exact same reference image and a different source video (#50728/#50729/#50732); their prompts explicitly request replacement of the person/face. The recent Genjutsu generations used Object Swap with the same image, a second video, 480p, and explicit face-replacement prompts. This rules out a missing prompt or missing image transport as the primary defect; neither provider's completed status proves face fidelity.
- Read-only contact sheets from local result files for Seedance #50732 and Genjutsu #51189 (same reference and visually similar source scene) show red hair transfer in both outputs. At the clearest sampled facial frame, neither is sufficient visual evidence of the reference person's facial identity. No new provider task was submitted for this comparison; temporary sheets stayed under `/tmp`.
- Official Higgsfield Genjutsu documentation explicitly supports recasting characters from photo references; the user's stated goal is within its advertised scope. The completed Object Swap result is therefore a quality failure of this input/workflow, not proof that Genjutsu lacks face replacement. Higgsfield's separate consumer Video Face Swap has no documented route found in the API catalog. The MCP endpoint requires OAuth and is not connected here.
- The user has only the customer's API key, not account sign-in. Higgsfield documents MCP as account/OAuth based and separate from the API; the API key cannot authenticate that connector. The official API also publishes Seedance 2.5 Video Edit (`bytedance/seedance-2.5/video-edit`) with `video_url` and optional `image_urls`; this is a possible separately metered workflow, not the route the bot currently calls. APIX already has a separate KIE Seedance 2.5 edit path: explicit edit prompt + one reference video + image references, adaptive aspect ratio, duration `-1`, source-duration billing. This existing path can be reused for an authorized comparison, but has not been visually proven on this identity-transfer case.
- Acceptance: establish by a short controlled render whether a single clear portrait and Motion Transfer provide materially better facial identity than the existing Object Swap result; only then choose a safe product change. Do not claim fidelity without visual evidence.

### Dependencies, controls, and test seams
- No migration or admin change is currently planned. Provider credentials/endpoints and DB pricing remain the existing control plane. Any new model would need typed provider contract, admin pricing, all three user surfaces, billing/refund, and audit coverage.
- Paid provider calls must be bounded to a short clip and logged by request ID without media URLs or credentials. Existing `tests/test_genjutsu_integration.py` and `tests/test_video_gen.py` cover transport; a qualitative identity check needs real output inspection.
- Site, Mini App, and text bot share the Genjutsu adapter; any model/UX change must be checked across all three.
- Diagnostic derivatives were removed from the public upload directory after both provider tasks terminated; original user uploads were preserved.

### Steps
1. [x] Audited current runtime generation, provider contract, code path, tests, pricing, and official API/MCP documentation.
2. [x] Prepared a 1.97-second source clip and a single frontal portrait crop from the existing test assets; both public URLs returned HTTP 200 with expected media types.
3. [x] The 2-second Motion Transfer diagnostic `ea4e2909-d304-458a-bde4-4d4ab200f118` failed with the provider's explicit minimum-4-second error. A 4.17-second follow-up `f6447b11-5e56-4b83-a9d5-b2300239efa2` was accepted but ended `nsfw`; no output video exists to compare. No further reruns on this source are planned.
4. [x] Red tests reproduced the accepted-too-short bug in server duration probing and Telegram upload; the server, bot, and shared site/Mini App UX now enforce/show 4–30 seconds before billing. Product face-fidelity changes remain dependent on an accessible, documented provider face-swap API or a successful allowed evaluation of a suitable model. No identity guarantee has been added to the UI.
5. [x] Focused Genjutsu/bot tests: 56 passed. Ruff, Python compilation, `git diff --check`, webapp TypeScript/build, and the provider-contract inventory check passed. OCR automated review remained unavailable due to provider HTTP 402; manual diff review found no high-severity issue. CI for this uncommitted tree is unavailable.
6. [ ] Determine why Genjutsu character recasting fails on the user's original collage/30-second/480p case; compare an allowed short clip with a single clear portrait and explicit character-replacement prompt. A Motion Transfer test on the existing source was rejected by provider moderation, so use only a permitted independent sample rather than retrying that source through another route.
7. [ ] If Genjutsu remains inadequate, evaluate the already integrated KIE Seedance 2.5 video-edit route on a permitted independent sample before recommending it for this use case. A separate direct Higgsfield Seedance route would require a provider contract, per-token pricing/admin settings, bot/site/Mini App parity, and visual acceptance.

## Follow-up — text bot top-up entry on main menu

Date: 2026-09-26. Baseline: `98d96bb`; local `main` is one commit ahead of `origin/main`, working tree clean. User requested to push to `main` and change the text bot's main button from balance to top-up.

- Scope: Telegram text bot only, as explicitly requested. Site and Mini App payment entrypoints are separate screens and need no change. All three bot home keyboard builders exposed the old balance callback, though `bot/keyboards/main.py` currently has no callers; `bot/handlers/payment.py` already handles `menu:topup` and loads active price plans.
- Acceptance: the Russian/English home menu and legacy builder offer a top-up button that opens the existing top-up flow. The balance details screen remains accessible through its existing callback for other callers. No schema, auth, pricing, integration, or admin change; no new observability needed for a static navigation change.
- Plan: (1) add/adjust contract assertions and observe red; (2) change both home builders and observe green; (3) run focused and required checks, review diff, commit and push the branch; (4) inspect CI for the exact commit and report status.
- Progress: red tests confirmed the old callback/labels in all three builders. Updated active Russian/English home, legacy-compatible builder, and unused older builder to `menu:topup`. Focused menu and balance tests: 25 passed. Maintained CI pytest gate: 260 passed; maintained Ruff gate, provider inventory, Python compilation, webapp build, and `git diff --check` passed. The broader local pytest collection still has 42 failures outside the changed menu contract, largely stale tests; this repository's GitHub CI intentionally runs a maintained subset. Automated OCR review failed before any analysis with provider HTTP 402; manual diff review found no high-severity issue. No DB migration or config/admin change.

6. [ ] Merge/deploy only after green review; production Seedance routing remains unchanged.

## Follow-up — Higgsfield Seedance 2.5 Video Edit identity lab

Date: 2026-09-26.
Baseline: `8f3aa98d4f2b1a8397d4b87ac5d39a6d3b156b9e`.
Branch: `feat/higgsfield-seedance25-edit-lab`.

### Evidence / root cause
- Production KIE Seedance 2.5 reference transport is intact: completed edit jobs persisted both image and video references, including #51012 with an explicit character/face replacement prompt.
- Visual evidence from prior comparisons showed appearance traits transferring more reliably than facial identity. This is therefore not a missing-reference transport bug.
- Mesh/noise/style transforms intended to evade provider safety detection are out of scope. The evaluation uses ordinary permitted reference media only.

### Provider contract under evaluation
- Higgsfield endpoint: `bytedance/seedance-2.5/video-edit`.
- Required: `prompt`, `video_url`.
- Optional published controls used by the lab: up to 30 `image_urls`, up to 10 `video_urls`, up to 10 `audio_urls`, `resolution` 480p/720p, `bitrate_mode` standard/high, `generate_audio`.
- The lab reuses existing server-side Higgsfield Key auth and authenticated status polling.
- No production model key, user pricing row, routing rule, or APIX billing path is changed.

### Intended outcome
- Add an admin-only Telegram lab entry under the existing Test Lab.
- Default to 720p/high bitrate and an identity-preservation prompt.
- Require one source video and at least one identity photo before a paid test.
- Let admins upload separate identity images (front portrait first, then optional extra angles), plus optional extra video/audio references.
- Provider result is polled through the existing Higgsfield budget and mirrored into APIX result storage.
- APIX user credits are never charged by this lab; only Higgsfield provider balance is consumed.

### TDD / verification
1. [x] RED contract added to maintained CI.
2. [x] Exact-head RED observed: 4 expected failures for missing adapter, missing selector entry and missing admin router.
3. [x] Minimal provider payload adapter and admin lab flow implemented.
4. [ ] Exact-head GREEN CI.
5. [ ] Open code review.
6. [ ] Merge/deploy only after green review; production Seedance routing remains unchanged.

## Follow-up — promptless Genjutsu diagnostic and face-swap path

Date: 2026-09-26. Baseline: `8f3aa98` (`main`, clean). User explicitly requests resubmitting the latest Higgsfield task without a prompt and implementing video face swap.

- Existing state: Genjutsu Object Swap #51189 completed using one multi-view collage and a source video; face identity remained unreliable. The adapter currently rejects an empty prompt before calling Higgsfield. The live Higgsfield API key is available server-side, while the account/OAuth-backed MCP is not. Earlier Motion Transfer diagnostic on a short derivative was rejected by provider moderation; do not retry that mode/source. A separate KIE Seedance 2.5 edit path already exists but prior same-reference outputs did not demonstrate identity preservation.
- Outcome/acceptance: submit one exact-media Object Swap comparison with no user prompt, record request ID/status and inspect output if completed. For product work, identify an official usable API contract and visually verify identity transfer before exposing a named face-swap operation. Preserve ownership, billing/refund, admin price configuration and parity across site, Mini App, and Telegram bot. No private media URLs or credentials in logs/commits.
- Plan: (1) verify official prompt optionality and existing task inputs; (2) submit the single authorized comparison through the authenticated Higgsfield client and poll to a terminal state; (3) inventory face-swap provider API and current application seams; (4) implement only a verified route with red/green tests and all user surfaces; (5) run relevant checks, review, and report deployment status.
- Diagnostic result: a direct Object Swap request with the exact saved photo/video inputs and no `prompt` field was accepted as Higgsfield task `86652201-fe36-4396-be8d-6815dd959a1c`, then failed immediately: API credit balance too low. No output exists to inspect. No further paid task was submitted.
- Seedance 2.5 audit: production generation #51012 contained one photo and one source video, an explicit replacement prompt, `adaptive` aspect ratio, and source-duration editing. The bot and KIE adapter forwarded both media references. The observed problem is therefore identity fidelity, not loss of the photo in transport. KIE's published multimodal reference contract offers no face-identity guarantee; treating it as an exact face swap would mislabel the product. User confirmed it takes only broad appearance from photos.
- Implemented promptless Genjutsu transport across shared API, site/Mini App, and text bot: blank prompt omits the provider field; non-Genjutsu video models still reject blank prompts; bot accepts `-` and explains it. Focused regression tests and web build pass. Dedicated Face Swap remains blocked by an accessible, documented, visually verified provider route; Higgsfield has insufficient API balance, and the available KIE Seedance route demonstrably lacks exact facial fidelity. No new model or billing was exposed.
- Verification: 83 focused Genjutsu, video bot, Seedance runtime/reference tests passed; webapp TypeScript and Vite build passed; Python compilation and focused Ruff passed; `git diff --check` passed. Repository-wide pytest remains red on unrelated existing tests (including legacy V4 entrypoint assertions and coroutine mocks); the changed-route-specific failure inspected is an outdated mock returning a coroutine for active-generation count. Full Ruff for `miniapp_routes.py` reports the pre-existing `_anonymous_user` undefined reference, present at baseline. CI for this uncommitted change was not run. No commit, push, or deploy yet.

## Follow-up — payment button advertises rails, not the acquirer

Date: 2026-09-26. Baseline: `a587206` (`main`, clean). Branch: `fix/payment-button-card-sbp-20260926`.

- Problem: the RUB payment method button named the acquirer (`💳 T-Bank / СБП` in the bot, `T-Bank / банковская карта` in the Mini App, `💳 Т-Банк` on the legacy site). User report: people read the brand name as "payment is only possible through T-Bank" and abandon checkout.
- Scope: user-visible payment copy only, in RU and EN. The acquirer stays the processing provider — no provider, routing, pricing, billing, webhook, or feature-flag change. `bot/legal_offer.py` bank details (`АО «ТБанк»`, the merchant's own bank) are legally required and intentionally unchanged, as are internal logs/identifiers and the `tbank` provider key.
- Reuse audit: the RUB acquirer is already exposed as rails — `topup_tbank_desc` and `rub_methods_kb` already offered "картой или через СБП". This change only removes the brand name from the surfaces that still showed it, so no new affordance is introduced.
- No hardcode note: payment-method copy remains in the existing i18n/keyboard/component surfaces with the existing pattern. Moving these labels to an admin-editable control plane is a larger, separate change and was not requested; `api/web/billing.py` labels stay the single API-side source consumed by the site/Mini App.
- Plan: (1) locate every user-visible acquirer mention with a repo-wide search; (2) update bot keyboards, i18n (RU/EN), bot payment screens, API label, and both frontend payment surfaces to `Карта | СБП` / `Card | SBP`; (3) add regression tests asserting the copy advertises rails and no acquirer brand; (4) run the maintained CI subset, Ruff, and the webapp build; (5) commit, push, and open a PR since `main` is protected.
- Steps: 1. [x] Located all mentions — bot keyboard (2), i18n RU+EN (4), bot payment screens (2), API label (1), Mini App balance sheet (1), legacy site (1). 2. [x] Applied the copy change on all ten surfaces; the RUB button now reads `💳 Карта | СБП` (RU) and `💳 Card | SBP` (EN). 3. [x] Added four regression tests in `tests/test_plan_payment_method_choice.py` (bot buttons RU/EN, i18n copy, API label, frontend sources) and updated the API label expectation in `tests/test_web_api_contract.py`.
- Verification: maintained CI pytest subset — 270 passed. Payment-focused sweep (`test_plan_payment_method_choice`, `test_stars_payment`, `test_tribute`, `test_payment_webhooks`, `test_apix_legacy_concept_runtime`, `test_web_generation_parity`, `test_public_offer`) — 53 passed. Ruff on changed files clean except the pre-existing `bot/i18n.py` W292 (no trailing newline at baseline; file is outside the maintained Ruff list). `npm run build` (tsc + Vite) passed. `git diff --check` clean. Pre-existing unrelated red: `tests/test_web_api_contract.py` contact-auth rate-limit tests fail identically with the change stashed.
- Follow-up: `webapp/src/components/balance-sheet.tsx` also labels Lava as `СБП / Lava`, which now overlaps the RUB method's `Карта | СБП`; consider disambiguating copy if both providers are enabled for the same user.

### Follow-up — public landing payment button parity

Date: 2026-09-26. Baseline: `63d9334` (`main`, clean). Branch: `fix/landing-payment-label-card-sbp-20260926`.

- Gap found while verifying the deployed release: the production marketing site (`/`) is served from `artflow/landing/`, not the Vite bundle. `landing/js/prototype-premium.js` keeps its own payment-method label map and renders the provider buttons from it, so the merged bot/Mini App change did not cover this surface.
- Reuse audit: `/billing/payment-methods` returns provider keys only, so the landing fallback map is what decides the visible button text. The landing map already said `Карта` (no acquirer brand), so the original complaint was not reproducible there, but the wording did not match the requested `Карта | СБП`.
- Steps: 1. [x] Changed the landing label map entry to `tbank: "Карта | СБП"`. 2. [x] Bumped the cache-busting query on all nine `landing/*.html` pages from `v=20260907_dual_prices` to `v=20260926_card_sbp_label`, otherwise returning visitors keep the cached script. 3. [x] Updated `tests/test_web_generation_parity.py` to assert the new cache-bust token and extended the CI-covered regression test to cover the landing source.
- Verification: maintained CI pytest subset plus `test_web_generation_parity` — green. `node --check landing/js/prototype-premium.js` passed. Ruff clean; `git diff --check` clean.
- Deployment: PR #171 merged to `main` (merge commit `827001086a71463617b62ab95679cd5ce1f5d3ee`).
  - Production Autodeploy workflow ran and succeeded (run `36238352403`).
  - Public live verification confirmed on `https://apixbotai.com/`:
    - Cache-busting script tag served: `prototype-premium.js?v=20260926_card_sbp_label`.
    - Landing JS label verified live: `tbank: "Карта | СБП"`.
    - Mini App assets bundle verified live (`/assets/index-CRzVm_CW.js`): contains `Карта | СБП` and subtitle `Оплата в рублях`.
    - API landing endpoint verified live (`/api/web/landing`): `[{'key': 'tbank', 'provider': 'tbank', 'label': 'Карта | СБП', 'status': 'enabled'}, ...]`.
    - Health endpoint verified live: HTTP 200 (`https://apixbotai.com/api/v1/health`).


---

# Execution ledger — Seedance 2.5 Identity Transfer preset

Date: 2026-09-26.
Baseline: `0b8170e61da7b113692e94a39018ace541c72d3b`.
Branch: `feat/seedance25-identity-transfer`.

## Production evidence before implementation
- KIE Seedance 2.5 receives both image and video references correctly; transport was already proven in production.
- A controlled one-image/one-video edit using an unstructured replacement prompt mostly transferred appearance traits such as hair color but did not preserve facial identity well enough.
- Re-running the same media with explicit role separation materially improved the result in operator review: `@Image1` as the identity/appearance authority and `@Video1` only for motion, camera, timing, lighting and scene.
- A second A/B run with three photos of the same person was rated successful by the operator. `@Image1` remained the primary identity anchor while `@Image2` and `@Image3` supported head-angle consistency.
- No adversarial mesh/noise/safety-evasion technique is part of this feature.

## Intended outcome
- Add a first-class Seedance 2.5 preset named `Замена персонажа` without creating a fake provider model.
- Keep the normal Seedance 2.5 multimodal product unchanged.
- Identity preset accepts 1–3 photos of the same person and exactly one source video.
- Backend, not user-written prompt wording, assigns reference roles deterministically:
  - `@Image1`: primary identity anchor;
  - `@Image2..3`: same-person identity support;
  - `@Video1`: motion/performance/camera/timing/background/lighting only.
- Identity mode always uses source-video edit semantics: adaptive frame geometry, automatic provider duration, audio generation off.
- User can choose `480p` or `720p`; the selected resolution is preserved through pricing and the KIE payload.

## Surfaces
- `telegram_bot`: dedicated `🎭 Замена персонажа` mode inside Seedance 2.5, 1–3 photo collection, source-video step, then 480p/720p choice.
- `mini_app`: Seedance panel exposes the identity preset and validates 1–3 photos + exactly one source video before request.
- `site/web`: Seedance Studio exposes the same preset and validation.
- All three surfaces use the same backend provider contract and control token.

## Test / safety contract
- RED was observed at exact test commit `5c0180b91e46086722f2bda10bc636ce9026e327`: 12/12 new identity tests failed before implementation.
- GREEN focused run after implementation: 72/72 Seedance/video tests passed.
- Ruff passed for the touched Seedance runtime/adapter, Telegram video handler and new identity test.
- Python compileall passed for `api` and `bot`.
- Mini App TypeScript typecheck and production Vite build passed.
- A broader legacy keyboard/UI test file still has pre-existing assertions unrelated to this diff; these are not introduced by Identity Transfer.

## Control plane / product constraints
- Pricing remains database-backed by the existing Seedance resolution variants; no new hardcoded mutable price is introduced.
- The role prompt is a provider-specific technical contract required for deterministic multimodal semantics, not mutable marketing copy.
- The preset does not promise exact biometric identity preservation; UI copy describes reference roles and recommended input quality.
- No customer media or paid provider job is used by automated tests.


## Review follow-up
- Open review found one provider-boundary edge case: the public Seedance 2.5 input allows a 30,000-character user prompt, but Identity Transfer prepends deterministic role instructions. Without a second check, the final provider prompt could exceed KIE's 30,000-character contract.
- TDD RED: commit `aaf5a6252ce9465c31c6190e3be1baddaf39cf95` added a regression test and CI failed exactly because the expanded prompt did not raise.
- Fix: `build_identity_transfer_prompt` now validates the fully expanded provider prompt against the existing Seedance 2.5 hard limit and raises before provider submission instead of sending an invalid payload.
- The feature uses project skills `systematic-debugging`, `test-driven-development`, `requesting-code-review`, `verification-before-completion`, and `finishing-a-development-branch`; external scan also applied WondelAI clean-code/testing principles and Anthropic webapp-testing guidance. No relevant implementation skill was found in `Bambale0/claw`.


---

# Execution ledger — Personalized trend repeat fields

Date: 2026-09-26.
Baseline at implementation start: `3a174db2de8b774203bc7b6732c6f535c1cb7bfb`.
Branch: `feat/trend-personalization-fields`.
PR: #175.

## User outcome
- Trend authors can declare up to six safe user-editable values for repeat runs.
- Initial presets include `Возраст`, `Имя`, `Надпись`, `Дата`, `Число`, and `Одежда`; admins may add a custom short label.
- The repeat sheet shows only those declared values plus the user's reference photo. The canonical prompt remains server-owned and hidden.
- Values are validated server-side, substituted into matching `{{Field}}` tokens when present, and also appended as explicit priority overrides so existing trends can add fields without rewriting their whole hidden prompt.
- Numeric fields reject non-numeric input; undeclared keys are rejected; explicit empty field configuration disables legacy placeholder auto-discovery.
- Telegram delegates a personalized trend to the same Mini App repeat sheet instead of exposing or duplicating prompt logic.

## Tanyapi reuse audit
- Inspected the live tanyapi worktrees before implementation:
  - `/root/ksu-personalized-trend-fields`, commit `ab808e5` (`feat(trends): add personalized template fields`);
  - `/root/ksu-trend-edit-fields`, commit `42f0e6150b50` (`fix(trends): edit fields on existing templates`).
- Reused the product contract, not copied provider/business implementation: public schema + private prompt, admin-configured fields, server-side rendering/validation, and editable existing templates.

## TDD / review findings
- Existing branch work first stored the field schema inside `UserPrompt.tags`. Review found this is unsafe in APIX because `db.prompt_repository._normalize_tags` lowercases and truncates each tag to 32 characters.
- Regression RED observed at exact commit `4b19d542e81be7c4677e7ecc6cd8efd1229396f7`: CI failed `test_explicit_user_fields_survive_repository_tag_normalization` after the encoded schema was lowercased/truncated.
- Fix: explicit trend field configuration is now a first-class nullable JSON column `user_prompts.trend_user_fields` (migration `035_trend_user_fields`).
  - `NULL` preserves legacy `{{Field}}` auto-discovery for old prompts;
  - `[]` explicitly disables personalization;
  - a populated list stores the normalized admin schema without tag normalization/truncation.
- Trend create/update APIs accept `user_fields` explicitly; a compatibility read from legacy `settings.user_fields` is retained during the transition.
- The run API only accepts `user_values`; the browser never receives or submits the hidden prompt.

## Surfaces
- Mini App: personalized repeat fields are shown before launch; upload no longer auto-runs when fields are configured.
- Trend admin in Mini App: fields can be configured on new trends and changed on existing cards via `⚙ Поля при повторе`.
- Telegram: personalized image/video trends open the canonical Mini App editor.
- Marketing landing has no independent trend runner, so there is no duplicate personalization implementation there.

## Skills
Applied project skills: `systematic-debugging`, `test-driven-development`, `requesting-code-review`, `verification-before-completion`, `finishing-a-development-branch`.


## 2026-09-27 — Telegram navigation repair

Baseline `8a9bbae789617da0731fd11c82c2d37cbc4980ef`. Evidence, acceptance, affected surfaces, review, checks and rollout notes: [NAVIGATION_DEBUG_20260927.md](NAVIGATION_DEBUG_20260927.md).

Explicit contextual video navigation and scenario selection; shared abandoned-FSM cleanup; image/photo/music return paths; task-owned Midjourney results and buttons. 196 focused checks pass; full suite 1370 pass / 42 pre-existing failures, same identities as pristine baseline. Changed Python files pass Ruff and compilation. Independent review blockers addressed. No schema/config/pricing changes. Production rollout verification will be appended after container startup.

Production verification: deployed code `24fabd0740d0fa9a2303a156a18b5f5dedff93e3`, image `sha256:956e56c02d5928dc3b19fae84022844b3d882582a2c0d72d99966b0842e92385`. Startup complete, /health 200, 31/31 Python hashes match reviewed source, zero restarts or startup error markers. Schema remains 035_trend_user_fields. Source/image backup retained at `/root/artflow-navigation-backup-20260927`; branch not pushed.

## 2026-09-27 — Genjutsu face / clothing replacement

Baseline: `db0eae5e57623614f740915b7f997bce21631b1b`; branch `feat/genjutsu-seedance-face-clothing`. User scope is explicitly Telegram Genjutsu, independent of Trends. Site/mini_app retain existing Seedance/Identity Transfer UX; common provider boundary gets regression coverage, no new web entry requested.

1. [done] Instruction/skill preflight and runtime audit. Reused `core/seedance_repeat_overrides`, `api/seedance25_identity`, `_launch_video_generation_from_state`, `seedance25_edit_billing_duration`, ModelCost resolution tariffs, mirror_telegram_file, existing refund repository. No migration/config/price changes planned.
2. [done] RED tests for reference ordering, identity/clothing collision, initial face replacement wording, actual `generate_video`→`kieai_client.create_task` payload, missing source video, Genjutsu entry. Expected baseline failures: clothing treated as identity with stale control token; fourth ref rejected; missing video accepted in content edit; no entry button.
3. [done] Shared strict role plan/prompt and explicit provider-boundary edit metadata; standalone Genjutsu FSM reusing paid launch infrastructure. Confirmed source duration before price/charge; preflight prompt length and upload validation. Persist versioned flow, roles, refs, clothing/number/resolution for repeat.
4. [done] Bot/repeat/billing/refund regressions, independent open review, hosted CI, native auto-merge, automatic production deploy and read-only production verification complete; exact evidence below.

Audit: actual 2.5 request is video_runtime_fixes._seedance_generate, installed after the older adapter wrapper. Existing identity token turns all image refs into identities. Existing repeat helper dedupes before aligning roles (can turn clothing into identity); conflicting identity/clothing URL is ambiguous. New metadata must dominate old identity tokens at provider boundary; reference preparation must not silently lose/reorder roles. Generic launch owns spend→generation→task→poll/webhook and idempotent refund. Existing repeat roles persistence is narrow and must retain new overrides explicitly.

Architecture: dedicated GenjutsuReplaceFSM and handler; validated shared role plan and content-edit prompt; explicit Seedance content-edit metadata passed through existing launch to runtime boundary. No new provider or fake model. Initial editor uses source video as scene authority; identity photos only face identity; clothing is last image. Callback confirmation bound to a draft token; dispatcher's existing per-user event isolation serializes duplicate clicks/albums. New workflow keeps draft on recoverable preflight failure.

Skills: project systematic-debugging, TDD (including writing-good-tests), requesting-code-review, verification-before-completion, finishing-a-development-branch; aiogram-codegen, bot-tester, bot-ux-designer, devops. Claw backend-integration general guidance (its repository registry paths not applicable); WondelAI working-with-legacy-code seams. Anthropic catalog inspected, no matching text-bot specialized guide. User already authorizes PR/merge/deploy, so finishing skill's choice menu is unnecessary. Existing 42 baseline suite failures stay documented, required CI must pass without weakened gates. No paid smoke allowed.

Genjutsu implementation evidence:
- RED commit `54017c8`: 8 failed / 4 passed on baseline; duplicate-role alignment, role collision, clothing misclassified under legacy identity token, four refs rejected, source-less edit accepted, new menu entry absent. GREEN implementation `db60474` makes those 12 checks pass.
- FSM RED commit `3dfb34b`: new source-first wizard not handled. `8b09007` adds standalone states, preserving-back, clear/skip/cancel, per-screen tokens and source upload/probe.
- Persistence RED commit `d6d8387`: actual launch lacks flow/edit metadata; regen/reparams/reprompt route into old flow. `c24a3c4` adds full snapshot and provider metadata, restore into confirmation.
- Review RED commit `604064a`: ambiguous legacy repeat plan throws outside guarded block; photo-only clothing prompt lacks explicit replacement instruction. Both reproduced, guarded planner + explicit outfit replacement fix applied. Extra RED: switching to an ordinary repeat retained abandoned face-edit metadata; shared restore now clears prior FSM before filling new snapshot.
- Independent review: actual provider model and path, token precedence, billing duration/resolution, atomic refund, reference persistence, duplicate-click isolation verified. Reviewer's 75 independent focused tests passed; final accepted fixes rechecked with 2 passing regressions, no remaining blocker in reviewed scope.
- Parent focused regression run: 251 passed, including normal Seedance, Identity Transfer, existing Genjutsu, navigation, runtime/refund reliability. Full suite at this stage: 1424 passed / 41 failed, zero new failure identities against recorded baseline (one existing contact-rate-limit test is timing-dependent). Final tests/CI rerun follows the last restore cleanup.
- Implemented docs: `docs/genjutsu-face-clothing.md`. New tests added to mandatory bot-navigation CI, with editor/core lint; no gates disabled. Provider requests/media/DB are mocked in tests; no paid request or customer message sent.

Final pre-PR verification: mandatory bot-navigation command passes; full suite **1425 passed / 42 failed**, exactly the same 42 failing test identities as baseline `/tmp/artflow-nav-fixed.xml` (zero newly failing tests). Final JUnit evidence `/tmp/apix-face-full.xml`. Changed Python files pass Ruff and compilation; diff whitespace check passes. Independent open review has no remaining blocker. Visual provider output remains unverified because no paid generation is authorized or needed for contract verification. No schema, credentials, prices or runtime configuration changes.


Production acceptance — Genjutsu face / clothing replacement:
- Feature PR: [#179](https://github.com/Bambale0/lena_bot/pull/179), branch `feat/genjutsu-seedance-face-clothing`; reviewed head `245d639cda500edc818f1e633c14b2062de63079`.
- Required `backend-quality`, `webapp`, `provider-contracts`, `bot-navigation` plus repeat/photo checks all passed. [PR CI](https://github.com/Bambale0/lena_bot/actions/runs/36320856767). Native squash auto-merge produced `6df43a1ab18463c833c406da0c1251205dfc0ce1`; no direct main push or admin bypass.
- [Main CI and Production Autodeploy](https://github.com/Bambale0/lena_bot/actions/runs/36320931609) succeeded for exactly that merge SHA, including the separate provider-contract gate and public health check.
- Read-only server verification: `/root/mkdir/lena_bot` clean on `main` at `6df43a1ab18463c833c406da0c1251205dfc0ce1`. App and nginx running with zero restarts. App image `sha256:53a5c32c290c5abf229c1728334e6743296e645fc59f4de5f0a55363d503b328`; started `2026-09-27T13:02:55.641989634Z`.
- Public `https://apixbotai.com/api/v1/health` returned HTTP 200. Application startup complete; zero ERROR/CRITICAL/Traceback markers since container startup at verification. All seven changed runtime Python files have matching source/container SHA-256 hashes.
- Inside the production container, non-billable smoke passed for 0/1/3 faces + clothing, deterministic roles and restore, authoritative @Video1 prompt, exact "25" override, legacy identity roles, and the installed Genjutsu router/states. Provider requests: zero.
- Final maintained navigation selection: **295 passed**. Full suite: **1425 passed / 42 unchanged baseline failures**. Pure/provider/FSM new cases add 55 passing checks. No required gate weakened; independent reviewer found no remaining blocker.
- Remaining limitations: no paid visual generation, so actual identity/outfit fidelity and exact rendered digits remain provider-dependent and unverified. No real-user Telegram session was exercised; handler/routing coverage uses mocked updates and production import smoke. Source/reference retention follows existing upload storage; a missing historical source prompts reupload. Existing unrelated full-suite failures remain outside scope.
- Delivery evidence is committed in a documentation-only follow-up PR after the feature deploy so that production assertions describe observations, not predictions. Application code is unchanged by that follow-up.


Post-deploy routing incident (same delivery, 2026-09-27): the initial no-error startup observation above was a point-in-time check. Subsequent real Telegram traffic after documentation deploy `2069abb` exposed `GenjutsuReplaceFSM() takes no arguments`: the fallback decorator passed a StatesGroup class as a callable filter. Supported-message happy-path tests never reached this fallback. This invalidated final acceptance until corrected.
- Fix branch `fix/genjutsu-state-filter`, baseline `2069abb5e6dfa36ae58b8afa783260d25bfd8080`. RED commit `20a9551`: 11 real aiogram Message/Dice cases fail at filter dispatch, covering four outside states and all seven editor states.
- Minimal fix: explicit `StateFilter(GenjutsuReplaceFSM)`. Unrelated updates return UNHANDLED; unsupported media inside each editor state gets the proper hint without losing state. Test confirmation fixture includes its actual required duration.
- GREEN: 198 targeted tests passed. Independent reviewer approved the minimal filter correction; the reported fixture issue was corrected and the whole focused selection rerun. Existing mandatory bot-navigation CI already includes this test file; no gate changes required.
- Production acceptance must include dispatching unsupported real Message objects through the installed router with Telegram send mocked, in addition to role-builder and startup checks. No customer messages or paid generation are needed for this smoke.

- Routing correction PR: [#181](https://github.com/Bambale0/lena_bot/pull/181). Final CI/deploy SHA, health, logs and installed-router dispatch evidence are recorded in that PR's delivery verification section after deployment. Final full suite: **1436 passed / 42 failures**, identical failing identities to the original baseline; 11 additional real-message regression cases. The maintained navigation selection now contains 306 cases.


---

# Execution ledger — Referral-aware trend sharing

Date: 2026-09-30.
Baseline: `388f67d3e04b79239bb73546d25d9917462a4717`.
Branch: `feat/trend-share-referrals`.

## User outcome
- Every trend link created through the Trends share action carries the sharing user's referral code.
- Shared links use the existing bot `/start` deep-link contract: `ref_<code>__trend_<id>`.
- Opening the link therefore goes through the existing referral middleware before routing to the requested trend.
- First-touch referral rules remain unchanged: an already-bound user is not reassigned to another referrer.

## Reuse / architecture
- Reused `bot.utils.deep_links.build_start_payload`; no second referral-link format was added.
- Reused `AuthMiddleware` for registration / late binding and `start.py` for trend routing.
- The Mini App/website Trends UI already obtains share URLs from `GET /api/v1/trends/{id}/link`, so the backend change covers every current Trends share button without duplicating frontend business logic.
- Text Telegram Trends currently has no independent share-link control, so there is no conflicting second implementation.

## TDD / verification
- RED contract commit: `0bf6ba277bfdcac8b728e071c6ab5fd89287cc7f` adds the endpoint expectation for `?start=ref_REF__trend_101` before the route implementation commit.
- Added referral middleware coverage for the composite `ref_REFCODE__trend_101` payload.
- Webapp smoke / journey mocks were updated to the same canonical link shape.
- Required PR CI and production autodeploy must pass before completion.

## Surfaces
- mini_app: trend share button uses the referral-aware backend link.
- site/web: same Trends frontend/backend share contract where applicable.
- telegram_bot: referral binding and trend target routing reuse existing `/start` handling; no separate Trends share button exists.


---

# Execution ledger — Inline checkout in Trends

Date: 2026-09-30.
Baseline: `c8681137d857815341faf84fb287fce307045ca9`.
Branch: `feat/trend-inline-checkout`.

## User outcome
- Trend Runner shows the repeat price before launch.
- When the current balance is insufficient, the same Trend Runner surface offers the smallest active PricePlan that covers the deficit.
- The user creates a T-Bank checkout without navigating to the separate Balance screen.
- The runner keeps uploaded media and personalization state, polls the quote after checkout opens, and unlocks generation after the payment credit arrives.

## Architecture / no-hardcode
- New authenticated backend quote: `GET /api/v1/trends/{trend_id}/checkout`.
- Cost derives from current ModelCost + trend settings; active top-up plans come from PricePlan rows.
- No payment prices, credit packs, model prices, credentials, or provider endpoints are hardcoded.
- Existing T-Bank transaction/webhook/crediting flow is reused; no parallel payment source of truth.

## TDD / verification
- RED contract commits: `92c6ef983625d8610ffd02c220c4c85a6c5df7e9` and `6c46f17331af03f850e199093ebd484842d7f3fa`.
- GREEN backend implementation: `a90cbaf4edb387b520775d309fd6b75da3046584`.
- Frontend inline checkout: `5674091e6761c1c2ae816d65d666d6259b94edc1`, follow-up state-preservation fix `aef1364d3ec720d736183b6a0fe2898b157535bf`.
- CI exposed a malformed test assertion; corrected in `021a768f829c9192d506469113e032f9e9ef2857`.
- Required PR checks, open code review, merge, production autodeploy, and health verification remain release gates.

## Surface parity
- mini_app: primary affected surface; full inline checkout UX added.
- site/web: the Trends React surface shares this implementation where rendered.
- telegram_bot: existing trend actions that hand off to the Mini App inherit this checkout; direct non-Mini-App trend launches keep existing billing behavior and are not given a duplicate payment implementation.


---

# Execution ledger — Moscow day for admin statistics

Date: 2026-10-01.
Baseline: `7fbe1605f59e00f8727836206f0ca35334190bf1`.
Branch: `fix/admin-stats-msk-day`.

## Incident evidence
- Telegram admin "today" counters were based on the UTC calendar date.
- At 00:02 MSK on 2026-10-01 the bot therefore still reported 2026-09-30 UTC revenue, which made operator and referral-day calculations disagree with the Moscow calendar day.
- Production audit for referral user tg_id 645180669 showed the same ambiguity: UTC-day and Moscow-day referral sales produce materially different totals.

## Fix
- Added one shared `moscow_day_bounds_utc()` helper using `Europe/Moscow`.
- Bot repository counters now query explicit UTC timestamps for the current Moscow day instead of casting timestamps to the UTC date.
- Web admin overview uses the same Moscow-day bounds for new users, generations and revenue.
- Telegram/admin-assistant labels explicitly say `сегодня (МСК)`.

## Verification
- Regression tests pin the 2026-10-01 Moscow day to the UTC interval 2026-09-30 21:00 — 2026-10-01 21:00.
- Required CI, review, merge, deploy, public health and production log checks remain release gates.


---

# Execution ledger — Referral commission accounting ledger

Date: 2026-10-01.
Baseline: production `485cf9264f023f94480094c2b993b7843ea2d50e`.
Branch: `feat/referral-commission-ledger`.

## User outcome
- Every new referral commission is tied to the exact paid transaction, payer, recipient, referral level and applied rate.
- Refund/reversal events are stored as separate negative ledger rows against the same transaction.
- Duplicate webhook/reconcile delivery cannot mutate referral balance twice: the ledger unique key is the idempotency guard.
- The partner cabinet shows the recent commission journal with payer, L1/L2/L3, payment amount, commission amount and transaction id.

## Accounting contract
- Source of truth table: `referral_commission_ledger`.
- Unique key: `transaction_id + recipient_user_id + level + event_type`.
- Each row stores `payer_user_id`, `rate`, `payment_amount_rub`, signed `amount_rub`, `balance_after_rub`, event type and timestamp.
- Ledger insert and `users.referral_balance` mutation happen in one DB transaction.
- Historical rows are not fabricated. The ledger starts recording exact events after deployment; older disputes remain reconstructable from paid transactions and withdrawal records.

## TDD / verification
- RED contract commit: `14bfe3f7685d1c0333df92fb452ad7281a52a333`.
- Tests require payment-linked accrual rows, idempotent duplicate suppression and transaction-linked reversal rows.
- Existing payment webhook/provider paths were updated to pass the persisted transaction object rather than only an amount.
- Required CI, code review, migration/deploy verification, public health and production log checks are release gates.


---

# Execution ledger — Neironych Seedance 2 / 2.5 admin lab

Date: 2026-10-01.
Baseline: production `f6125ae4e55ebb208b58cedb10d2edada5fd8401`.
Branch: `feat/admin-neironych-seedance-lab`.

## User outcome
- APIX Telegram admin Provider Test Lab gets separate Neironych Seedance 2.0 and Seedance 2.5 entries.
- The lab is isolated from customer billing/provider routing. APIX credits are never charged.
- A paid provider request is created only after the admin explicitly presses the launch button.
- Every new request keeps one idempotency key until parameters change or the admin explicitly requests a new key.

## Provider contract verified live
Public provider base: `https://api.xn--e1aikcel5c5a.online`.
Verified endpoints/contract before implementation:
- `GET /v1/models`;
- `POST /v1/videos/generations` -> HTTP 202 + request_id;
- `GET /v1/videos/{request_id}`;
- authenticated `GET /v1/videos/{request_id}/content`;
- `POST /v1/media/uploads` followed by a direct signed-storage PUT with no partner Authorization header.
Live catalog exposed both `seedance-2.0` and `seedance-2.5`.
Live public price parsing returned:
- Seedance 2.0: 480p 6.80 ₽/s, 720p 14.11 ₽/s, 1080p 35.90 ₽/s;
- Seedance 2.5: 480p 10.00 ₽/s, 720p 21.80 ₽/s, 1080p 55.13 ₽/s.
Seedance 2.0 4k remains selectable per provider video contract but is shown as price-not-published when the price page has no 4k row.

## Modes and limits
- Text -> video.
- Multi-reference image/video/audio.
- First/last frame.
- Seedance 2.5 video edit with source video and source-controlled duration/aspect.
- Expert raw JSON overrides for future provider options, with trusted standard fields protected.
- Seedance 2.0: 4–15 s, 480p/720p/1080p/4k, refs 9/3/3 and 12 total.
- Seedance 2.5: 4–30 s, 480p/720p/1080p, refs 30/10/10 and 50 total, edit supported.
- Prompt limit: 40,000 UTF-8 bytes.
- Prompt reference integrity validates @Image N / @Video N / @Audio N before provider spend.

## Security and recovery
- Router is server-side admin filtered with `IsAdmin()`.
- Partner key stays server-side in a gitignored `.env.neironych` overlay and is excluded from Docker build context.
- Pre-signed storage PUT never receives the partner Bearer token.
- Provider errors redact long tokens and URL query strings.
- Telegram files are size/type checked before and after download.
- Result content is downloaded through the authenticated API with bounded resumable range reads.
- Background polling has a timeout; request_id remains in Redis-backed FSM so an admin can manually re-check after a process restart.
- Status failures include provider `expired` as terminal.
- No automatic paid generation is used as a deployment smoke test.

## TDD / verification
- RED contract commit: `52579bf026ee56489f5a735ca23ea6155f1996fd`.
- Focused local gate: 18 tests passed; Ruff clean.
- Read-only live smoke: provider model catalog resolves both Seedance versions and public price parser matches the current provider price page.
- Docker Compose config validates with the optional secret overlay absent.
- Required CI, code review, merge/autodeploy, production health/log and read-only provider-auth verification remain release gates.


---

# Execution ledger — Seedance insufficient-balance inline checkout

Date: 2026-10-01.
Baseline: production `290cf6cea856e5ab19b265284a7d959ae31bb9aa`.
Branch: `fix/seedance-inline-checkout`.

## Problem
The public Telegram video model picker blocked Seedance 2.5 with a Telegram alert:
`Недостаточно 💋. Для 5 сек нужно минимум ...`.
Telegram alerts only expose `OK`, so the user had no direct purchase path at the exact point where more credits were required.

## Fix
- Replace the blocking alert with an inline checkout card in the same message.
- Card shows required credits for the 5-second minimum, current balance, exact deficit, and the smallest active PricePlan that covers the deficit.
- Payment methods are inline buttons for the configured providers only (Card/SBP, Tribute USD, CryptoBot, Lava).
- Existing payment creation/reconciliation code is reused; no duplicate crediting/payment logic is introduced.
- The generation context is stored in FSM. Provider payment screens get a contextual return button.
- After payment confirmation the user gets `Продолжить Seedance 2.5`, which rechecks the current DB balance and opens the normal Seedance reference/settings flow.
- If balance is still short, the same checkout card is refreshed instead of showing the old one-button alert.
- No plan prices or model prices are hardcoded.

## TDD / verification
- RED contract: `09d62292640c0bf78f4fe7bae6daa5835244fd2a`.
- Focused verification: 43 tests passed across Seedance multimodal, inline checkout, payment method choice and payment webhooks.
- Ruff clean for modified bot/payment surfaces.
- Required PR CI, open code review, merge, autodeploy, production health/log checks remain release gates.


---

# Execution ledger — Neironych admin lab direct references

Date: 2026-10-01.
Baseline: production `290cf6cea856e5ab19b265284a7d959ae31bb9aa`.
Branch: `fix/neironych-direct-reference-upload`.

## Incident evidence
- Production Redis showed the active Neironych admin session in `NeironychSeedanceFSM:dashboard`, mode `reference`, with all three reference arrays empty.
- The lab only registered media handlers for `awaiting_image_ref`, `awaiting_video_ref` and `awaiting_audio_ref`.
- Therefore media sent directly while looking at the reference dashboard had no matching handler and was silently ignored.
- Provider upload itself is healthy: a read/write media-only smoke through `POST /v1/media/uploads` + signed PUT succeeded for Seedance 2.5. No paid generation was started.

## Fix
- The dashboard now directly accepts photo and video media.
- Image/video/audio documents are routed by MIME type.
- Dropping media in Text mode automatically switches the test to Reference mode instead of ignoring the file.
- In First/Last Frame mode, dashboard images fill Start then End; incompatible video/audio receives an explicit explanation.
- Existing per-type reference buttons still work; direct upload is an additional fast path.
- Unsupported document types now receive a user-visible message instead of disappearing.

## TDD / verification
- RED: dashboard media tests failed because the dashboard handlers did not exist.
- GREEN: all Neironych admin tests pass and Ruff is clean.
- Live provider media upload smoke succeeded without starting a billed video generation.
- Required CI, review, merge, autodeploy, production state/log checks remain release gates.


---

# Execution ledger - production Neironych credential source

Date: 2026-10-02.
Baseline: `0076d346c24fb80dbebac3312820e6c5d0289a23`.
Branch: `fix/production-neironych-canonical-env`.

## Evidence and scope
- Live Seedance primary submissions returned HTTP 401 `invalid_api_key`, then KIE fallback.
- Compose loads `.env.neironych` after `.env`, overriding the canonical production key.
- Owner confirms `artflow/.env` is the only correct production credential source.
- Do not read, modify, delete, rename or copy the real `.env.neironych`; neither real secret file is part of this change.
- Neironych remains primary, KIE remains fallback; no billing, provider routing or DB changes.
- Site, Mini App and Telegram bot share this app container and credential source.

## Plan and acceptance
1. Add real Compose resolution regression tests using synthetic files in a temporary directory; observe RED.
2. Remove the lab overlay declaration from production Compose; leave the real lab file untouched.
3. Gate the new tests in backend CI and document the single credential source.
4. Verify GREEN, review the diff, PR auto-merge, exact-SHA CI and production autodeploy.
5. Verify runtime key equality to canonical `.env` without exposing values, then a read-only provider auth probe. No billed test generations.

## Verification
- RED: 4 Compose tests ran; 2 failed because the synthetic lab value overrode/supplied the production key.
- GREEN: the same 4 tests passed after removing only the lab env_file declaration.
- Python compilation and deployment shell syntax passed.
- backend-quality now runs these regressions (with real Docker Compose, no application/provider calls).
- Exact-SHA CI, PR review/auto-merge, autodeploy and runtime verification remain pending.
- Pre-deploy read-only auth probe: canonical `.env` key received HTTP 404 for a synthetic nonexistent video ID; unauthenticated control received HTTP 401. The running app still did not match the canonical key. No billed request was made.

---

# Execution ledger - temporary KIE primary for Seedance

Date: 2026-10-03.
Baseline: `da7f94e48347fd8e5ac279dbb4e282d40756edb0`.
Branch: `fix/seedance-kie-primary`.

## Scope and acceptance
- Seedance 2 and both Seedance 2.5 submission paths currently prefer Neironych; KIE is secondary. Fast/Mini already use KIE.
- User requests temporary KIE primary and authorizes merge.
- Use one validated `SEEDANCE_PRIMARY_PROVIDER` setting, default `kieai`; `neironych` restores the previous order after app restart.
- Preserve same-model fallback, existing request preparation, billing, callbacks and polling of in-flight tasks from either provider.
- `site`, `mini_app`, `telegram_bot` all share the generation backend and provider order. Public parameters and pricing are unchanged.
- No migrations or new secrets. Existing environment configuration is reused; a DB/admin routing control plane is outside this temporary operational switch.

## Plan and verification
1. RED: four provider-order regressions failed against the baseline because Neironych ran first.
2. GREEN: the same five-test file passes with KIE first and Neironych secondary.
3. Verify configurable reversal, media/edit payloads, failure handling and the legacy Seedance 2.5 wrapper; run focused checks and review.
4. Create PR, enable native squash auto-merge after review, and verify required exact-SHA CI.
5. Verify Production Autodeploy and public health for the merge SHA.

## Local results
- 93 focused tests passed on Python 3.14: provider order/reversal, both-provider failure, KIE media/edit/identity payloads, legacy wrapper, existing Neironych contracts and product-surface guards.
- New routing module is included in the provider CI compile/lint gate; routing tests already belong to that gate.
- Four initial routing failures reproduced the old Neironych-first behavior before implementation.
- Exact Python 3.12 CI, independent review, merge and deploy verification remain pending.

---

# Execution ledger - provider task IDs in Telegram

Date: 2026-10-03.
Baseline: `9c045a2db0c57b717d8ba29a74147b25f92c9d3b`.
Branch: `feat/bot-provider-task-id`.

## Existing state and requested outcome
- User explicitly wants the provider task ID (KIE/Neironych) to find disputed generations in provider dashboards.
- Generation.task_id already persists provider IDs with internal routing prefixes where applicable. Existing admin search matches task_id.
- Telegram launch, result and failure messages mostly omit this ID. History lists also omit it.
- Add a copyable HTML code reference to bot launch acknowledgments, results, terminal failures and own history. Decode only documented internal prefixes; never invent an ID when a provider has not assigned one.
- Apply to image/video/music/Midjourney delivery paths, including callbacks, polling and file/link fallbacks. Do not expose other users' tasks or change ownership checks.
- `telegram_bot`: explicitly requested surface. `site` / `mini_app`: no UI change requested; provider persistence and admin search remain shared. No schema changes, migrations or new configuration.

## Plan and acceptance
1. Add message-boundary regressions and observe missing-ID failures.
2. Reuse persisted provider IDs through one HTML-safe formatter and wire bot delivery paths.
3. Verify launch, webhook/poll success and failure, history recovery, prefix decoding, missing-ID behavior and Telegram length limits.
4. Run focused lint/tests, independent standards/spec review, required CI, PR delivery and production verification.

## Implementation and local verification
- Shared formatter renders escaped, complete provider IDs in HTML code spans; strips documented web/neironych/nexus/comet transport namespaces and leaves unknown IDs intact. Missing task IDs produce no label.
- Wired accepted-task acknowledgments, webhook/poll results and errors, original-file/link fallbacks, Midjourney actions/modal, and the owner's newest ten history records. History pages preserve complete IDs within Telegram message limits.
- RED: three result-caption regressions failed for missing IDs before implementation. GREEN: 111 focused tests pass on pinned Python 3.12, including actual Neironych video launch, polling success/failure and music webhook delivery. 42 additional image-reference tests pass (one pre-existing model-selection test is incompatible with the baseline handler signature and is outside the maintained CI gate).
- Formatter tests cover HTML safety, missing IDs, routing namespaces, unknown prefixes, history ownership query and full-ID pagination. Ruff maintained changed files and git diff whitespace checks pass.
- New formatter and tests included in maintained CI gates. No paid generation initiated.
- Independent Standards/Spec review, required GitHub CI and exact-SHA production deployment checks follow.
- Full maintained bot-navigation gate passed locally (348 tests). Standards and Spec each identified the same Comet synchronous-image sentinel issue; fixed by suppressing comet:image:direct and its web-prefixed form. Both sentinel regressions pass (17 formatter/history tests total).



---

# Execution ledger — Nano Banana 2.1 Artflow provider routing and reconciliation

Baseline: PR #200, commit `2440734` (2026-10-08). User task: complete the release across Telegram bot, Telegram Mini App and website. Existing CI checks for `2440734` were green, but Codex identified four merge-blocking findings in unresolved review conversations.

## Findings and root cause
1. P1: ambiguous upstream HTTP timeouts caused immediate application-level credit refunds while upstream provider work might still be billed.
2. P2: primary route was environment-only; changing it required deployment, lacked an audit trail.
3. P2: HTTPS was not enforced on the image adapter's bearer-key endpoint.
4. P2: base64 decoding without full image verification could mark corrupt data as completed.

## Target, preservation and risk
- Keep exact `nano-banana-2.1` provider IDs, 1K/2K/4K and up to four references.
- Preserve working Nano Banana 2, Pro, existing session and billing semantics; add only one new routing control plane and scoped reconciler.
- **No double credit/refund or double paid POST after unknown provider outcome.** Protect `Neironych` direct generation, user-facing initial generation, feed remix, and public provider-operation API; use durable UUID and read-only status recovery.
- The provider's synchronous base64 image may not be available in later status responses. Such completed-but-missing-file tasks require manual reconciliation; do not automatically resubmit.
- Provider credentials and API base URL remain in secure settings; only provider choice and its audit are database-backed.
- Production migration `036 → 037` is an explicit safety/rollback gate requiring operator approval (per `AGENTS.md`).

## Implementation and test seams
1. [x] Diagnosed PR reviews and actual Neironych code; confirmed `GET /api/v1/generations/by-client-request-id/<UUID>`.
2. [x] Reproduced HTTPS, correlation ID, corrupt payload and ambiguous-refund failures with tests.
3. [x] Added UUID-before-POST, HTTPS-only transport, PIL raster decode verification, definitive-only fallback.
4. [x] Persisted uncertain tasks as processing, added bounded scheduled and on-demand reconciliation; completion/refund uses atomic existing repository transitions.
5. [x] Added typed, validated admin routing table, DB audit trail, web admin GET/PUT and Telegram admin keyboard; environment is bootstrap fallback.
6. [x] Added unit and integration regression tests for direct model calls, Mini App, admin authorization, routing and recovery.
7. [x] Offline-only review: generated SQL for `036_referral_commission_ledger:037_provider_routing_settings`; read-only production version check confirms `036`. No production DDL applied.
8. [ ] Exact new PR SHA passes GitHub backend-quality, bot-navigation, webapp, provider-contracts, photo-prompt, Pinterest and user-journeys.
9. [ ] Codex review conversations re-reviewed and resolved only after fixes verified.
10. [ ] Production migration/deployment with explicit operator approval; post-deploy model, DB routing, live billing/delivery and health verification.

## Observability and rollback
- Trace via `generation_id`, idempotency UUID, provider choice, correlated status lookup and credit ledger.
- Log no API keys, full user images, or sensitive prompts.
- Control plane change recorded in `provider_routing_audit`, actor ID and source. Rollback primary to Nexus through authenticated admin panel, not by editing environment; pending jobs remain attached to Neironych.
- All new tables and migration are additive; no destructive migration step is required. Deactivation/rollback does not delete in-flight user financial records.

## Technical guidance
- Follow repository `AGENTS.md`, its `.agents/` engineering TDD/playbook and review workflow. Prioritize a failing test → fix → focused regression → PR CI → production verification. Avoid changing unrelated legacy tests to hide failures.

---

# Execution ledger — reject failed video-to-prompt responses

Baseline: production/main `5f02ff2f5a38de56ec4b41be4a419f95f640b934`, tree
`a4155a917df8a7c186989e79fa9573f00f1f770c`; 2026-10-08.
User authorized fix and deployment. No historical credit adjustments authorized.

- Evidence: shared Comet extractor accepts failure-only text as a successful prompt;
  bot and API spend before the provider call and refund only on exceptions.
- Scope: shared response validation, preserving legitimate prompts that quote an
  error; explicit provider errors/refusals/content filtering fail closed.
- All surfaces: Telegram handler and Mini App endpoint use the shared service;
  website delegates to the Mini App endpoint. No UI, model, tariff, migration,
  credential, retry policy or admin-setting changes needed.
- Acceptance: invalid completion causes one existing refund and no success result;
  valid completion remains successful and is not refunded. No paid retries.
- Observability: typed safe error reason, never include full provider payload in
  failure exceptions/logs. Current request and credit attribution remain intact.
- Steps: [x] read-only diagnosis and current-main verification; [x] RED tests;
  [x] minimal fix; [x] GREEN focused/maintained gates; [x] independent review;
  [ ] exact-SHA CI; [ ] authorized merge/autodeploy and public health.
- Constraints: no production Docker/filesystem/journal access, live generations,
  or historical ledger changes. Provider-side cause and prior charges unverified.
- Guidance: repository systematic-debugging, TDD and verification-before-completion;
  Bambale0/claw integration safety; anthropics webapp-testing reviewed (no UI change).
  Connector search found no relevant Bambale0/skills or wondelai testing guidance.

Verification progress: RED reproduced 14 failures before implementation; GREEN
34 focused tests pass, including real shared parser through Telegram/Mini App/web
and success controls. Maintained backend gate: 407 passed; bot-navigation: 351
passed; maintained Ruff and diff whitespace checks passed. Provider contract
inventory first lacked local dummy config; rerun uses test-only BOT_TOKEN and
COMET_API_KEY, not production secrets. Existing CI already includes both modified
test modules. No full legacy-suite claim is made.
Provider contract inventory passed after supplying all test-only required settings
(including dummy DATABASE_URL); no database connection or provider call performed.
Python compilation passed. Independent review found no blocker in validation,
billing/refund integration or legitimate quoted-error preservation.

Independent review reran both changed test modules: 30 passed (the 34-test
focused run also includes four existing API route tests). Typed-error assertions
were strengthened per the reviewer; final exact-SHA CI and deployment remain pending.

---
## Execution ledger — Feed deep-link repeat conversion (2026-10-08)

Baseline `02c807eb1b73e20dc3a0e2af2c76efa1b3e1f26d` (main after #200/#201); branch `feat/feed-remix-prelaunch-conversion`, isolated worktree `/root/agent-work/lena-feed-remix-prelaunch-20261008`.

**Source of task:** user-supplied feedback from Lena and screenshot of post-generation «Ремикс / Повторить генерацию» actions. Customer wants a first-repeat prelaunch editor with optional appearance change, simple post link entry, user photo/reference, visible cost, inline top-up, and immediate start without navigating menus.

**Root-cause preflight:** `App.processStartParam` routes both `feed_*` and `remix_*` to the feed tab without opening the edit runner. The existing `feed-remix-runner.tsx` renders a model/reference/settings form but no user edit text, quote or top-up; `MiniAppApi.remixFeed` fabricates partial feed metadata. Telegram `feed:use` opens intermediate model selectors. Backend `FeedRemixRequest` has no edit instruction. Pricing is in DB (`ModelCost`, `resolve_image_model_cost`/`resolve_video_model_cost`) and existing payment endpoints exist (`/topup/{provider}`).

**Scope / acceptance criteria:** (1) direct feed/remix shared link opens exact public work in the *prelaunch* runner; never submits by itself; (2) user's photo refs + optional appearance change entered before initial repeat; hidden author prompt never exposed; (3) quote from DB before payment/launch including variant + count + video seconds and per-user unlimited, not frontend hardcode; (4) balance, deficit, one-tap top-up with configured payment plans and available methods from APIs, preserve form while payment completes, refresh balance; (5) no accidental duplicate paid POST, safe 402 handling and idempotent retry; (6) obvious chat shortcut from Telegram post to the same inline flow; preserve existing chat generation flows; (7) parity: site and Telegram Mini App share React; text bot provides direct wizard entrance, pre-launch optional change; (8) automated negative/positive tests across backend/Playwright/bot, mobile widths, regression and GitHub PR checks.

**Safety/configuration:** No secrets in frontend; no direct writes to `main`; no DB schema changes unless shown necessary; money tariffs and package/provider selection always read from DB or existing authenticated APIs; only already-public feed posts can be repeated, ownership enforced server-side. No auto-launch on opening a deep link; a paid generation starts only after explicit button press.

**Execution steps:** [x] root cause and relevant `AGENTS.md`, `.clinerules` TDD/debug/worktree and `.agents` frontend/UX skills reviewed; [x] baseline five feed remix pytest tests passed; [x] regression tests failed before fix (405 quote, missing edit helper); [x] backend quote and optional edit instruction; [x] frontend link-to-setup plus balance/top-up; [x] Telegram source WebApp shortcut and chat fallback; [x] API/bot regressions + TypeScript/build; [ ] Playwright E2E on GitHub CI (local Chromium lacks libatk); [ ] PR/review/CI; [ ] production verification if authorized. No migrations introduced.

**Observability:** correlate `source_feed_gen_id`, `generation.id`, quote resolution/model, failed 402, provider task ID, payment id/status, without logging tokens/source prompts. Validate exact deep-link and upload→edit→quote→topup→launch transitions.


**Verification note (2026-10-08):** the broader `test_webapp_routes.py` suite contains three baseline failures. All three were reproduced unchanged from clean `origin/main` commit `02c807e` using an isolated snapshot: `test_photo_prompt_rejects_disguised_non_image`, `test_webapp_feed_returns_items`, and `test_webapp_my_feed_returns_only_current_user_cards`. None of these assertions, helpers or paths were modified for this task. Keep separate from new PR gate and do not weaken tests. Browser job is required because local host lacks `libatk-1.0.so.0`.

## 2026-10-08 — Narrow pending-payment recovery after PR202

- Baseline verified fresh: `5279532ac5c5d6c6d52ea673b6017dbf3dcbb283`.
  Branch `fix/feed-payment-recovery-20261008`; no competing current fix PR found.
  Alternative `126775c`/migration038 remains unpublished and is not merged here.
- User authorized fixing the deployed payment P1s in a separate PR and releasing
  after checks. Scope is durable pending invoice state before external checkout,
  retained unresolved payment across polling timeout/reload/close, and reopening
  or checking the same invoice without creating a second one.
- Preserve PR202 image-count billing, existing payment integrations, appearance
  behavior and hidden-prompt design. No schema/config/secret/price changes.
- Reuse authenticated billing transaction history for exact invoice resolution;
  unrelated balance sufficiency is not proof that an invoice settled. Unknown
  create response or missing invoice remains guarded, never auto-retried.
- Verification: pure-state RED/GREEN tests; mocked browser immediate external
  handoff, delayed webhook, reload/TTL and repeated invoice creation regressions;
  maintained backend/bot/CI, typecheck/build, independent review, exact-SHA CI and
  production autodeploy/public health only after authorized merge.
- Local Chromium execution remains environment-blocked (socket EPERM); do not
  retry/bypass. Browser coverage is executed in existing GitHub Actions.

### Narrow fix validation
- Pure payment-state regressions demonstrated RED before implementation, then
  10/10 GREEN. TypeScript and production build passed.
- Existing maintained backend gate: 407 passed; PR202 prelaunch tests: 7 passed.
  No backend, billing, schema, payment-provider or appearance code changed.
- Independent review resolved same-source late invoice identity adoption,
  Tribute fixed-product URL reopening, and stale quote after fast paid receipt.
  No remaining high-severity findings in reviewed diff.
- Added mocked immediate-handoff snapshot, 130-second webhook delay/reload,
  same-invoice reopening, response loss, latest edits, exact paid receipt and
  stale quote cases. 48 feed-repeat cases collect across four viewports;
  browser execution awaits exact-SHA GitHub Actions.
- Legacy/ambiguous requests with no transaction ID remain unresolved, rather
  than guessing that an invoice settled. Tribute fixed product links are not
  offered as reusable invoices. Existing provider/support guidance is shown.
- Other PR202 findings (quote/provider compatibility/currency and model-dependent
  hidden-prompt confidentiality) are outside this narrow payment-recovery fix.



---

# Incident execution ledger — Neironych Seedance video hangs and delivery (2026-10-09)

**Task:** eliminate end-user stuck video tasks across APIX site, Mini App and Telegram bot. Incident source: Seedance 2.5 UUID `aeb56f5f-ddfd-42fe-baba-115372cbb1e4`, APIX generation `56698`. The provider independently reported failed, while APIX remained processing for >2 h until manual reconciliation; 70 credits were refunded exactly once through the existing atomic repository function. Production read-only inspection after the incident found no other active videos waiting.

**Baseline:** origin/main `396cd57fbbaab64f4c9638d1a9665f6216c72b3a`; feature branch `fix/apix-neironych-video-stuck-recovery`, isolated worktree `/root/agent-work/apix-neironych-video-stuck-20261009`.

**Root causes confirmed:**
1. No scheduled reconciliation of active Neironych video generations; only on-demand endpoint/user-history polling calls `_reconcile_generation_status`. Music and Nano Banana image have schedulers, video does not.
2. Generic `_reconcile_generation_status` treats *all* Neironych poll exceptions as terminal and refunds, including HTTP/network/download errors; it also applies a 20-minute wall-clock refund to a provider that may still be working.
3. The result-delivery helper swallows Telegram failures and has no durable retry after `done` commit; a completed but undelivered video can remain unnotified.

**Scope and target:**
- Enforce provider terminal `failed/cancelled/expired` as sole basis for refund. Unknown, HTTP errors, 404, timeout, slow progress, or valid completion with temporarily unavailable video file cannot trigger refund or a second paid POST.
- Query Neironych Seedance 2.0 and 2.5 active generations periodically, with bounded rate, rotating fairness, database-driven task identities, backoff and observability.
- Download and persist completed video once, settle the DB with existing atomic `finish_generation`, and deliver via Telegram if chat exists. Keep `web:` origin without unsolicited chat.
- Add durable, leased Telegram notification receipt for success and confirmed failure, so a transient blocked chat or Telegram outage can be retried after restart (at-least-once; residual crash-after-send duplicate risk explained).
- No schema migration or modification to primary provider selection, tariffs, prices, balance/credits for successful/unknown requests, or user data. Only normal atomic failure refunds.
- Keep site, Mini App and text bot in sync through shared `generations` state; only Telegram chat needs message delivery. Public status/history must see terminal updates automatically.
- Tests: failing tests first, terminal/transient/slow/completed/no-file/refund-once/lease/bot-delivery/scheduler fairness, then focused suite, CI PR, deploy and read-only smoke.
- Safety: no backfill paid POSTs; no webhook bypass; never expose keys or prompts; no production DDL. PR and CI requirements from `AGENTS.md`.

**Progress:** [x] skill setup and local instructions; [x] incident traced DB→provider→refund; [x] baseline 22 tests passed; [x] 9 regression cases observed failing on unmodified main; [x] typed terminal provider failure, safe non-terminal handling, 20m timeout bypass, bounded concurrent fair video scheduler; [x] transactional success/failure delivery receipts, leased Telegram retries and user failure notice; [x] 47 focused tests passed and 191-video/backend compatibility tests passed; [x] Ruff/py_compile and production PostgreSQL regex selector read-only test passed; [x] required CI gate augmented; [ ] independent PR code review + exact SHA CI; [ ] main auto-deploy and read-only production smoke.

**Observability plan:** log `generation_id`, provider task ID (UUID), state, task age, poll failures, finish winner, notification claim/attempt/message ID, pending oldest age, durable pending count; redact errors/prompts and credentials. If a task is > configured alert age and upstream is unknown, keep it pending, report for manual inspection, **never** launch fallback automatically.

**Risk / rollback:** Notification send then DB ack can be interrupted, causing a duplicate retry after lease expiry; acceptable to prefer delivery over silent loss, mitigated with lease and bounded backoff. Git revert PR restores prior process without rewriting money ledger or pending provider tasks. Production migration not needed.


## Verified incident safeguards (2026-10-09)
- Previous production task 56698: direct Neironych GET returned `failed` while DB was `processing`. Atomic on-demand reconciliation set `failed` and returned exactly 70 credits once; `credit_ledger` has one matching +70 `generation_refund` row. This historical compensation is already complete and is **not** part of the future PR.
- New tests: timeout/404/unknown/mismatched provider ID and >20m slow provider task preserve `processing` and balance; confirmed terminal error applies existing guarded atomic refund + failure notice; completed media copy outage stays retryable; web-origin tasks never send Telegram notifications; successful video queues pending notification transactionally with DB completion; lease/backoff/single-winner token tests prevent duplicate delivery attempts in normal concurrent runs; recovered expired claim can resend after restart.
- Scheduler: 90s default periodic status GET and delivery scans; fair cursor, 24-task batches, 4 parallel bounded workers, 240s max task time. Malformed individual tasks do not block other work. Outages log oldest task IDs and status without exposing secrets/prompts.
- PostgreSQL 16 read-only regexp selector tests: pending=true, sending=true, sent=false. This was tested using literal temporary SQL strings, not customer records or schema writes.
- Deployment risk: no Alembic schema changes, no manual balance or task updates as part of PR. Roll back by reverting PR; records with pending delivery keys persist.

## Codex PR #204 review remediation

Reviewer observed five P2 issues on `6ed8acf`. All five have dedicated reproduction/regression checks:

1. **Long PostgreSQL transactions while polling**: scheduler now commits read-only generation lookup before the provider call; SQL row locks are only acquired again during the short atomic settlement and durable notice claim. Test asserts `commit` occurs before provider GET.
2. **Unbounded Telegram retries for blocked users**: `NEIRONYCH_VIDEO_NOTICE_MAX_ATTEMPTS=8`, then persisted `dead_letter` instead of endless re-sends. Test exercises both retry and terminal dead-letter states.
3. **Foreign provider response UUID**: client validates any returned payload `request_id` against the queried one before interpreting terminal failure. Test simulates a failed status for a different UUID.
4. **Lease-vs-timeout configuration**: Pydantic cross-validates notice and provider poll leases against the maximum configured video recovery timeout, with at least 30s margin; invalid configuration fails to start.
5. **Concurrent user-history/scheduler polling**: new Redis NX/TTL task lease guards the *whole* provider GET + media download + settlement, from all entry points. It is released only by its unique claim token via Lua; unavailable Redis fails closed (no provider charge/refund mutation). Test uses concurrent callers and verifies provider poll only once.

The original four top-level product paths remain shared: website and Mini App poll the generation and receive DB/refund state; Telegram subscribers additionally get success/failure notifications via durable outbox. No second paid POST, no migrations or changes to historical refunds. Independently await new exact SHA CI and code review before merge.


## Codex PR #204 review round two (commit e20f0bb)

Second Codex review discovered three new P2 issues (plus a redundant security finding), reproduced as red tests:
1. Unbounded on-demand Telegram sends could outlive the DB delivery lease and generate a second message. **Fixed:** the outbox notification helper now applies the same `asyncio.wait_for` timeout regardless of caller; on timeout the receipt remains pending for bounded retry.
2. Static Redis SET NX TTL could expire while the same task was finishing its DB settlement, permitting a duplicate provider download. **Fixed:** periodic token-checked atomic Redis lease renewal runs throughout status + download + settlement. Lost ownership cancels the polling attempt and is converted to a non-terminal retry outcome; one bad Redis renewal never takes down the scheduler.
3. Existing Telegram bot foreground Seedance polling used `poll_until_done`, independent of the new Redis lease. It could race scheduled polling/download and refund after an ordinary elapsed timeout. **Fixed:** Telegram Neironych tasks are picked up exclusively by the new background scheduler and persistent notification outbox. Other video providers retain their foreground processing paths.

Review regressions: actual bot video submission for Neironych starts no foreground polling while Higgsfield remains unchanged; 2-way Redis ownership with renewal, lost-owner cancellation/defer, successful token-only release; on-demand Telegram send timeout persists unconfirmed receipt for retry. No new paid submissions, schema changes or manual balance writes. PR review + exact SHA CI and production smoke still required.

## HTTP status latency hardening (2026-10-09)

Additional reproducible root cause of perceived hanging UI: `GET /generations/{id}` and first-page `GET /history` called `_reconcile_generation_status` synchronously for Neironych, and therefore could await the provider GET + up to 250 MB download for as long as 240 seconds, exceeding browser/reverse-proxy timeouts. The new scheduler already supplies the durable reconciliation path. Both read-only HTTP routes now skip Neironych provider I/O and return current database `processing/done/failed` status immediately. Other providers still use their original path. For the exceptional direct/manual reconciler, the read transaction is explicitly committed before slow provider HTTP I/O so PostgreSQL connections are not held while waiting. TDD: three red HTTP/status/history cases plus provider poll DB-connection regression, all now green. This addresses 503/timeouts without creating any new paid jobs; the status may lag by up to a configured background polling interval.


## Wide regression baseline comparison

Full `tests/test_webapp_routes.py` revealed two unrelated pre-existing red cases: `test_photo_prompt_rejects_disguised_non_image` expects error text omitting existing GIF support, and `test_webapp_feed_returns_items` assumes images appear in `result_urls` whereas the existing feed endpoint sanitizes them to `[]`. Both cases were rerun against untouched `/root/mkdir/lena_bot/artflow` main `396cd57` and failed with identical assertions, proving they are **not introduced by the Seedance video recovery branch**. A broader run identified two more pre-existing feed/prompt assertions (`test_webapp_my_feed_returns_only_current_user_cards`, `test_generation_out_includes_all_result_urls`); both were independently reproduced on the same untouched main with identical failures. Neither production behavior nor tests were altered to silence these four unrelated baseline failures.


## Codex PR #204 third-round findings

Additional Codex P2 findings on `1260a00` addressed before merge:
- Local `run_polling.py` mode had no FastAPI lifespan and therefore no Seedance recovery worker after foreground Neironych polling was removed. It now starts and shuts down the same scheduler; a red-to-green entrypoint regression test covers the omission.
- On lost Redis ownership after the first `finish_generation` commit, cancellation could abort post-commit feed royalty and image-session updates. The lease now marks the irrevocable settlement phase immediately before refund/finish; Redis loss can abort provider GET/download, but cannot cancel already-committed money effects. Concurrent lease-loss-in-settlement regression added.
- Unindexed `input_params` regex scan was repeated over all terminal history even when no pending notices existed. New cursor scans bounded `generations.id` primary-key ranges (recent and incremental old), advancing on empty matches, with operational window setting and no schema migration. TDD verifies cursor progress and new/old notice selection. PostgreSQL production `EXPLAIN ANALYZE` confirms primary-key index scan and about 8.6 ms on the most recent 5000 IDs.



## Completion/receipt cancellation boundary

Before release, an additional TDD regression reproduced an independent unsafe outer `asyncio.wait_for` wrapping the entire scheduler reconciliation and notification receipt. Even though provider polling and Telegram send were already independently bounded at 240 s, the redundant outer timer could cancel *irreversible* post-commit feed royalty/linked-session effects or the DB acknowledgement after Telegram accepted a message. Removed both redundant outer timers. Provider GET/download and Telegram send remain time-bounded inside their helpers. Two regressions prove the settlement/receipt work outlives the short provider timeout and finishes; this avoids silent partial settlement and needless redelivery.


## Codex PR #204 fourth-round recovery

Latest Codex reviewed `244c97b` and raised two P2 liveness concerns:
- In-memory old-notice scan cursor resets at every restart, and scanning millions of IDs from zero can take many hours, repeatedly interrupted by daily deployment. **Fixed:** scan cursor is checkpointed after each bounded indexed scan in Redis (existing compose `redisdata` volume), restored from Redis every cycle; new TDD test explicitly discards the Python cursor between cycles and verifies Redis restarts from previous position. If Redis fails, defer the sweep rather than report nonexistent completion.
- Polling-only mode fell back from Redis to MemoryStorage even while Neironych API credentials were configured, causing the now-unified Redis-guarded video worker to fail closed and potentially strand newly charged work. **Fixed:** fail polling startup before Bot creation when Neironych is enabled and Redis unavailable; KIE-only development can retain existing MemoryStorage fallback. Added negative/positive regression.

No new SQL migrations or hardcoded prices, and no paid POST or manual credit writes.


## Codex PR #204 final outbox/readiness checks

Codex code/security review on `6c676a0` found three further P2 cases, reproduced as failing tests and fixed before release:
1. `claim_neironych_video_notice` could reclaim an expired `sending` or overdue `pending` receipt even when `attempts >= MAX_ATTEMPTS` after a process crash. Now transitions to `dead_letter` before claiming, with stale lease token cleared; the completion-time cap remains. Regression verifies both cases.
2. Redis historical notice cursor alone skipped the retry window of previously discovered old receipts. New Redis ZSET tracks discovered notice IDs by due time and a Lua operation atomically commits IDs **before** checkpoint advance. After an attempt, next due is derived from the DB's `retry_at` or `claimed_at + lease`, and terminal `sent/dead_letter` are removed. Tests cover old notice backoff without sweep wrap, token lease expiry, removed successful notice, loss of Redis during discovery, and prior restart recovery.
3. Main ASGI lifespan created a lazy Redis client but could start the webhook/site even if its configured Redis endpoint was unreachable. It now performs a bounded PING against the exact configured Redis before Bot/Webhook creation and fails startup if unavailable (without leaking credentials). Unit regression probes success and connection failure; source contract ensures call precedes webhook.

All recovery paths remain read-only provider GET/download plus atomic existing DB transitions. No additional paid provider submissions or price/configuration hardcoding.


## Codex PR #204 readiness, fallback and old-row intent

Code review on `be993ee` and its security review identified three additional P2 issues (plus duplicate security finding), all reproduced via red regressions:
1. A terminal notice created for an **old** Neironych Telegram generation after its ID range had already been swept was absent from the Redis ZSET if the process crashed immediately after DB commit, or the immediate Telegram attempt failed. The video scheduler now writes a durable Redis ZSET intent (`ZADD NX`) **before** provider status/download and any terminal DB settlement. The notice sync retains IDs while generation is still processing (before the receipt exists), reschedules pending/sending based on DB backoff/lease, removes only terminal sent/dead/missing. Verified an injected post-commit crash and an in-progress intent test.
2. Redis PING did not prove write/ACL capability: a read-only replica could accept users' paid submissions without any working Redis lease, due queue, Lua scripts. The required startup preflight now exercises a random ephemeral lock's SET NX, token Lua renew/unlock, the actual atomic due-ZSET/checkpoint script and ZRANGEBYSCORE/ZADD/ZREM. Both production `main.lifespan` and local polling-only entrypoints call the helper before Bot/webhook setup. Unit tests cover ready Redis, unreachability, read-only SET and ACL denied EVAL.
3. A Telegram `send_video` hang could exhaust the outer notice timeout, preventing a successful direct-link fallback and eventually dead-lettering a paid finished video. Added typed configurable upload budget fraction 0.75 of the total, separately bounded link message in the remainder, retaining outer notice timeout/lease safety and durable DB receipt. Red-to-green timeout/fallback regression.

No new provider POST, SQL migration, uncontrolled user credit change or manual production modifications.


## Latest release preflight and legacy static warning

A final production read-only/scratch-key Redis test using the **actual deployed `settings.REDIS_URL`** confirmed `PING`, temporary `SET NX`, token-checked Lua `EXPIRE`/unlock, atomic notice ZSET/checkpoint Lua, sorted-set range and writes. Scratch keys were deleted; no paid provider requests or ledger mutations. Ruff on all other changed files passes. An unrelated pre-existing `F821` at `api/miniapp_routes.py` public-post route calling undefined `_anonymous_user()` was reproduced verbatim on the untouched `main` deployment (`main` source line 2340 versus branch line 2545). Not altered in this scoped Seedance recovery PR; tracked separately as a legacy issue. Image/other-route legacy tests have documented baseline failures as above.

## CI service isolation after fb5f226

GitHub Actions backend-quality failed on exact `fb5f226` even though the on-host recovery suites passed. The action's failing `Pytest maintained PR gate` step listed precisely two failures: `test_video_scheduler_releases_read_transaction_before_provider_poll` and `test_scheduler_does_not_abort_post_commit_royalty_after_poll_deadline`. Their FakeSession stubs mocked the DB but not the newly introduced durable Redis intent call. CI has no Redis at localhost:6379, whereas the server workstation does, so their accidental integration dependency was invisible locally. Root-cause fix is test-only: those two tests mock the Redis intent seam `_track_active_video_notice_intent` and additionally assert it was invoked exactly once for the generation. Separate `test_active_old_video_persists_notice_intent_before_db_completion` continues to test actual Redis ZSET registration with a fake Redis. Targeted suite rerun under an intentionally unavailable `REDIS_URL=redis://127.0.0.1:1/0` now passes. All provider, finance and delivery semantics remain unchanged; do not start Redis in GitHub just to cover mock isolation.


## Seedance uncertainty circuit and explicit user review state (2026-10-09)

Baseline main 427e57e. New isolated branch fix/apix-seedance-uncertain-routing-20261009.
Read-only evidence: two APIX generations (identifiers and amounts redacted) remain processing for over two hours. Their matching upstream generations (identifiers redacted) are reconciliation_required with submission_outcome_unknown, no external task ID/polls. Worker logs show ArgoLink POST 503 for both. The API hides internal review status behind pending; APIX ignores its error and continues displaying normal processing. No completed output exists. Reconciler itself runs every 90s.

Scope: typed nonterminal review outcome; persist manual-review marker and one durable notification (same outbox, no money mutation); expose reconciliation_required to site/Mini App/Telegram rather than claiming normal creation. Protect NEW requests from the known-uncertain Neironych model via a bounded, model/environment-scoped Redis circuit consulted BEFORE any paid submission. While paused, use existing KIE provider only, never resubmit the uncertain jobs or fall back into the paused route. Do not refund ambiguous provider expense or user balances without explicit financial authorization. Preserve existing per-generation atomic success/refund and final notice behavior.

Acceptance: runtime raises typed review exception for exact pending+submission_outcome_unknown; normal pending/transport errors remain distinct. DB marker+review outbox written under expected-task/active-state row lock and only once; terminal transitions still replace review notice. Model-local circuit is refreshed while unresolved; default cooldown configured, no change to user tariffs. New-request routing selects KIE BEFORE any POST and fails closed if admission check cannot run; old job never retried. Browser labels review without success toast and supports later refresh; bot reports no receipt/possible charge honestly. Existing success/failure and no-double-refund regressions pass. Independent PR review, exact-SHA CI and normal auto-deploy, then read-only real-task verification required.

Skills: repository systematic-debugging, test-driven-development and verification-before-completion; claw release-hardening; no schema/price/key change.
Progress: [x] reproduction/trace and scope; [ ] RED tests; [ ] implementation; [ ] CI/review/deploy and live verification.

### Verification progress
- RED: five independent failures proved unknown provider status was ignored, paused route was still used/re-entered, review notice could not be claimed and public status stayed normal processing.
- GREEN: 140 focused new/existing video tests and exact maintained backend CI gate (532 cases at this point) passed with intentionally unreachable Redis in the test environment. New module tests mock real Redis explicitly; no paid requests or user balance changes.
- TypeScript typecheck and Vite build passed. Local browser execution is unavailable: installed Chromium cannot load libatk-1.0.so.0 on this production host; do not install OS packages into production just to satisfy a test. Added the real browser regression to the existing four-device CI suite, which installs required dependencies on its runner. Browser assertions still need CI verification.
- Remaining: fresh full changed-file lint after test additions, PR review, exact-SHA CI and normal auto-deploy. Main remains unmodified.

### Exact CI isolation correction (2f76219)

GitHub navigation and provider-contract jobs failed because two more provider/Telegram test modules invoked the newly added Redis admission seam without mocking it: test_genjutsu_replace_bot (three scenarios) and test_provider_spec_p0 (same-model fallback). The complete CI trace shows localhost:6379 refused, not a provider payload or product failure. These modules now mock the external admission seam as other provider tests do; dedicated circuit/Redis-failure regressions remain real unit tests of that seam. Local tests passed before isolation because tests/conftest.py overwrites REDIS_URL with localhost:6379, where this host has Redis. Thus the earlier wording that an environment override forced Redis unavailable was inaccurate; use the dedicated failure-injection test as proof of fail-closed behavior and CI as proof no Redis service is needed. No production or financial behavior changed in this test-only correction.

### Review of 2f76219 and corrective tests

- P1 durable admission: a Redis write failure after DB review commit must not reopen new submissions. Admission now checks active model/provider-specific PostgreSQL review markers when the Redis key is absent; DB errors fail closed. Added lost-cache and database-query/exception regressions.
- P2 notice ordering: nonterminal review notices now reload status and claim token immediately before send, suppressing a notice already replaced by terminal completion/refund. Red-to-green test simulates terminal completion after claim but before message send; stale acknowledgement cannot erase terminal notice.
- P1 standalone website: GenerationCard now uses the same review projection as Mini App/realtime, and landing/js/prototype-premium.js labels the state, keeps it pollable and displays held-credit/support guidance. The original oversight was that site REST does not exclusively use the Mini App serializer.
- P2 AppV4: its separate ACTIVE_STATUSES set now includes review so later terminal results refresh without reloading. Both standalone/V4 predicates have executable JavaScript regressions in addition to browser CI coverage for the modern UI.
- P1 evidence privacy: customer generation identifiers and amounts introduced in this execution entry were redacted from the final tree. Delivery uses the mandatory squash merge; no force-push or rewriting protected main history was attempted. Actual IDs remain only in authorized operational systems/chat, not new source/test fixtures.

## Seedance Neironych default and create-response recovery — 2026-10-09

Supersedes the earlier temporary KIE-primary default record; explicit environment
values still override the default. Ordinary Seedance 2/2.5 use Neironych first and
KIE after definitive rejection. Fast/Mini remain unchanged.

Baseline: a55e8e6; synchronized with main 77db6e18 (PR224), preserving its UX2
changes. Delivery: PR223. Site, Mini App and Telegram share the same backend.

New attempts durably record a correlation UUID before POST. Ambiguous responses
hold credits and recover by authenticated read-only client-UUID lookup, without
replay or speculative refund. Identity/model/key checks and atomic settlement
protect late responses. Proven pre-POST failure refunds only the locked matching
attempt. Foreground bot review edits share the durable notice claim/receipt with
the scheduler; failed edits retain the outbox fallback.

Verification uses mocked HTTP and isolated synthetic SQLite; exact-head required
CI and independent code/security reviews precede normal protected merge and
main autodeploy. No new migration, historical backfill, production DB operation,
manual SSH operation or paid generation test. Final exact-SHA CI/deploy evidence
is retained on PR223. See docs/seedance-reconciliation-guard.md for full semantics.

Missing/unavailable provider evidence remains nonterminal, with bounded read-only
checks and overdue review. KIE's separate inherited transport/refund behavior is
outside this package. Existing server environment loading is not independently
inspected; deploy and public health are verified through the standard pipeline.


## Consumer video status privacy (2026-10-10)

Baseline: `5523593bdf15eda6b05ff2af3f318c2c52a551a7`; branch `fix/apix-consumer-video-status-20261010`.

User request: do not send end users intermediate supplier/reconciliation/held-credit messages. Show launch acknowledgement, then only finished video or a clear error. The attached Telegram example identifies one active request; its recovery and balance are not authorized for modification by this wording task.

Confirmed root cause: `mark_neironych_video_reconciliation` creates a pending `reconciliation` Telegram outbox item and `_deliver_pending_neironych_video_notice` sends supplier detail via its dedicated helper. React Mini App, V4 legacy app and standalone landing duplicate the same technical explanation and separate review badge. This is not a provider outage fix or finance-policy change.

Acceptance / scope:
1. New reconciliation notices are explicitly suppressed (not falsely marked sent). Old pending/sending review outbox items are suppressed safely under existing row/token guards so restarts do not send them. Keep actual terminal success/error notices working.
2. Reconciliation markers, provider polling, Redis circuit, no-paid-retry and atomic refunds stay unchanged. No automatic failure/refund based on unknown status, no DB schema migrations.
3. Existing API machine status `reconciliation_required` remains backward compatible; all customer UI labels/messages map it to ordinary generation-in-progress. Technical detail remains in admin/runtime diagnostics.
4. Final error message says only the video failed and the actual credited refund; no supplier claims. Existing initial accepted message and UUID remain.
5. TDD: new silence/retry/race tests; update superseded UX assertions (not financial invariants); run backend maintained gate, frontend build and browser regression. PR, review, exact-SHA CI, native auto-merge, auto-deploy and production smoke.
6. No notification campaign or direct edits to previously sent Telegram messages, no provider POST or user balance mutation. Read-only verification of the screenshot task only.

Progress: [x] current repo/AGENTS/README, code, actual DB, notification and frontend paths inspected; [x] local TDD/systematic-debugging/verification playbooks read; [ ] failing regressions; [ ] minimal fix; [ ] verification/review/release.

### Implementation and verification
- New `reconciliation` notices use `suppressed`, with zero Telegram attempts; old pending/sending reviews are retired under existing row locks. An already-claimed stale review is suppressed only with its matching token, so a later `done`/`failed` outbox item is not consumed. Foreground uncertainty no longer edits the acknowledgement to supplier details. Terminal success/failure delivery, ledger updates, polling and source UUIDs remain unchanged.
- Mini App (legacy and UX2), V4 and standalone site keep the machine review status pollable but show ordinary nonterminal labels with no supplier/credit-hold explanations. Failed video message reports only video failure and an actually recorded refund.
- TDD: seven initial behavior regressions failed on main; after the fix 88 focused backend cases passed, including SQLite restart recovery with single terminal send/refund and no paid resubmission. Updated old message-specific assertions because the user explicitly replaced that UX policy, not to relax financial checks.
- Frontend: all 93 unit tests pass; TypeScript check and Vite production build pass. Scanning built artifacts confirms obsolete supplier/held-credit copy is absent.
- Local Playwright cannot launch Chromium because the host lacks libatk/libatspi/libXdamage/libasound. No system packages installed on production for this check. The two new/updated UX2 browser scenarios are included in the required GitHub webapp gate, which supplies browser dependencies. Test-only Playwright module resolution was isolated under the worktree; production dependencies untouched.
- A full maintained-suite launcher call was blocked by tool safety and was not retried by an alternate mechanism; required GitHub CI remains the full-suite verification source. Focused backend and all frontend unit checks above executed successfully.
- Read-only investigation of the screenshot task: the actual upstream generation has an initial failed attempt followed by a 503 on fallback submission, with no final media at investigation time. No cancellation, refund, new provider submission, or customer message was made during this task.
- Required next gate: independent PR review, exact-SHA CI (including UX2 browser), protected auto-merge, production autodeploy and public health/runtime smoke.

- Cross-surface audit also found an existing standard Mini App browser smoke asserting the old supplier text. Updated only those UX assertions to neutral waiting, retaining the existing processing -> review -> done transition, disabled premature publish, and zero paid replay assertions. The UX2 test covers review -> failed. GitHub now verifies both terminal paths on the same consumer policy.

- Added a separate RED/GREEN recovery invariant: suppressing a progress receipt must not remove the active generation's durable terminal-delivery intent. The notice scheduler now checks DB generation state for suppressed reconciliation items and retains active intents until the real success/error receipt is created. No extra customer message or provider POST; this protects eventual delivery after a restart.

### Independent review: atomic receipt/status snapshot
Codex P1 PRRT_kwDOSSmOms6rC2fd identified a real READ COMMITTED race: the old receipt and the new terminal status could be read by separate SELECTs and cause removal of a newly needed Redis delivery intent. Added a failing regression that simulates that interleaving, then replaced the two reads with one SELECT of input_params + status. An active suppressed snapshot now stays queued and a terminal snapshot sees the corresponding pending receipt. Existing due-time/lease/terminal cleanup stubs were updated to the single-row query without changing their assertions. This does not mutate generation or ledger state.


## 2026-10-10 — Seedance auto-close and no global provider circuit

Baseline origin/main: e145252c8e33a964c2a61e0b2e3f7f1dd62fd018. Isolated worktree: fix/seedance-autoclose-no-global-circuit-20261010.

### Confirmed cause and business requirement
- One unresolved Neironych Seedance request set the model-wide Redis/DB admission gate and routed unrelated *new* customer work to Kie. A 30-minute Redis TTL persisted even after an operator refunded the original task.
- The existing recovery scheduler polled results and emitted warnings after NEIRONYCH_VIDEO_ALERT_AGE_SECONDS, but **never transitioned an unconfirmed old job to failed**, even when it was over one hour old. The customer remained charged until support intervened.
- User requested automatic closure/refunds instead of a global gate; preserve one-time paid submission, provider/financial reconciliation and no duplicate payouts.
- Production preflight 2026-10-10 10:45 UTC: **zero Seedance active tasks older than one hour**; one young active task, no mass-refund blast radius at release.

### Design
- New config SEEDANCE_AUTO_REFUND_SECONDS defaults to 3600 (bounded 1800–86400).
- Every video scheduler cycle processes a bounded oldest-first batch of overdue Neironych Seedance 2/2.5 jobs with task IDs or persisted submission IDs.
- One final existing read-only provider poll is performed; if result already settled as done/failed, leave it intact. Otherwise use the repository's atomic fail_generation_and_refund with an exact expected_task_id, a safe customer error, ledger note identifying automatic timeout, and a terminal DB-outbox notification only on Telegram surfaces.
- Supports previously unbound neironych-submit IDs; outbox scan must include them. Redis notification failures cannot block committed refunds, and the timeout phase runs **before** Redis-backed notice processing.
- New unrelated tasks always try configured primary (Neironych in production). Unknown submissions and pre-submit durability errors **never** fallback/reissue the same paid generation. Ordinary errors may still follow separately configured provider fallback.
- Leave upstream provider reserve and audit identity for independent reconciliation. No automatic supplier charge reversal, no user secrets in logs.

### TDD and checks so far
- RED witnessed for absent SEEDANCE_AUTO_REFUND_SECONDS, absent overdue query/processor and old route choosing Kie during another customer's pending review.
- GREEN 103 focused tests across routing, timeout, existing video recovery and credit-ledger transactions; Ruff, compile, whitespace pending full final run.
- Existing site/MiniApp and Telegram status updates use the shared generation row; timer uses terminal failed and existing outbox.
- Still required: concurrent/late-result tests; exact CI, independent code/security review, deployment and production smoke verification.

### Review-driven hardening of PR #235 (second commit)

Initial exact-SHA GitHub backend, navigation, provider and Playwright checks were green on da43ed8. Independent Code/Security Review raised eight P1/P2 issues. Before any merge, the implementation now:
- Uses a guarded **single Kie createTask POST**, and an explicit KieSubmissionOutcomeUnknown for HTTP 5xx, transport loss, invalid response and missing taskId. No provider retries/fallback for unknown outcomes. KieDefiniteRejection alone allows safe fallback when Kie is primary. Other Kie endpoints were not altered.
- Starts the 60-minute provider clock at the durable Neironych submission marker started_at rather than before reference upload. The SQL selector uses a correctly cast coalesced PostgreSQL timestamp; EXPLAIN ANALYZE passed on real production PostgreSQL read-only without customer data changes.
- Claims the **same Redis video poll lease** as customer history and media download, then runs a bounded read-only provider GET/identity lookup. If lock is busy or provider says completed (even when downloading is broken), it defers refund. If identity becomes bound, it saves that ID rather than refunding. Terminal failed is eligible for fail+refund. Pending/unknown after deadline may receive a provider-uncertain SLA compensation.
- Saves a durable seedance_refund_provider_review marker **in the same DB commit** as the user credits and ledger when upstream remains uncertain. An independent, bounded post-refund read-only checker carries it through restart, records late done/failed in audit (never mutating final user balance), and alerts administrators on conclusive supplier state.
- Runs deadline, normal downloads, Telegram outbox, and supplier review lanes concurrently. A broken Redis notice-queue accelerator does not block the credit settlement; delivery notice is still in the transactionally committed database outbox.
- Prevents credit recycling with a user-scoped liability gate: while an account has an outstanding supplier review on a refunded Seedance task, it cannot issue further paid Neironych Seedance POSTs. Other accounts are entirely unaffected. A rejected pre-submit command refunds the charged new customer generation via the existing no-POST path.
- Uses the existing typed environment refund deadline and validation. An admin-editable DB control-plane deadline remains a separate follow-up enhancement; changing the configured SLA still requires deployment. No changes to pricing or purchasing are part of this patch.

New/updated tests cover: lost Kie response/5xx with exactly one provider POST, safe definite-rejection fallback, invalid/missing Kie task ID, real-DB-independent supplier audit in refund transaction, lease contention, late provider completion without balance change, short final GET, submit-start clock, pending and 503 before and after deadline, no starvation of Telegram, per-account liability gate and unaffected unrelated user. All review findings must be rechecked against the updated SHA; no user credit/debit, provider paid POST, or production deployment was done while preparing these tests.


### Continuation: Kie correlation and current main reconciliation (2026-10-10)

PR #235 code/security review on 47633a9 found financial issues: Kie 5xx/lost submit results needed persisted callback linking; late-completed provider reviews needed to remain blocked pending supplier-cost settlement; expiry and normal polling needed independent claims; indefinite supplier reviews needed bounded operator escalation; SQLAlchemy expired rows needed snapshots before read-only transactions end. First fixes committed as 47633a9; further source/test fixes staged here.

- Kie callback obtains per-generation HMAC parameters before its one-shot paid POST. Missing createTask response never authorizes another provider POST or speculative refund; the unknown submission is durably marked kie-submit plus generation ID and can be correlated by a signed webhook.
- Customer deadline refund is atomic. Late provider callback only updates supplier review metadata. Completed provider charges remain blocked for that specific customer until authenticated admin settlement; unrelated users are not blocked.
- Provider audits have maximum checks/age; indeterminate results escalate to operators and do not self-clear; completed remote video does not authorize refund; Redis failures do not invalidate durable refund/outbox.
- 150 focused service/finance/reconciliation tests were green. Two new SQLite durable roundtrips validate Kie unknown->bound and Kie refund->late provider completion->admin settlement; four Kie callback tests green. Legacy API/bot test fakes updated for new persisted registration. Ruff and compilation green after fixing accidental escaped newline in Telegram import.
- CI now includes new timeout and Kie callback regression files. Main advanced by #237; reconcile via ordinary merge in feature branch, rerun exact-SHA CI and review before protected squash deployment. No production customer money was changed during tests.

---

# Execution ledger — feed creator-input replay (2026-10-10)

Baseline: `e145252`, fix branch `fix/feed-replay-source-inputs`; production `main` unchanged.
Observed: published Seedance 2.5 job #57213 was created with a photo and a 5140-character prompt, but personalized job #57247 was sent a rendered video plus the reader photo and a 314-character generic edit prompt.

## Outcome and acceptance
- Repeat server-side creator prompt with new viewer image(s).
- Never convert generated output MP4 into a reference video when it was not a creator input.
- Reuse an original video reference only if it is present in the source task's stored input.
- Secure prompt from user-visible API/Telegram output, copies, and history.
- Same rule for site, Mini App and Telegram; quote and submission must agree.
- Reject extra video inputs and unsupported/missing provenance before charging.
- Preserve provider/model adapter routing and ledger/refund paths.

## Plan and evidence
1. [x] Preflight AGENTS, local skills, code paths, production provider and DB records.
2. [x] Isolated branch/worktree; read-only production is kept untouched.
3. [x] RED regression tests: video-output source with image-only original inputs wrongly sent generated MP4 / lost creator prompt. Both Python and Node tests reproduced the fault before change.
4. [x] Author input-provenance resolver, server-side prompt/parameters recovery, Telegram picker and Mini App/site parity; no generated MP4 injection for sources with known provenance. Legacy sources with missing input snapshots still use the existing guarded compatibility flow.
5. [x] Local regression: 14 provider + source tests, focused feed/Seedance suite; Ruff clean, Python compileall clean, TypeScript typecheck, Node unit 105/105, Vite production build pass. Two legacy feed tests and an unrelated web referral test fail identically at baseline; do not change them in this PR.
6. [ ] PR / green required GitHub checks / auto-merge / deploy verification. Local Playwright test is blocked by missing `libatk-1.0.so.0` on host; CI is the authoritative browser gate. No real paid generation was submitted.

No new config or pricing keys. Trace source generation and input-media provenance without printing author prompts or reference URLs.

## Codex review follow-up — creator input replay
- Resolved known-provenance video from text-only models: original prompt + text mode, no mandatory photo and no rendered video. Original-model compatibility and no extra viewer image are enforced in both browser and bot.
- Deep-link hydration in `src/lib/api.ts` preserves source-video provenance and original settings from `/api/web/feed/{id}`; added browser test for old shared posts outside the initial feed page.
- `?legacy=1` original feed screen routes known creator-recipe videos through the shared modern safe runner, not the rendered-MP4 editor. Untouched legacy image/unknown snapshot paths keep prior behavior.
- Restore original validated Grok mode (and safe read-only public Grok mode metadata) in quote, submission, Telegram FSM and browser settings.
- Reject viewer audio/characters/seeds on Telegram exact replays before credits are charged; keep additional author video references only in their original validated form.
- Verified 282 backend feed tests (2 unrelated existing baseline failures excluded), 105 JS units, Ruff clean, TypeScript check, Vite production build. CI browser/deploy checks still gate release.


### Financial pre-submit fail-closed guard (2026-10-10)

An additional self-audit on merged branch 7d657a1 found a real risk: register_kie_video_callback can legitimately return false (generation row no longer eligible, no durable callback identity), yet four launch routes ignored the result and still issued paid POST. Three regression tests first failed against original branch with visible provider calls despite registration refusal (MiniApp launch, remix, Telegram). All four launch paths now require a successful durable registration before provider call; refusal is a no-POST failure that uses guarded standard generation refund, not new provider POST. RED -> GREEN tests and all related Feed/Genjutsu/routes/Kie transaction cases passed; Ruff clean. This is a release-critical guard against lost Kie responses without recoverable callback identity. No production charges or direct financial writes during tests.


### Real SQLAlchemy rollback detachment P2 guard

The previous Security Review warned that the final provider GET after a session.rollback might use a detached expired ORM generation. An actual SQLite SQLAlchemy Session reproduction confirmed this exact failure: reading task_id after the second rollback raises DetachedInstanceError, which the existing error catch interpreted as unknown provider outcome and would wrongly refund a remotely completed paid video. The new integration regression was RED (log: Seedance final status deferred reason=DetachedInstanceError, returned refunded); fix materializes task ID, model and copied decoded input params as a simple immutable-value snapshot BEFORE rollback. Provider GET and read-only submission binding use only the snapshot; the fresh row/ledger settlement remains separately locked and guarded by task ID. New test GREEN and all 166+ targeted finance/recovery tests GREEN; Ruff/compilation clean. No actual production ledger entries modified for this validation.


## 2026-10-13 - Feed photo repeat identity-reference priority

Baseline: `8f5d381a059b64fff609945d0d5d1c50466e4117`; local branch `fix/feed-remix-user-reference-priority`. Production and paid provider APIs were not accessed.

### Confirmed defect and narrow fix
- Mini App `_prepare_feed_remix_inputs` and Telegram `_launch_session_generation` both submitted a personalized image repeat as public source image first, followed by the reader's uploaded identity references. The image service and Nexus/KIE adapters preserve this list order.
- A synthetic Telegram regression reproduced the old order before the change. The exact user report still cannot be correlated to a specific generation without its link/ID, so this records a confirmed orchestration defect rather than claiming provider-specific causality.
- Added one shared ordering boundary: direct reader references remain in their original order and are deduplicated, then the public feed source is appended as scene/style context. A plain repeat with no reader image still submits only the source image.
- Updated the isolated personalized prompt contract to describe the final image as the public source and preceding images as user appearance/object references. Hidden author text remains excluded on personalized paths.

### Verification
- `58` feed prompt/security tests passed after RED/GREEN.
- Independent review found and closed a Telegram image-source-to-video parity gap: that path now uses the same user-first/source-last helper and its launch/regenerate regressions are green.
- `134` focused tests passed across feed security, quote/prelaunch, Seedance API/Telegram image-video repeats, ordinary multi-reference generation and the existing Pinterest identity-before-scene provider contract. Direct tests cover multiple user photos, stable deduplication, source-only repeats, request-scoped source switching and prompt Image-role wording. The ordinary generation test confirms its user-supplied order remains unchanged.
- The broader Telegram reference module passed `42` tests and retained one unrelated failure in `test_model_selection_opens_task_first_composer_for_any_model`; the identical missing-`db_user` failure was reproduced on a clean detached `8f5d381a` baseline.
- Ruff and compileall passed on all changed Python implementation/test files. The focused `134`-test acceptance run had no failures; one existing AsyncMock coroutine warning remains in the ordinary-generation test. The first PR CI run exposed one additional maintained Seedance test that still asserted source-first ordering; its expectation was updated to the same user-first contract and the complete file passed locally before republishing.
- Independent review has no remaining blocking findings after the Telegram video parity fix; final multi-reference test recheck and publication are still pending. No merge, deploy, secret, pricing, balance or historical ledger mutation was performed.
# Execution ledger — feed image recipe for all reference-capable models

- Baseline `9bca8443353ad1ed394cd65f80965afd269326bc`; branch `fix/feed-repeat-all-image-models`; 2026-10-14. Pre-existing untracked diagnostics and `error.log` are unrelated.
- User outcome: every supported image model repeats a public photo using the creator's original prompt and only the reader's uploaded references. No finished author image or author input references enter the provider request. A model unable to take both text and a reader image must fail before charging.
- Evidence: production generation `59353` (`nexus:3c18db9f-2a9d-4c09-8e51-067ee80bee54`, Nano Banana Pro) already received the creator prompt plus one reader collage and no author image. Its facial resemblance is weak. The collage is 714×1280 with small face regions; no separate close portrait exists. This establishes a separate image-quality limit that routing alone cannot resolve. No live paid rerun was made.
- Current state: Nano Banana 2.1 accepts recipe replay for all public image posts, including derived posts; other models require direct-post metadata and can fall back to author-finished-image editing. Site/Mini App shares one API and React runner; Telegram has separate collection and generation paths. Provider capability data is in `IMAGE_CAPS` and `IMAGE_SPECS`; Midjourney Imagine accepts prompt plus one image, Blend has no text prompt. Existing admin-controlled identity instruction, audit table, model tariffs and feature rollback flag are reusable. No schema/auth/permission changes are planned.
- Risks/dependencies: source ancestry must stay public; missing origin fails closed; some models are text-only or have no prompt+image contract; provider identity fidelity cannot be guaranteed from a small collage. Do not manufacture face crops or paid retries. Do not expose the hidden prompt in UI/API/session/logs. No source image may be silently added as a reference.
- Acceptance: quote and submit use identical author-prompt/reader-reference policy for each compatible model and fail before charge for incompatible models, no refs, bad ancestry or unavailable media. Bot/session repeat and site/Mini App reflect the same rule and reference capacity. Provenance context stays v4. Focused tests cover model families, derived posts, unsupported models, no charge, source isolation and previous-repeat protection. Required CI, review and exact-SHA autodeploy/public health gate apply.
- Configuration: keep `FEED_ORIGINAL_RECIPE_ENABLED` and the audited `feed_recipe_identity_policy` admin setting; model availability/prices remain DB-backed. Capability comes from provider contracts, not a new hardcoded business list. Observability: existing structured feed recipe logs contain generation/user/model/ref count, without prompt or URLs. Test seams: provider wire mocks, quote/submit repository mocks, bot state/launch mocks and frontend capacity tests.
- Steps: [x] production incident/read-only evidence; [x] repository/provider/UI/bot/CI preflight; [x] RED regression tests; [x] backend/bot/frontend implementation; [x] maintained backend CI test list, bot navigation and focused provider contracts passed locally; [x] 113 web unit cases, typecheck and build passed; [x] OCR delegate review covered 7/7 source files and found a stale-FSM owner-ID gap, fixed by taking the authenticated user ID at launch; [x] 38 Desktop browser cases passed; [x] PR #255 opened with auto-merge enabled; [x] stale foreign-post fixtures corrected after CI exposed the new public-recipe prerequisite; the 8 Tribute browser cases and 25 domain-06 user journeys passed locally in separate runs; [ ] required exact-head CI; [ ] exact-merge-SHA production deploy and public health verification.
- No schema migration, pricing change or new secret. `FEED_ORIGINAL_RECIPE_ENABLED` and the audited admin identity instruction remain the control plane. Existing structured logs record source ID, reader ID, model and reader reference count without URLs or prompts. Public post ancestry and reader ownership are checked at the paid boundary. The latest reported Nano Banana Pro task already used the correct inputs, so this routing release cannot guarantee stronger facial likeness from the small collage; a separate crop/portrait enhancement would need its own quality and capacity validation.
- PR #255 review found a blocking text-bot setting loss: marketplace cleared FSM before the generation launch, so the reader's selected aspect ratio could be overwritten by an unsupported origin ratio. Focused RED tests reproduced both the lost ratio and unsupported inherited 21:9; the fix carries only the selected ratio through the clear and inherits an origin ratio only when the selected model supports it. Ratio menus no longer manufacture portrait for models without ratio support. Re-run exact-head CI and resolve the review thread before auto-merge.

# Execution ledger — stronger face priority in feed image repeats (2026-10-14)

- Baseline `6924f2e15ebef5a2b62971d6d96bed268e9de02e`; isolated branch `fix/feed-identity-priority`. Production remains on `main`. Pre-existing untracked diagnostics and `error.log` in the production checkout are unrelated.
- Intended outcome: all compatible image models receive the creator's full original scene recipe and only the reader's photo references, with explicit scene and identity-policy sections and the authenticated admin identity instruction retained as the final rule. Site, Telegram Mini App and text bot share `build_feed_image_recipe_prompt`; no client-facing author prompt exposure.
- Read-only production evidence: completed post-deploy repeats 59420 (Nano Banana Pro) and 59422 (Seedream 5 Pro) both have v4 provenance and one reader reference; neither stores the author's finished image as a reference. Visual comparison shows partial but imperfect facial likeness. The current DB policy already names face geometry and forbids blending; the common builder currently concatenates a 2309-character creator prompt and that instruction without labeling the author's text as scene-only. Generation 59418 was pre-deploy v3 and is excluded from quality assessment.
- Existing/reusable: `feed_recipe_identity_policy` is singleton, typed, audited and authenticated through `api/web/admin.py`; `FEED_ORIGINAL_RECIPE_ENABLED` is rollback control. `feed_image_recipe_context` v4 binds prompt digest and instruction for safe continuation; API quote/submit and bot call the same builder. No schema, auth, tariff, provider mapping, secret or new mutable configuration is needed.
- Risks/dependencies: changing prompt structure must not duplicate or remove creator text or reader changes on a derived repeat; historic v4 and older marker-bearing recipes must still unwrap safely; provider prompt-size limits should not be strained by repeating the long identity policy. A stronger instruction cannot guarantee biometric likeness from a small collage, and no paid production rerun is authorized.
- Acceptance: shared composition labels the creator text as scene direction and gives reader identity explicit precedence; the creator recipe, requested edits and current admin instruction each appear once; old authenticated continuations remain idempotent; all provider requests contain only reader references; no charges or URL disclosure in quote. Tests cover builder RED/GREEN, API/bot/provider parity, provenance, admin control and maintained CI. Observability uses existing generation/source/model/reference-count logs without prompt or media URLs.
- Steps: [x] production read-only state and image inspection; [x] repository/docs/schema/auth/admin/provider/tests/CI preflight; [x] isolated worktree; [x] two builder regressions failed before the first change; [x] shared builder role boundary, with unchanged admin policy and no additional media; [x] initial 617 focused API/bot/policy/provider tests passed; Ruff, compileall and diff whitespace checks passed; [x] OCR delegate selected 1/1 reviewable source and rules, with manual review of the excluded test/docs diffs; [x] PR #257 review flagged hardcoded behavioral identity wording outside the audited policy; a new RED regression reproduced the conflict and the shared builder now uses only structural labels plus the admin policy; [x] 618 focused tests, Ruff, compileall and whitespace checks passed after review fix; [x] follow-up OCR preview and manual review covered all changed source/test/docs files with no remaining blocking finding; [ ] resolve PR thread; [ ] exact-head CI and auto-merge; [ ] exact-merge-SHA Production Autodeploy and public health.
# Execution ledger — feed photo face fidelity, 2026-10-14

- Baseline: `cd8951b7cdeff7c7ade74748151286723a42d365` on `main`; branch `fix/feed-face-fidelity-20261014`. Production checkout has unrelated untracked diagnostics and `error.log`; work is isolated in a worktree.
- Evidence: completed task `neironych-image:5e5ceda9-f427-54ee-88f4-5ab95cd9e221` (generation 59458) sent the full creator prompt and one clear reader portrait to Nano Banana 2.1. No creator media was in references. The result adopted hair color but retained facial appearance close to the author. Thus the failure is model fidelity after correct routing, not a missing input. The current 796-character audited instruction is at the end of a 1606-character scene prompt. Provider contracts expose prompt and up to four images, but no verified identity-strength field.
- Intended outcome: improve identity priority for every compatible image model through the shared prompt composer, keeping the author's full recipe once and only reader media. Site, Mini App, and Telegram bot must use the same composition. Do not claim biometric likeness from synthetic transport tests.
- Acceptance: current admin instruction appears at the start and end of the provider prompt; full creator text appears once; no hardcoded behavioral policy is added; old v4 repeats unwrap to one current prompt without accumulating policies; tampered/foreign lineage remains rejected; model reference limits and billing are unchanged. The reported 1606-character recipe plus two 796-character policies is about 3.3k characters; provider-specific maximum prompt lengths are not documented in the verified contracts.
- Current state/reuse: `core.feed_remix_prompt.build_feed_image_recipe_prompt` is shared by API quote/submit and bot. `feed_recipe_identity_policy` is typed, validated, audited and admin-managed through authenticated API; v4 prompt digest binds provenance. Provider adapters send only supplied reference URLs. `FEED_ORIGINAL_RECIPE_ENABLED` remains the rollback control. No schema, price, permission, secret, model routing or integration change is required.
- Risks: repeating a long instruction adds up to 3000 characters; very long creator prompts need pre-charge validation. Automatic face cropping is deferred because the installed stack has no reliable detector and models have low common reference limits. Stronger text does not guarantee visual fidelity; a future quality study needs controlled paid comparisons with consent/accounting.
- Observability: existing generation/source/model/reference-count and provider task IDs trace calls without logging prompts, URLs or faces. Test seams: pure composer, authenticated v4 continuation, synthetic API/bot provider payload, admin setting and provider limits. CI gates: backend-quality, webapp, provider-contracts, bot-navigation; review and Production Autodeploy/public health on merged SHA.
- Steps: [x] read-only production diagnosis and visual comparison; [x] tools, skills, repository/config/auth/provider/test/CI preflight; [x] isolated worktree and ledger; [x] RED regression reproduced four failures; [x] minimal composer change; [x] 443 focused API/bot/security/admin/provider tests passed; [x] Ruff, compileall and diff whitespace checks passed; [x] OCR delegate selected and reviewed 1/1 source file; excluded test and ledger diffs reviewed manually, no blocking finding; [ ] PR, required CI, auto-merge, deploy/health verification.

# Execution ledger — feed prompt safety mitigation, 2026-10-14

- Baseline: `9f2ebe6834f1cc2009fadaeaa4f21c672f09f8e9` on `main`; isolated branch `fix/feed-prompt-safety-rollback-20261014`.
- Intended outcome: follow Google's reference-image prompting framework in the shared creator-recipe prompt for every compatible image model: direct creation request, explicit reference relationship from the administrator-controlled instruction, then the creator scene. Keep the complete creator scene recipe once, reader changes and only reader-uploaded references. A previous repeat with the doubled policy must continue with one current policy.
- Read-only production evidence: generation 59474 (Nano Banana Pro/Nexus) and 59473 (Nano Banana 2/Nexus) were rejected by the provider safety filter and refunded; 59475 and 59477 completed on Nano Banana 2. The recent double-policy change increased the reported prompt by about 823 characters. These observations do not prove the longer prompt caused rejection. Neironych generation 59469 has a separate HTTP 502 and unresolved provider status.
- Existing/reusable: `core/feed_remix_prompt.py` composes the shared prompt for API, Mini App and bot. Authenticated v4 provenance binds the saved prompt and prior admin instruction. The typed, audited `feed_recipe_identity_policy` admin setting and `FEED_ORIGINAL_RECIPE_ENABLED` rollback flag remain the control plane. No schema, price, authorization, provider routing or secret change.
- Risks: reducing repetition may affect likeness; the provider safety decision can also depend on creator text or reader media. No paid generation or private image inspection is needed for this mitigation. Avoid logging prompt or reference URLs. Existing task/source/model IDs and provider outcomes provide observability.
- Acceptance: new and continued prompts contain exactly one current policy and one creator scene in the Google-recommended reference-relationship-scene sequence; old double-policy, old single-policy and new relationship-first prompts unwrap without policy accumulation; provenance and reference isolation remain intact. RED/GREEN builder tests, focused feed/API/bot tests, required CI, review, auto-merge and exact-merge-SHA production health gate.
- Source principle: Google Cloud's Nano Banana guide recommends a clear action and a reference-images + relationship instruction + new scenario structure (https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana). Google's examples do not establish why Nexus issued the two safety rejections.
- Steps: [x] read-only incident and repository preflight; [x] isolated worktree and ledger; [x] RED builder regressions for single-policy and new relationship sequence; [x] shared composer and authenticated continuation guard updated; [x] 443 focused feed/security/Nano Banana API and routing tests passed; Ruff, compileall and diff whitespace checks passed; [x] OCR delegate selected/reviewed 1/1 source file and excluded test/docs diffs manually reviewed, no blocking finding; [ ] PR/CI/auto-merge; [ ] Production Autodeploy and public health.

# Execution ledger — immediate image HTTP 5xx settlement, 2026-10-14

- Baseline: `9f2ebe6834f1cc2009fadaeaa4f21c672f09f8e9` on `main`; branch `fix/neironych-image-5xx-immediate-fail-20261014`. User explicitly chose immediate failure and customer credit return after a provider HTTP 5xx.
- Intended outcome: every image launch route that receives an explicit HTTP 5xx from Neironych or Nexus marks that generation failed and atomically returns its customer credit, preserving the original provider correlation ID. Network loss without an HTTP response remains in reconciliation. Do not issue an automatic paid retry or switch providers. A late result must not change the terminal generation or refund twice.
- Evidence: generation 59469 sent a Neironych Nano Banana 2.1 POST with request UUID and got HTTP 502; two later provider GETs returned not_found, while APIX left the task processing and charged. Nexus image adapter currently wraps HTTP 5xx as outcome-unknown without status code. Live entry paths (site/Mini App regular image, feed remix, text bot) return processing on ambiguous errors. The separate `api/web/provider_operations.py` module is not mounted and currently has an unresolved import, so it is outside live product surfaces. Existing `fail_generation_and_refund` has row lock, pending/processing CAS, task-ID guard, refund ledger marker and one-commit settlement.
- Existing/config: Nano Banana 2.1 routing, prices and recovery deadlines are DB/admin controlled. The HTTP 5xx terminal rule is a fixed error-state semantic requested by the user, while the existing DB SLA continues for true unknown/no-response cases. No schema, secret, price or provider route change planned.
- Risks: providers can have accepted/charged the request despite HTTP 5xx; this policy deliberately favors immediate customer refund and can create supplier liability. No automatic retry or fallback. Preserve provider task identity and log generation/provider/status without prompt or reference URLs. Existing callback/poll settlement must remain terminal-state safe.
- Acceptance: explicit 500–599 failures settle immediately once across all live image surfaces/providers; connection timeouts remain processing; no second POST; exact task guard prevents settling a changed identity; user-visible state is failed/refunded. Unit/provider contract, API, bot, repository/idempotency and CI checks apply. Review and exact-merge-SHA autodeploy/health required.
- Steps: [x] read-only production incident and route/adapter/repository/config/CI preflight; [x] isolated branch and ledger; [x] RED Mini App Neironych 502/503 tests; [x] shared 5xx settlement and Nexus HTTP-status preservation; [x] 488 focused routing/recovery/API/feed/bot tests passed; Ruff and compileall passed; [ ] review and PR/CI/auto-merge; [ ] exact-merge-SHA deploy and public health; [ ] verify disposition of existing 59469.
- Merge/review update: merged main commit `72da293a11d1340985b424e3322c4f606833f5c8` (prompt structure PR #260) into this branch, retaining both ledger sections. All 490 focused cases then passed; Ruff, compileall and diff whitespace checks passed. OCR delegate selected 4/4 source files; reviewed each source diff plus all five excluded test/docs diffs. No blocking finding remains.
- Existing incident disposition: production generation 59469 remained processing with its original Neironych UUID and the provider again returned `not_found`. The repository's task-ID-guarded atomic failure/refund operation won the CAS, transitioned it to failed and refunded exactly 1.0 customer credit. A separate read-only check found `refund_applied=true`, one generation-refund ledger entry totaling 1.0, and the original task ID retained. No replacement provider POST was made.

## 2026-10-14 — image HTTP 5xx post-merge review follow-up
- Baseline: main `107d3a768123fa89207fe96b12cc6096e071abad` (PR #261), deployed by run `38640632537`, public health 200. Branch `fix/image-5xx-review-followup-20261014`.
- Review evidence: Codex posted P1 findings after merge: 5xx refunds lacked durable supplier review/late outcome tracking, and non-idempotent Nexus image models fell through a non-atomic refund path. P2 findings: Telegram lost-guard UI/zero-credit copy and feed share lost on callback race. New user task 59487 (Nano Banana Pro/Nexus) is failed by provider Safety Filter and has exactly one 1.5-credit refund; it is not a 5xx and yielded no image.
- Existing seams: atomic `fail_generation_and_refund`, Seedance supplier-review marker/admin pattern, signed Nexus image callback and canonical status fetch, Neironych image status GET, image reconciliation scheduler, admin-only routes. No schema migration or provider POST is needed.
- Intended outcome: all explicit image 5xx terminally refund once across site, Mini App and text bot; preserve an auditable operator queue for possible supplier cost; record authenticated late result without changing customer balance; show current bot state on lost guard; keep accepted feed-share count. Acceptance: focused regression tests and exact-head CI, reviewed PR, auto-merge, main Production Autodeploy, public health.
- Plan: [ ] RED tests for four review findings; [ ] minimal implementation and durable supplier review/admin controls; [ ] focused checks and OCR review; [ ] PR/required CI/auto-merge; [ ] exact-merge deploy/health. Observability: generation ID, provider, task ID/status and review state; no prompt, face image, URL or secret in new logs. Existing image scheduler interval/batch and existing admin authentication govern reconciliation; no new mutable hardcode.
- Feed repeat incident evidence: task 59487 used Nano Banana Pro/Nexus and was rejected by the provider Safety Filter, with one 1.5-credit refund; no image exists to judge facial likeness. Its saved request contains the creator prompt exactly once, the admin identity instruction exactly once, one reader reference, and no finished creator image in references or prompt. The source prompt contains no obvious adult/violence/minor keywords under a bounded local scan; this does not establish why Nexus filtered it. No private prompt, image URL or face was logged for this audit.
- Implementation progress: [x] durable image supplier-review marker in same atomic 5xx refund; [x] authenticated admin queue and resolution; [x] signed late Nexus callback accounting and Neironych post-refund polling/alert, without changing final customer state; [x] atomic plain Nexus 5xx handling across normal image/feed/bot; [x] Telegram lost-guard/zero-credit text and feed-share race fixes; [x] new SQLite refund/review/idempotency, scheduler, admin auth and feed/bot regressions. No schema, price, secret or route-selection change. Pending: broad checks, OCR, PR, CI, deploy/health.
- Feed repeat visual audit: task 59490 (Nano Banana 2/Nexus) completed with one reader portrait and no creator output media. Comparing the actual reader photo and result showed retained hair/eye color but visibly altered facial shape, nose, lips and skin tone. The creator recipe contains multiple facial/appearance descriptions, a plausible competing instruction. RED test reproduced the old order (identity policy before creator text). The shared composer now keeps the creator recipe verbatim once and places the single admin-managed identity policy after it; authenticated continuations unwrap both old and new layouts. This is a reasoned prompt-priority adjustment, not proven visual fidelity; a new authenticated result is required to judge it. No new provider POST was made in this audit.
- October 9 comparison: commit `5279532` (2026-10-09 00:07 +03:00) built image feed repeats from the creator prompt plus any reader change, and selected `user_refs` before source media for image generation. When reader photos were present, that code sent those photos without the finished creator image and without an extra identity policy. Later October changes added recipe wrapping and identity instructions. The user's report that earlier repeats worked better is consistent with the code history, but the old code alone cannot establish visual superiority across the current provider versions and source recipes. The new single policy follows the creator text and remains admin configurable; post-deploy output comparison is the acceptance evidence for fidelity.

## 2026-10-14 — restore October 1 image feed prompt contract
- Baseline: main `125afeef2d1c27a26f22a606513df6ca36fc61fa` (PR #262). User explicitly asked for the October 1 behavior exactly after reviewing the historical comparison. Branch `fix/feed-repeat-oct1-20261014`.
- Historical evidence: commit `246e3e6903aefecf125d40d75b102a1841e08c74` (2026-10-01 06:48 UTC) passed `source.prompt` directly to image generation and selected `user_refs` before public source media. Successful task 42457 stored the creator prompt verbatim (1837 chars, zero additions) and one reference; current task 59490 stored its 3796-char creator prompt plus 929 chars of added instructions. Different source recipes/models prevent treating this as a controlled image-quality comparison.
- Scope and acceptance: for personalized image feed repeats on site, Mini App and Telegram, use the original creator prompt without relationship header or face-policy text, and submit only reader-supplied references as separately required by the user. An explicit reader change remains appended only when present so it is not silently ignored; unchanged repeats must equal the creator prompt byte-for-byte after existing trim behavior. Keep owner-bound prompt provenance, source-media isolation, model/ref validation, credits and 5xx handling. Existing saved repeats with wrapped policies must unwrap on continuation.
- No migration or secret change. The existing admin policy row/route stays intact for compatibility but is not read by the October 1 image repeat path. Log generation/source/model/reference count only, never private prompt or media. Risks: face fidelity remains provider-dependent and requires a new authenticated output; no paid provider POST is made in tests. Steps: [ ] RED contract tests; [ ] route/bot/core implementation; [ ] focused tests and code review; [ ] PR/required CI/auto-merge; [ ] exact SHA production deploy and public health.
- Progress: [x] RED October 1 contract test; [x] bare creator prompt on site, Mini App and bot; [x] legacy saved policy unwrapping and owner-bound provenance retained; [x] broad feed, prompt security, provider transport, reference privacy, quote/prelaunch and session tests passed; [x] Ruff, compileall and whitespace checks. PR #262 main merge `125afeef2d1c27a26f22a606513df6ca36fc61fa` finished Production Autodeploy run `38643983784` successfully and public health returned 200 before this rollback branch. Existing task 59469 was guardedly registered for supplier review after that deploy: still failed, `refund_applied=true`, review pending for Neironych, one 1.0-credit refund ledger entry. No extra provider POST or balance change.
- Review: OCR delegate selected all three changed source files; manually reviewed their complete diffs plus all excluded tests/docs for privacy, provenance, continuation, model parity and billing. Removed obsolete policy imports and test monkeypatches, and removed unused composer parameters. No blocking finding remains locally. Pending exact-head GitHub CI and a real postdeploy face-quality result.
- Verification/review: full focused Nano Banana/feed/refund/callback suite passed; Ruff, compileall and whitespace checks passed. OCR delegate selected 8/8 changed source files; each source diff and five excluded test/docs diffs were manually reviewed against its rules and the PR #261 findings. No remaining blocking source finding identified locally. New feed prompt order is shared by site, Mini App and Telegram bot; none of the three surfaces sends creator media in v4 recipe replay.
# 2026-10-15 Qwen video sampling contract

The active video-to-prompt route sends an MP4 URL to KIE Gemini 3.1 Pro. Its verified API contract does not accept an FPS sampling field. Explicit FPS requests fail before any paid provider call; the former `COMET_VIDEO_PROMPT_FPS` setting was removed from current configuration. The archived 2026-10-09 release note describes the previous Comet implementation.
# 2026-10-16 — Trend run reliability

- Baseline `b8aad29eed99f1bfae906c39f7f1762008d5aa43` on `main`; branch `fix/trend-run-reliability-20261016`, isolated worktree `/root/agent-work/apix-trend-run-reliability-20261016`. User authorized fixing three audit findings and release through protected-main PR.
- Current state: authenticated trend checkout quotes from model tariff; `/trends/{id}/run` omits Wan's mandatory confirmed price, defaults video duration to 5 (invalid for Gemini Omni), and stores its idempotency marker only after the generation call. Existing tests cover generic trend contracts and checkout but not these end-to-end failure paths. Production CI/deploy on baseline succeeded; no paid provider call is authorized for this fix.
- Outcome/acceptance: checkout and run agree on Wan price, a changed price returns 409 before charge, valid Gemini duration is used or bad admin settings are rejected, concurrent same-key requests create at most one paid task; duplicate success returns the original task and ambiguous outcome fails closed. Site/Mini App and bot parity will be checked; no prompts/media/secrets enter logs or claim rows. A new claim table and unique `(user_id, key)` index require Alembic migration; no tariff or secret changes. Observability: claim state, trend/generation IDs and failure class without input media. Test seams: authenticated API, repository concurrency, quote and provider mocks, migration. Rollout: main CI migration then health; revert app code via PR if needed, preserve claim table for audit.
- Steps: [x] API behavior, migration, bot and SQLite concurrency regressions added (10 pass); [x] shared Wan quote/confirmation from active resolution tariff, including default-resolution parity, and Gemini validation; [x] durable claim migration and API integration; [x] 53 focused Python cases, 74 Wan contract/routing/quote cases, 114 web unit cases, typecheck/build, two Desktop browser trend cases and 25 trend user journeys passed; [x] source/test/migration/security/parity diff reviewed with no unresolved high-severity finding; [ ] PR, required exact-head CI, native auto-merge; [ ] merge SHA Production Autodeploy and public health.
- Local wide `test_webapp_routes.py` still has baseline legacy failures, including `test_trend_checkout_quote_recommends_smallest_plan_covering_deficit`; that exact case also fails on untouched baseline `main` with HTTP 422. No failing test was removed or softened. The maintained CI gate remains intact and now includes the new reliability suite.
- First exact-head `backend-quality` run found one migration-head assertion still pinned to 043 in the photo-1 migration contract. The assertion now expects the additive 044 head and verifies 044→043→042→041 lineage; no production behavior or previous migration was changed. CI rerun pending.
- Parity: Mini App and site use the shared authenticated trend runner; Telegram trend action opens that same runner for video, while Telegram admin duration buttons now exclude invalid Gemini choices. Image trend execution remains on the same guarded API path. No provider pricing, secret or existing customer row is modified by this branch; migration adds only the claim table.
- PR #275 exact-head CI on `6ad1783` passed all required backend-quality, webapp, provider-contracts and bot-navigation gates plus user-journeys. Automated review raised four actionable conversations before merge. Follow-up: definitive 402/429 pre-provider rejection releases its unique claim for retry while ambiguous outcomes keep the claim; stale quote 409 has a typed code and Mini App refreshes checkout without reupload; legacy admin form restricts Gemini duration options; stored Gemini 5-second trends continue to normalize to four seconds while new/edited settings with five seconds fail validation. Added API, repository and browser regressions. Review conversations, amended exact-head CI, merge and deploy remain pending.
- Final verification: PR #275 was squash-merged to `4d0bd4e2b8d9103414d9df6953c288ccc08fc1ee`. All four review threads were resolved. Exact-head checks passed: backend-quality, webapp, provider-contracts, bot-navigation, user-journeys and pinterest-backend. Main-SHA APIX CI/CD run `38811511463` passed backend-quality, webapp, bot-navigation and Production Autodeploy; separate provider, user-journey and Pinterest workflows passed on the same SHA. Public `https://apixbotai.com/api/v1/health` returned HTTP 200 with `{"status":"ok"}` after deploy. Local follow-up verification: 60 focused Python tests, 114 web unit tests, typecheck/build, Desktop stale-quote browser regression and Ruff passed. The additive migration `044_trend_run_claims` deployed through main CI. No paid provider request was made during verification.

# 2026-10-16 — Full repository audit and documentation refresh

- Baseline: `b4e62a1a8b24a8a3df0e940a19fda41aa1446329` on `main`; isolated branch `audit/full-project-20261016`. The production checkout has unrelated untracked diagnostics and `error.log`, left untouched.
- Intended outcome: an evidence-backed, prioritized cross-project audit of site, Mini App, bot, backend, billing, model/provider contracts, persistence, security, operations, test gates and documentation; refresh misleading entry-point docs without changing product behavior. Acceptance: reproducible checks and exact evidence for each finding, documented coverage limits, reviewable docs PR, required exact-head CI, merge-SHA autodeploy and public health.
- Current state: recent main-SHA CI/deploy succeeded after trend reliability PR #275 and ledger PR #276. The root README and `artflow/README.md` contain stale architecture/setup claims, including old route names and nine migrations despite current migration 044. Existing `docs/current_surface_inventory.md` identifies the current frontend entry points. `docs/provider_contract_coverage.md` is a dated snapshot, not live tariff or production proof.
- Audit plan: (1) inventory code/docs/schema/auth/config/tests/CI and available runtime evidence; (2) run safe static, migration, provider and maintained test checks, then targeted broad tests; (3) inspect high-risk flows for defects with code-level evidence; (4) write prioritized audit and update onboarding docs; (5) review documentation diff and deliver through protected-main PR. No migrations, paid provider calls, customer data writes, configuration changes or user-visible behavior are planned. Observability: CI/job IDs and public health, without secrets or personal data. Test seams: existing provider-contract, auth/payment, bot-navigation, backend and browser gates.
- Progress: [x] baseline/worktree and repository instructions; [x] external tool repositories updated and relevant audit/documentation guidance read; [ ] inventory/checks; [ ] findings and docs; [ ] review/local verification; [ ] PR/CI/deploy/health.
- Inventory/check evidence: 193 FastAPI OpenAPI paths, 98 provider contracts, Alembic head 044, 225 backend test files. Public `/health`, `/api/v1/health`, `/app/` and `/studio.html` all returned 200. Provider inventory, registry readiness, smoke manifest dry validation, compileall, deploy shell syntax, landing JS syntax, web build and 114 web unit tests passed. Full pytest: 3263 passed, 44 failed, 13 skipped; full Ruff: 27 findings outside maintained CI. Six focused trend/repeat/payment modules: 114 passed. No paid provider or production DB action.
- Findings: P1 refund status/balance race and partial T-Bank reversal; P1 text-bot photo trend without user photo/common claim. P2 full-suite debt, provider payload logging, static Tribute product mapping, inconsistent provider surface inventories, stale docs and duplicate OpenAPI health operation IDs. The metadata-only OpenAPI ID issue is fixed here; other runtime findings are documented for separate code fixes. README, trend/API docs, generated OpenAPI and provider coverage are refreshed. No migration, price, admin setting, secret, permission or rollout behavior changes except unique OpenAPI metadata; site/Mini App/bot runtime behavior is unchanged.
- Review/checks: OCR delegate preview selected 5 source/config/JSON files; rules resolved, generated JSON validated, Markdown/test diffs reviewed manually. OpenAPI unique-ID test passes and is in maintained CI. Two independent OpenAPI exports matched byte-for-byte; generated provider dashboard `--check` passes; relative Markdown links pass. [x] inventory/checks; [x] findings and docs; [x] local review/verification; [ ] PR/exact-head CI; [ ] merge-SHA autodeploy/public health.

## 2026-10-18 - native admission 503 misclassified as paid outcome unknown

Baseline `0da8798d42dafbe2ba721bebcb85fe186605026b`, isolated branch `fix/seedance-admission-rejection-20261018`.
Fresh APIX and Neironych logs correlate Seedance rejection at 09:24:34 UTC and repeated Qwen photo-prompt 503 failures at 09:42-09:49 UTC with `native_inference_rejected`, stage `provider_capital`. No media, prompts or credentials are stored here. The APIX local row remains a submission marker; prior examples have one automatic timeout refund each. No live provider POST, manual financial adjustment or routing override is authorized/performed by this work.

Provider baseline `Bambale0/ooo@50963d35033497d5014b830bf3a1eda263d72402` was read: reserve locks the partner and checks existing idempotency before capital admission. Admission raises HTTPException with the exact FastAPI `detail` string; router attaches a UUID X-Request-Id. Once admitted, the native video route returns 202; synchronous downstream errors instead use the `error` envelope and generation request_id. These are different contracts, not an HTTP-503-wide retry permission.

Outcome: recognize only this verified pre-admission 503 shape, using the existing configured single KIE fallback for new Seedance requests and the existing Qwen fallback policy. Generic/proxy/malformed/accepted-generation 5xx and transport loss remain unknown and never get a second paid submission. Existing unknown jobs are not replayed. Preserve references, idempotency markers, prices, customer finality and provider-capital protection.

Test seams: actual HTTP clients with in-memory transports -> configured router; shared photo prompt service -> configured backup; negative 5xx shapes/timeouts; real Seedance 2/2.5 fallback payload and persisted marker contract; maintained backend/provider/navigation gates. All site/Mini App/bot callers share these adapters. No schema, new business setting, manual balance or upstream capital change is needed. Observability: safe local request ID and supplier trace UUID, classification and HTTP code only.

Steps: [x] fresh logs and current code/instructions; [ ] RED regression; [ ] minimal classification fix; [ ] focused/regression gates and review; [ ] PR, exact SHA CI, normal auto-merge/deploy, runtime identity and smoke. Separate audit PR #279 is not mixed into this incident branch.

Progress: classifier RED was 3 expected failures / 22 safe negative cases. After minimal classifier changes, 120 focused tests passed. A real SQLite handoff probe then found the existing `before_kie_submit` callback was wired only for Wan, not the three Seedance KIE submission sites. All 3 probes failed before the fix. The shared fallback-only hook now transfers the exact submitting Neironych marker to KIE immediately before POST; the KIE-primary path is unchanged. Expanded accepted/timeout/persistence-failure cases and surrounding suites: 136 passed. A cross-repository in-memory ASGI probe against the exact gateway source plus its diagnostics suite passed 18 tests, proving capital refusal creates no Generation or upstream POST and accepted idempotent replay wins before capital checks.

Full Ruff, changed compilation and diff checks passed. The maintained backend suite ran 2036 passing tests, with 2 environmental guard failures because the task-owned disposable database name differed from `apix_session_migration_test`. Follow-on DB-setup and local test commands were blocked before execution; no blocked command was retried or protection weakened. New regressions are added to maintained backend/provider CI. Exact-head CI must prove its own correctly named disposable-service tests before normal PR merge. No production data, credentials, procurement holds or routing settings changed. See `docs/seedance-admission-recovery.md` for the precise error-shape contract and remaining live-verification boundary.

PR #281 initial exact-head required CI passed, including the correctly named PostgreSQL tests. Independent security review passed. Code review found missing immediate reconciliation after failed KIE handoff: a started primary context must not use the original pre-submit exception handler. Three RED cases reproduced this, plus one committed-journal/lost-ack case. The fallback-only helper now raises the existing uncertain-submission signal; recovery matches persisted KIE identity when commit acknowledgement was lost, and otherwise marks the original attempt for reconciliation. Existing scheduler prefix/timeout safeguards remain. Revised focused run: 115 passed; Ruff/diff checks passed. Updated revision still requires exact-head CI and review resolution. No provider replay, live payment, direct balance edit or production checkout change occurred.

## 2026-10-18 - finish audit PR #279 after the Seedance incident release

Owner requests completion, not only status reporting. Starting audit head `1adf9f188c2007239065cf55523654bf838e86ce`, production/main `8f05e2d2adbd8f2ace895ca10b934dd616753db4`. Current live Seedance query since 10:30:02 UTC and all pending/processing jobs returned zero at 11:01:53 UTC. New Qwen admission classification is observed in real logs; completed fallback responses still need correlation. Hourly read-only Seedance monitoring was explicitly authorized and created.

The audit PR has green old-head CI but conflicts in the backend test gate with released PR #281. Merge current main into the existing isolated audit worktree, preserving all incident fixes. Resolve the sole conflict by retaining full pytest plus an explicit new admission regression step; no assertion, protection, or test is removed. Verify original five code-review findings against the amended implementation, re-run full tests/migrations/browser/API checks, request independent re-review, and only then protected squash merge/exact-SHA deployment verification. Production checkout, customer balances, procurement holds and routing config are not edited manually. Additive migrations 045/046 are delivered only by the authorized normal release and retain refund/catalog audit evidence; rollback remains forward repair. Prior real-bank/live-AI limitations remain explicit.

Combined verification: full pytest **3496 passed / 0 failed / 0 skipped**, 3 pre-existing dependency/mock warnings. Full Ruff and YAML parse passed. Actual full Alembic chain from empty test public schema reached `046_tribute_catalog`; the full-suite roundtrip guards preserve original money and admin/refund evidence. Frontend units **114 passed**; fresh-build catalog and Seedance deep-link browser scenarios **20 passed** across all four Chromium device/viewport profiles. Provider registry/readiness/dry smoke **98 contracts**, two independent deterministic OpenAPI exports and committed JSON match at **195 paths**. Python compile, JS syntax, deploy shell syntax and diff check passed. All five old review findings verified against code and regression cases; new exact-head review/CI is next. Test resources: only task-owned `apix-finish-pg-20261018` at loopback port 55484 and dedicated `apix_session_migration_test`. No live AI or payment POST, production DB mutation, manual checkout/restart, price or procurement-hold change.

## 2026-10-19 - repair Wan public feed repeat quotation and submission

Baseline: `f1cfa8eb2797d825389df4c5819ed504956adae8`. Isolated unprivileged clone `/tmp/apix-wan-repeat-user-20261019`, branch `fix/wan-feed-repeat-20261019`; no deployment checkout or secrets copied. Initial privileged preparation was denied; no policy changes/retries of that preparation. Root/local AGENTS, debugging/TDD/verification guides and focused engineering/webapp guidance inspected.

User report: Wan repeat does not work, requested account opens source 61270. Previous read-only evidence found four other-account repeat attempts rejected with `Wan 3.0 requires a verified quoted request`, no supplier IDs, one refund each; do not misattribute them or put private prompts/media in fixtures. Source has canonical `wan30_request` edit inputs. Cause remains in current main: feed quote/launch use generic duration pricing and omit `wan_request`; ordinary Wan checkout already has strict per-quality pricing, locally measured refs and the typed request.

Outcome: feed quote and launch use the existing Wan constructor/tariff resolver before debit; preserve source operation/settings/video/audio materials while reader photos replace author identity inputs; no finished MP4 as an input recipe. Both Wan and Prime, web/Mini App/shared Telegram feed behavior covered. Bad/missing media, stale/missing price, disabled tariff or invalid combined duration must fail before spending/provider work. Keep signed callback/durable fallback/unknown-outcome handling; no paid replay, manually altered balance, model routing or migrations. Existing source refs are reconstructed only from stored recipe, never supplier GET. Update applicable docs with every code change.

Steps: [x] current code/contract/entrypoint inspection; [ ] RED route/payload/privacy/billing regressions; [ ] minimal shared repair; [ ] focused/full CI and review; [ ] protected PR merge/deploy/production checks. No live provider POST is authorized by this task.

Progress: real HTTP RED reproduced the missing typed Wan request; additional RED covered storage failure and Telegram mode/setting parity. Canonical quote/launch and shared server-side recipe restoration implemented. Original media durations are freshly measured; inactive/missing/mismatched prices fail before debit. Unknown supplier responses retain the original recovery handlers, no paid replay/refund. New backend regressions: 30 passed; earlier related set 253 passed. Full local set before final 3 cases: 3459 passed / 64 dedicated-environment skips / 0 failed (3 existing warnings). Browser fresh-build 8/8 Wan/Prime cases across 4 Chromium profiles passed; frontend units114. Ruff, unchanged OpenAPI195, provider98 dry validation passed. Test examples are synthetic; no customer prompts/media, wallet changes or provider POST. Additive provider CI step protects feed/Telegram/quote/durable handoff regressions. Await exact-head full CI, independent review, protected PR merge and production checks. Full source/behavior notes: docs/wan30_feed_repeat.md.

PR #282 review amendment: reject unknown public Wan video input provenance before the generic public-output fallback. Independent P2 finding reproduced by 18 failing cases (normal/Prime x web/Mini App/bot x missing/empty/malformed snapshot); fixed at shared API and bot preparation boundaries. 48 new cases total; related amended suite232passed, Ruff clean. Original source61270 independently probed read-only: original video14.239sec, output15sec, combined29.239 valid; no private URL/prompt output. Current full exact old-head backend/provider/navigation CI passed. Updated head must pass its own CI and independent review before normal release. Initial in-memory and previous full-suite results are not substituted for updated-head results.

Second independent P2 review finding fixed: Telegram Wan quote now catches OSError/RuntimeError from media preflight and returns a retry message before debit. Four failing-then-passing tests cover both models/error classes and no save/debit/supplier calls; 52 new cases total. Full Ruff passed, related Wan set85passed. These review amendments change only pre-charge failure handling, not payment execution or supplier retries.

Final review-amended local full suite: 3484 passed / 64 dedicated-service skips / 0 failed; 3 existing warnings. These cover the final 52-case regression module. Exact-head GitHub CI must prove its actual PostgreSQL/Nginx checks before release.

## 2026-10-20 — Telegram repeat confirmation length

Baseline: `7277ea5`; branch `fix/telegram-repeat-message-length`, isolated worktree. Production traceback at 14:39:49 MSK shows `open_repeat -> _prepare_repeat -> answer(_confirmation_text)` rejected as `message is too long`. Renderer includes entire saved prompt; feed edits can also exceed the message budget. Existing handler tests mock Telegram and miss this constraint.

Acceptance: opening/editing repeat sends valid escaped HTML within Telegram's 4096 UTF-16-unit text budget for supported model/settings. Short text stays complete; previews are marked when shortened. Full source/edited prompts stay in FSM and launch. Hidden author/Pinterest prompts, prices, reference warnings, authorization and idempotency remain intact.

Parity: telegram_bot fixed here; site (`landing/js/prototype-premium.js` repeat/variant action) and mini_app repeat setup render browser text, not this Telegram confirmation, so this protocol limit is inapplicable. No schema, integration, credential, business configuration, balance mutation or paid provider request. Message length is a protocol constraint. Existing error logging remains the signal; no prompts logged.

Steps: 1. [x] runtime/code/tests/CI audit; 2. [x] RED: original 2 short cases pass, 4 oversized Cyrillic/emoji cases fail at the parsed-message length assertion; 3. [x] bounded previews and Unicode/feed-edit/full-launch/hidden regressions (23 handler tests pass); 4. [x] 476 focused repeat/reference/ownership/identity/Wan tests pass, full Ruff, py_compile and diff checks pass; [x] independent reviewer found no actionable defects and independently reran all 23 handler tests; 5. [ ] required CI, native auto-merge, exact-SHA autodeploy and health.

Skills: `.clinerules` systematic-debugging/requesting-code-review; Bambale0/skills TDD; claw QA checklist; wondelai working-with-legacy-code test seams. Anthropic webapp-testing inspected, inapplicable to Telegram rendering. Existing handler test seams are within the user's fix authorization.

Delivery: PR #286, implementation commit `922167d`; exact-head CI/merge/deploy evidence pending.


# Kling 4 final pre-delivery evidence

Full amended Python gate: 3728 passed, zero skips, three existing warnings. Ruff, compileall, diff whitespace, 100-contract inventory/readiness/manifest all pass. Focused Playwright: Mini App 3/3; Studio 8/8, including owned typed recipe restoration on four viewport/device profiles. Frontend unit/build passed; broad browser regressions running.

Site history repeat now restores the owner-authorized generation-ID recipe including nested roles, duration and resolution; protected creator prompts cannot be exported. Telegram edit/material controls bind the current draft revision; launch additionally binds the quote token. Additional RED regressions reproduced stale-index edits, changed-intent replay and recipe ownership, then passed. Independent Standards and Spec reviews rechecked amendments and report no remaining blockers. OCR selected 44 source files; all source rules and diffs reviewed, excluded tests/docs reviewed manually; pre-existing diagnostics/error.log excluded. PR, exact-head CI and autodeploy pending. No public rollout or manual production rebuild.

PR #290 opened with native squash auto-merge. Final parity review reused the existing shared six-active-generation limit instead of a separate Kling-specific value, and corrected the bot's immediate definite-refusal receipt to explicitly report the returned credits. Sixteen focused transaction/API/bot tests passed after that small amendment. Auto-merge is briefly unqueued while publishing the amendment, then re-enabled; all required checks must pass on the amended SHA.

## 2026-10-23 — verified Wan Neironych primary, KIE standby

Baseline `0112499faca7c403408c43c6297787010871d61d`; branch `fix/wan30-neironych-only` predates clarification. User confirmed Neironych primary and KIE fallback. Fresh code/config/contracts/quote/billing/UI/CI audit: current empty model defaults skip primary; authenticated live catalog now offers `wan-3` and `wan-3-prime`. Public guide verified. Standard synthetic 2s/480p/no-audio request accepted by real primary; Prime rejected same input with 422 before acceptance (current contract requires >=4s, fixed ratios and audio). KIE handoff stopped before paid POST because smoke has no KIE journal; no KIE purchase. Correct Prime smoke uses 4s/16:9/audio-on with separate durable local journal.

Acceptance: verified typed configurable model defaults activate Neironych for compatible requests; KIE remains standby for incompatible parameters/unavailable mapping/catalog membership/definite rejection, never unknown acceptance. Preserve billing, durable admission, ownership, pricing and history. Prime default selects compatible 16:9 for new drafts; explicit saved choices retained. No migrations, new permissions or source of truth. Existing env mappings remain overrideable. site/mini_app/telegram_bot share backend. Observability: provider-tagged task IDs, existing safe logs; synthetic smoke local fsynced journal, no customer data or APIX wallet changes.

Test seams: existing public provider/router/config and contract builders; negative unsupported Prime cases, normal/Prime success, safe fallback/timeout/durable journal regression, surface defaults. Skills: local TDD + Bambale0 TDD; claw QA map; OCR host review. Anthropic webapp-testing inspected for relevant browser checks. Steps: [x] current audit/catalog/guide; [ ] RED regression; [ ] minimal config/contract/default patch; [ ] checks/live acceptance/completion/review; [ ] PR/exact-head CI/native auto-merge/autodeploy/public health. Risks: runtime env overrides; provider acceptance is not completion; current Prime native contract is narrower than KIE; standard edit contract now disallows fixed duration so keep such operations on KIE rather than change billing semantics.

Progress: config seam RED reproduced both defaults bypassing primary; green after verified IDs. Native contract RED reproduced 12 unsupported Prime/edit/payload cases; added strict compatibility and preserved original KIE payload. Telegram default RED reproduced adaptive Prime and passed with 16:9. Additional documented-body RED caught leaked `mode`; removed it. Two initial accepted smoke jobs failed definitively upstream with `argolink_400`, confirmed by read-only provider attempt rows; both are `not_chargeable` and had no APIX wallet charge. Corrected documented 5s/720p bodies accepted for both verified models and reached `done`, with 5 billed seconds each. No fallback POST after accepted jobs, no replay of unknown work. Runtime preflight confirmed both mapping env variables unset in production, so shipped defaults will apply; no server env/checkout edits performed.

Verification: full local pytest exited 0, 3670 passing progress cases / 81 dedicated-environment skips / 3 existing warnings. Focused final native/route/provider/durability/bot suite: 135 passed. Full Ruff, provider contract inventory and diff checks pass. Frontend units 119 passed, typecheck/build pass (existing bundle-size warning), fresh-build Prime quote/default/explicit-adaptive browser test passes 4/4 viewport/device profiles. OCR selected 5 source files; host reviewed all source rules/diffs plus excluded tests/docs/env/CI manually, no unresolved high/medium findings. No migrations or pricing changes. Delivery pending PR/exact-head required checks/native auto-merge/main autodeploy and public health.

Post-merge review: PR #293 merged as `2c8fd8e7a9f3945cfcb10aedc8e7c2f09065010c`; two late P1 comments were discovered before deploy: absent Neironych credential bypasses safe KIE standby, and mutable WAN provider/mapping choices lack DB-backed authenticated control. Main workflow `39921456846` cancelled before deploy; no production runtime update. Follow-up branch `fix/wan30-runtime-control` starts from merge SHA. Resolve both before resuming protected release. Extend existing audited control-plane pattern with dedicated Wan routing records (model, primary, KIE standby flag, native model ID, revision, authenticated actor/source); seed verified IDs once, runtime reads DB, admin edits require optimistic revision and current primary catalog verification. Preserve all prior no-replay/billing behavior. Shared authenticated web admin form serves site/Mini App/Telegram entry; server authorization remains mandatory. Add migration and integration/auth/credential/standby tests and refresh OpenAPI. No direct production config/SQL/build.

Follow-up progress: real missing-key regression reproduced catalog failure before safe standby; fixed by credential-gated primary selection. Added DB policy/mapping/revision/audit with migration048 and guarded web control; shared form links shipped for site/mini_app/telegram_bot. SQLite real migration upgrade verifies both seeds, persistent runtime policy changes, atomic audit, stale revision rollback. Unauthorized GET/PUT rejected before DB access; unadvertised and cross-family/version/variant mappings rejected before write; KIE-only admin save works without primary key/catalog. Core/router/provider amended focused suites pass. No primary policy change can cause fallback after unknown/accepted work. New admin browser auth/save/switch/conflict/no-replay coverage 8/8 across all four viewport profiles; frontend119 units and fresh-build typecheck passed. First full local follow-up run 3681passed/81dedicated skips/0failures (3 existing warnings); final extra mapping/admin cases and exact-head CI must also pass. Independent reviewer requested via local requesting-code-review skill: reviewed source/migration/auth/CAS/journals/client handling, independently reran30 tests; family mapping finding fixed, final approval with no remaining high/medium findings. OCR selected12 source/generated files; manually reviewed additional tests/docs/CI/env. OpenAPI export now199paths, includes the new Wan endpoints and previously missing Kling4 schema entries. Final protected release pending.

Final follow-up local verification: full pytest3684passed/81dedicated-environment skips/0failed/3existing warnings in34.32s; focused31passed; Ruff/compile/JS/YAML/diff checks pass, provider inventory/strict100contract coverage pass, admin browser8/8 and frontend119 units/build pass. Independent review approved latest code with no unresolved high/medium issues. Migration048 real upgrade+seed+CAS/audit roundtrip verified in isolated SQLite; required exact-head CI remains responsible for complete PostgreSQL migration/service guards. No additional paid requests; both previously corrected Wan/Prime outputs downloaded and ffprobe verified. No production deployment yet. Ready for protected follow-up PR; original review threads will link these fixes and be resolved after exact-head review.

PR294 exact-head required CI passed, security review clean; automated code review identified seed compatibility: explicit empty mapping/custom native alias must survive bootstrap. Actual SQLite RED reproduced overwritten custom ID before checking disabledPrime. Migration048 now reads effective mapping settings once, preserves aliases, and stores kie_only for an empty disable switch; no live deployment has run. Regression plus existing seed/CAS/audit/provider/route/auth checks pass on amended code. Runtime remains DB-authoritative after bootstrap. Follow-up independent amendment review and exact-new-head CI/review required before native auto-merge.

Second migration amendment: rerun review found legacy arbitrary aliases (e.g. real-wan) would be stored active but rejected on every DB read, blocking runtime/admin. Four actual SQLite RED cases reproduced this for unknown/Wan2/wrong-variant/Wan30 aliases. Bootstrap now applies the same family/variant validation before insertion: compatible Wan3 aliases persist; empty/incompatible aliases become safe kie_only with a valid inactive native default so the editor remains usable. No live config/DB edits. An unrelated CI Seedance Node subprocess exceeded its existing5s startup budget on b7fb760; exact local test passed and failed-job-only CI rerun was requested without changing limits/tests. Amended SHA requires its own exact-head CI and review.

## 2026-10-23 — Kling 4 automatic Telegram references

Baseline `5fe1e289eeea19af6b0cacda30eff68188dd5796`; branch `fix/kling4-bot-auto-references`. User requests one Kling 4 entry, automatic reference handling analogous to other video models, references only in the bot. Fresh inspection: dedicated Kling editor currently separates reference/keyframe models and requires selecting upload roles; Seedance 2.5 already collects mixed attachments automatically. Shared checkout validates media ownership, provider payloads, active DB tariffs, access policy, exact quote and idempotent intent. Dispatcher serializes per-user events. CI maintains full pytest, provider contracts, browser and navigation gates.

Acceptance: one Kling 4 model in all Telegram catalog groups; /kling4 and old model/start buttons open reference input directly; text/photo/video/audio accepted without role selection, including media captions; validated type chooses reference role; edits invalidate old quote/intent; explicit price confirmation still precedes paid generation. Optional character/voice bindings remain available as advanced reference controls. Preserve rollout/auth, DB tariffs, upload ownership, history, provider no-replay and recovery. No migration/config/admin permission changes or paid smoke needed. Observability uses existing upload/checkout diagnostics without logging media/prompts.

Parity: telegram_bot intentionally simplified per explicit request. site/mini_app retain the full reference/keyframe studio and unchanged shared billing/validation. No provider or price hardcoding; Telegram workflow choice is product UI scope. Existing schema and API support both provider models for other surfaces/history.

Skills/guidance inspected: local TDD/requesting-code-review; Bambale0/skills TDD and code-review; claw QA checklist; wondelai legacy test seams; Anthropic webapp-testing (browser surface unchanged); OCR host review. Managed runtime tool unavailable; local executor used with inherited network configuration.

Steps: 1. [x] current code/contracts/auth/schema/admin/CI audit; 2. [ ] RED navigation test; 3. [ ] unified entry and automatic media/text slices with regressions; 4. [ ] focused/full checks and independent standards/spec review; 5. [ ] PR/exact-head CI/native auto-merge/deploy/public health.

Progress: RED menu tests reproduced both entries/split label; RED command/old-button tests reproduced chooser/keyframe mode; RED automatic attachment tests reproduced missing photo/video/audio collection. All slices now pass. Real installed-router tests cover direct prompt editing in edit/confirm, mixed photo/video/voice/document ordering and caption prompt, real provider payload building, rejected-limit draft atomicity and stale quote invalidation. Independent review caught restored legacy keyframe orders receiving reference fields; RED regression reproduced contamination, fixed by retaining explicit legacy frame controls and refusing unassigned uploads before storage. New entries remain reference only. History model/tariff is never silently converted.

Host OCR review: all four selected source files reviewed against resolved Python rules (4/4, 100%); tests/docs reviewed manually; pre-existing untracked diagnostics/error.log excluded. Independent reviewer rechecked source, tests/docs, router wrappers, authorization, draft atomicity and checkout identity: no remaining blockers; 31 bot/API tests passed independently. Focused Kling/navigation/model-label suites passed (environment-specific PostgreSQL cases skipped); provider inventory, full Ruff, compilation and diff checks pass. First full pytest exited 0 with existing environment skips and three baseline warnings; final full run with explicit summary in progress after legacy amendment. No paid generation, production SQL/config, migration, deploy checkout edit or direct main push.

Final local verification: amended full pytest **3702 passed, 81 dedicated-environment skips, 0 failures, 3 existing warnings** in34.58s. All17 Kling bot regressions pass, independent bot+API31pass; full Ruff, Python compile, provider inventory and whitespace checks pass. Steps2–4 complete. Required exact-head CI must supply PostgreSQL/service and browser gates. Delivery step5 remains pending PR checks/native auto-merge/main autodeploy/public health.

PR295 automated review added two P2 findings before merge; auto-merge disabled while fixing. Eleven RED regressions reproduced slash commands consumed in edit/confirm and over-limit image/video/audio files stored before validation. Text collection now lets slash commands reach existing routers. Automatic uploads check the collection's maxItems from the existing typed Kling4Input schema using the same extension classification as storage, before downloading/writing. All28 bot tests pass; amended full gate/re-review running. No duplicated quota settings, new migration or runtime control needed.

## 2026-10-23 — unify Kling 4 site / Mini App / bot

Baseline `9cd74d3b7daa6fdf179e0992cc6618f3c9d4efd8` (PR295 verified production/deploy success and public health in prior delivery). User explicitly requests website and Mini App parity with the shipped automatic Telegram reference flow. Branch `fix/kling4-unified-surfaces`. Fresh audit: site uses prototype-premium catalog + Kling studio extension; Mini App uses GenerationScreen + typed Kling4Materials/API; both still expose keyframe choice and separate upload roles. Server already measures and returns image/video/audio kind; shared checkout validates owner, caps, rollout, exact tariffs/quotes/idempotency. Typed recipes and legacy frames are retained in history; no schema/provider contract change is needed. Auth/admin pricing/access controls and CI inspected.

Acceptance: one new-order Kling4 choice on all three surfaces, one mixed-reference uploader on site/Mini App, authoritative returned kind determines role; no manual text/image/video mode selection; optional character/voice controls remain secondary. Preserve uploaded references on batch errors, block launch while uploading, fail closed on invalid media response, preserve account/model isolation and limits. Existing saved keyframe orders retain explicit frame-role editing and tariff with history labels; never silently convert old paid recipes. Price confirmation, auth/ownership, server validation and no-replay unchanged. New browsing does not advertise keyframe model. Site/Mini App names and flow match Telegram; regression-check bot too.

No migration, new secret, mutable price/routing/config or rollout permission change. Quotas remain existing provider contract caps; server remains authority. Existing upload/quote/submission diagnostics apply; no new sensitive logging. Skills: local TDD, frontend-data-contracts (use existing API boundary), requesting-code-review; Bambale0 TDD/code-review; claw frontend QA checklist; wondelai legacy seams; Anthropic webapp-testing. Sites skill inspected, inapplicable to existing repository-hosted product; retain mandatory GitHub/autodeploy delivery.

Steps: 1.[x] fresh discovery/acceptance/parity; 2.[ ] RED catalog + automatic media slice; 3.[ ] site and Mini App implementation with owner/error/legacy regressions; 4.[ ] unit/build/browser/backend/provider checks, OCR + independent review; 5.[ ] PR/exact-head CI/native auto-merge/main deploy + public health.

Progress: Mini App catalog RED reproduced exposed keyframes; single-reference choice and mixed uploader now pass. Site/Mini App automatic routing uses server kind; frontend extension classification only preflights existing protocol counts. Files are committed individually to the draft, so a later batch failure preserves earlier uploads. Busy guards, mounted/account/model checks, legacy frame editor and exact quote confirmation retained. Site first four-profile run exposed a new test-harness glob that failed to intercept query URLs (not an app defect); corrected interception. Independent review reproduced a real optional-voice deletion crash introduced by the new summary; browser RED reproduced undefined.split, guard added; independent Chromium remove/replace probe now passes with zero page errors.

Verification: site **80/80** across iPhone SE, iPhone13, Pixel5, Desktop; Mini App **8/8** including mixed references/partial errors/invalid kind/over-limit/history checkout; frontend units **121/121**; typecheck/build passed (existing bundle-size warning); full Python **3713passed/81dedicated-environment skips/3existing warnings/0failures**. Provider inventory, full Ruff, JS syntax and diff checks pass. Independent Standards/Spec reviewer covered all11task files with no remaining findings; host OCR6/6source coverage plus manual tests/docs review, excluding pre-existing diagnostics/logs. No migration/price/access-policy changes or paid provider request. Steps2–4 complete; exact-head required CI/native auto-merge/deploy/public health remain.

Release asset check: live site scripts have Cache-Control public,max-age=600. Bumped existing script query versions in all landing HTML entry points, including the Kling studio extension, so already cached old split-mode JS cannot survive the new HTML release. This is cache identity only; application behavior/checks unchanged. Auto-merge briefly disabled while publishing the amendment; new exact-head required CI must pass.

Exact-head CI b6133da correctly caught the existing cache-version contract test still expecting the previous 20261022_private_catalog URL. Reproduced locally; updated its exact required release string to 20261023_kling4_references (same all-entrypoint assertion, no test removed/relaxed) and renamed the test to describe the general release contract. Focused full web parity module passes. Amended full pytest and new exact-head CI required.

Exact-head web CI6bba947: 331/332base browser +93/93UX2 passed, one new iPhoneSE catalog harness failed. Downloaded trace proves mock /history returned `{}`; real runtime expects array and threw `(history || []).map is not a function` before render. Three profiles had accidentally rendered via concurrent public-load timing. Corrected harness default list responses to `[]`, matching actual API and surrounding fixtures; retained all DOM assertions/timeouts and no production source change. Focused four-profile rerun/new exact-head CI required; no flaky retry used to hide the fixture defect.

## 2026-10-23 — Kling 4 finished result not delivered (same authorized parity release)

User additionally reports missing result during PR296 verification. Baseline head70814bb, production still9cd74d3. Read-only production DB/log audit found Kling4 bot generation63327 done since09:00:06UTC, result stored, durable done notice pending with zero attempts. No prompt/media/customer identity/credentials copied here. Runtime recovery is running; notice claim rejects plain KIE task IDs unless the model is Wan, so bound Kling4 jobs are silently skipped. No provider replay, balance/SQL repair or manual Telegram send performed. User task identity clarification requested; do not attribute other users' results.

Acceptance: existing scheduled recovery claims only matching bound Kling4 provider identities, sends existing final result/failure through the durable lease/receipt path and does not resubmit AI work or charge again. Retain web-origin suppression, unrelated-model rejection, missing/unbound/mismatched identity rejection, attempt caps/backoff/leases/token checks. Shared backend fixes all surfaces' result status, with Telegram delivery only for bot-origin tasks. No new config, migration or money transition. Existing delivery receipt logging supplies gen/kind/attempt/delivered observability.

Regression RED: four cases (both Kling models × done/failed) could not acquire a claim; five invalid identity cases correctly rejected. Minimal fix extends the existing exact-model, bound-marker and matching-task guard to the two verified Kling4 models, keeping all other delivery conditions. Focused tests/full gate/review and renewed exact-head PR296 CI required before deployment. Auto-merge disabled while amending. All previous70814bb required checks ultimately passed, but this material incident fix needs its own exact-head release.

Incident verification: actual read-only production scheduler query selects generation63327, with bound provider identity and durable pending done notice/zero attempts. All79 focused notice/Kling/API/privacy tests pass from the correct artflow cwd; first root-cwd attempt had two relative-path fixture failures (no code failure). Full amended Python gate **3722passed/81dedicated skips/3existing warnings/0failures**. Independent reviewer traced startup→scan→claim→Telegram→ack and independently ran24outbox tests, no remaining finding. Host OCR reviewed added repository Python diff; identity/lease/backoff/financial invariants preserved. Actual production send must be checked after normal protected deploy; no direct DB write or manual send used.

# 2026-10-25 — public Kling 4 rollout and Wan 3 primary verification

Baseline `6d84c0288c9a7ba16e663b7305c44ba77946e187`; branch
`feature/kling4-public-wan3-neironych-20261025`. Owner explicitly requested the
APIX `lena_bot` rollout: expose Kling 4 to all users and make Neironych primary
for Wan 3 across all surfaces. Production preflight found Kling 4 still
`admin`, all six tariff rows active, and both Wan routes already DB-configured
as `neironych_kie` with native IDs `wan-3` and `wan-3-prime`. The site, Mini App
and Telegram share those access/routing adapters, so no surface-specific route
change is required.

Acceptance: add a trusted-shell control that uses the existing authenticated
Kling access mutation and immutable audit instead of manual SQL or Telegram
identity impersonation; open production only after protected merge/deploy; then
verify exact SHA, public access, audit source, active tariffs, both Wan policies
and native catalog mappings. The owner subsequently authorized bounded paid
production smokes for Standard and Prime. Use separate durable journals and
idempotency keys, verify provider task identity, billed seconds and downloaded
media, and never replay an accepted or ambiguous request. KIE remains standby
only after a definite rejection or unsupported input.

Parity: `site`, `mini_app`, and `telegram_bot` already consume the same Kling 4
policy and Wan provider entrypoint. Configuration remains DB-backed and audited.
Migration 050 adds truthful trusted-shell actor provenance; no price, provider
contract, credential or customer-balance change.

Live evidence before the source release: the Neironych catalog exposed `wan-3`
and `wan-3-prime`. Standard request
`131f2fe5-b1e8-4bbc-90ba-e75a75f9c527` completed on Neironych with 5.0 billed
seconds; its downloaded MP4 was 5.038 seconds and 7,862,290 bytes. Prime request
`6d3d531d-1779-4433-99d2-ce2dbe2d37a8` was definitively rejected after
admission because the model was temporarily at capacity; no billed seconds and
no KIE fallback/replay. One separately journaled Prime retry is allowed after
that terminal unbilled outcome. Retry
`92c63e09-2ea3-4dbd-8fa2-b56d0fe71b04` received the same terminal capacity
failure with no billed seconds; stop further paid Prime attempts and report the
upstream capacity blocker honestly.

Skills: claw backend-integration, telegram-miniapp, frontend-qa,
release-hardening and kie-seedance; Bambale0 wayfinder, implement, TDD and
code-review; Anthropic webapp-testing. Steps: [x] current source/production
preflight; [x] acceptance/parity/security plan; [ ] RED/green focused tests and
full relevant gates; [ ] independent review; [ ] PR/exact-head CI/native
auto-merge/deploy; [ ] production policy change and live verification.

## 2026-10-25 — photo-to-prompt Qwen incident route repair

Baseline `216e2fd74241738fa4edbc9f2a0152be0fec5bb7`; branch
`fix/photo-prompt-qwen-route-20261025`. Four production photo-to-prompt calls
failed through Neironych Qwen 3.8: three exact 90-second read timeouts and one
HTTP 503. These are ambiguous after admission, so retrying or falling back to a
second paid provider would risk duplicate supplier cost. The no-replay guard is
working as designed and remains unchanged.

Production preflight: the `image` route was still the default
`neironych -> kie`; both provider credentials are configured and the verified
KIE image model is `gpt-5-2`. Acceptance: add a trusted-shell Qwen route control
with explicit immutable ops attribution, preserve authenticated web/Telegram
attribution, then move only `image` to `kie -> neironych` after protected
deploy. Text/video routing, prices, customer balances and provider request
semantics remain unchanged. Rollback uses the same audited command after
Neironych recovery is independently confirmed.

TDD: new tests first failed because the command/migration did not exist. The
implementation adds migration 051, ops actor validation, the route command,
audit-shape checks and updated runbook. Focused routing/script/migration tests
now pass. No paid live smoke is authorized or required; production verification
will cover exact SHA, migration head, route/audit state, service health and
absence of new photo-prompt Neironych submissions after the cutover.

Steps: [x] root-cause and production preflight; [x] RED/green operator control;
[ ] full relevant gates and review; [ ] PR/exact-head CI/auto-merge/deploy;
[ ] audited production switch and live verification.

## 2026-10-26 — WAN 3.0 native edit and duration settlement (active)
- Baseline origin/main 4508acfaaca1a7d900d62dae65e2c53fe16bd8ba, branch fix/wan3-neironych-native-edit-20261026, isolated worktree.
- Evidence: 29 edit KIE tasks and 2 Neironych non-edit tasks in preceding 24h. Current contract blocks native edit. Live Neironych guide documents omni_reference_task_type=edit, reference_videos, omission of duration/aspect_ratio/size; Prime edit unsupported.
- Intent: route compatible edits to native Wan3, preserve requested duration contract via KIE for incompatible edits, settle actual verified duration with atomic exactly-once refund and ledger. No new DB schema; admin controls remain source of pricing and routing.
- Plan: failing contract and billing tests, provider adapter, settlement, regression, docs, PR, auto-deploy only through approved CI. No paid smoke without per-test approval.

- Implementation complete in worktree: native WAN Standard edit body with explicit task type and no duration/ratio; verified-source quote upper bound; original KIE semantics for incompatible requests/Prime; owned MP4 probe; row-locked exactly-once post-completion ledger and partial credit return. No migrations or new configuration values.
- Test evidence before PR: full backend pytest command exited 0 (26 Oct 2026, 28.58 seconds) with expected skips; WAN/provider/recovery and financial suite exited 0; two real PostgreSQL race tests on disposable schema exited 0 (parallel callback/poll and completion/failure). Read-only provider-contract inventory valid, product readiness OK for 100 public contracts. Ruff, compileall and git diff --check passed. Synthetic credentials only.
- Product surfaces checked: site=shared backend; mini_app=shared backend; telegram_bot=shared backend. No new UI branch; no user-facing code hardcode. Observability: safe generation ID, changed billable seconds, refund credits, overage seconds; no prompt/key in logs.
- Remaining release gates: CI checks on exact PR head, reviewed merge, production autodeploy health and authorized paid edit smoke. No paid request performed and no live billing/customer data mutated by this branch.

## 2026-10-26 — trend category folders, live tiles and administrator catalog

- Phase A released through PR #307 at merge SHA `4265a382763fa6c325b466bc1111e0cf8860000e`; Production Autodeploy run `40337775834` completed, public health and Mini App assets returned 200, and build marker `20261026-studio-black-lilac-r1` was present.
- Phase B branch `feat/trend-category-folders-admin-20261026` starts from that release. The existing black/lilac Studio palette remains authoritative; the new category shelves, folders and admin controls use the same black canvas and lilac tokens. Build marker is `20261026-trend-folders-black-lilac-r1`.
- Backend adds authenticated, revision-guarded category create/rename/reorder/show/hide and trend reassignment with immutable opaque keys, populated-hide confirmation, transaction rollback and audit rows. Pricing, balances, provider routing and generation contracts are unchanged.
- Mini App now renders server-backed category shelves with viewport-scoped live media, explicit folder entry, pagination, broken-media fallback and admin-only catalog controls. Telegram opens category folders first, pages eight folders at a time, keeps callback payloads below 64 bytes and restores the originating folder page.
- Local evidence: Ruff passed; 93 focused backend/category/repeat tests passed; web typecheck/build passed; 148 unit tests passed; 72 maintained browser journeys passed across live category, black/lilac, completion and duration flows. Screenshots at 320/390/768/1280 were inspected. No paid generation or mutable production control was used.
- Remaining gates: push PR, exact-head required checks and review, native squash merge, Production Autodeploy, then verify exact SHA, migrations, health, public build marker and read-only category endpoints.

## 2026-10-27 — black/lilac luxury media-studio home

- Baseline `44a55debba0a1c027910c0595ea6690de683c4b3`; branch
  `feat/lilac-luxury-home-v4`. The requested visual reference is a mobile luxury
  AI studio: compact brand/balance header, one dominant media hero, two promo
  panels, six large service launchers and a floating five-item bottom bar. APIX
  keeps its established black/lilac palette, product names and real routes.
- Existing implementation already has authenticated balance/top-up, five-item
  navigation with a central Create action, viewport-scoped live media, real
  image/video/music/assistant/motion/tools routes, drafts, trends and recent
  work. The gap is composition and visual hierarchy, not backend capability.
- Acceptance: reproduce the reference composition at 390px without copying its
  gold branding or inventing functions; keep all launchers at least 44px,
  keyboard focus, safe areas, reduced motion, no horizontal page overflow and
  live-media fallback. Existing labels and all generation/payment/admin flows
  remain intact. Verify 320/390/768/1280 widths and the real click-through to
  every launcher.
- Scope/parity: `mini_app` visual refresh; `site` uses separate entry styling and
  is unchanged; `telegram_bot` has no visual composition equivalent and is not
  applicable. No API, schema, migration, price, balance, provider, permission,
  admin configuration, secret or observability change. Rollback is the single
  frontend release commit.
- Skills/guidance: UI UX Pro Max, `.agents` frontend-design, TDD and webapp-testing.
  Direction: **Lilac Noir Studio** (luxury/refined with one restrained futuristic
  accent); anchor is the cinematic hero plus luminous nested-square launcher
  grid. DFII discussion score 16/19 (impact 5, fit 4, feasibility 5,
  performance 4, consistency risk 2).
- Steps: 1. [x] current source/contracts/tests/CI/brand preflight; 2. [x] RED home
  composition and routing tests; 3. [x] implement semantic React/CSS vertical
  slice; 4. [x] unit/typecheck/build/browser/accessibility/visual checks and open
  code review; 5. [ ] PR, exact-head required CI, native auto-merge, Production
  Autodeploy, exact-SHA/public health and public asset verification.
- Local evidence: TypeScript and Vite production build passed; 148 unit tests
  passed; all 284 maintained UX2 browser journeys passed in 6.9 minutes. The
  suite covers 320/375/390/768/1280 portrait widths and 844x390 phone landscape,
  real routing for all six launchers, balance/top-up, live MP4 viewport behavior,
  reduced motion, fullscreen safe areas, keyboard focus and no page overflow.
  The 390px screenshot was inspected after the final build. Review found no new
  correctness, security, permission, billing or provider issue; no paid request
  or mutable production control was used.
- Review removed an unsupported customer-facing `24/7` help SLA copied from the
  visual reference. The promo keeps its real help route and neutral `Центр
  помощи` copy; no availability promise is invented outside the control plane.
- PR #312 first exact-head webapp run exposed one stale device-matrix selector:
  the new six-button semantic quick-launch navigation was correctly included in
  an unscoped `navigation` query that previously assumed only the five-button
  bottom bar. The smoke now addresses both navigation regions by accessible
  name; its four iPhone SE/iPhone 13/Pixel 5/Desktop cases pass locally. Product
  behavior was unchanged by this test correction.

## 2026-10-28 — Wan KIE primary with Neironych fallback

- Baseline `ac790307fbda56ad7b70fc8b14032ebf40b2588c`; branch
  `fix/wan-kie-primary-neironych-fallback-20261028`. The owner corrected the
  requested route from KIE-only to **KIE primary, Neironych fallback** for both
  Wan 3.0 variants.
- Safety contract: fallback is permitted only after `KieDefiniteRejection`,
  which proves the paid KIE task was not accepted. Timeout, 5xx, malformed
  response, missing task ID and every other uncertain KIE outcome stop without
  a Neironych POST. Both provider sends retain their existing durable journal
  requirements and provider task identity.
- Control plane adds audited policy `kie_neironych`, revision-checked writes,
  catalog/key validation and an expand-only migration `053`. Existing rows are
  not changed by deployment; the production switch must be made afterward by
  an authenticated administrator and verified in the audit table.
- Surfaces: shared backend behavior covers site, Mini App and Telegram bot;
  APIX Studio and the Telegram admin page both expose `KIE → Нейроныч`. Prices,
  balances, access policy, credentials and provider payload contracts remain
  unchanged. No paid generation is used for verification.
- TDD evidence so far: the new route and control-policy tests failed before the
  implementation and now pass; the static admin browser scenario failed on the
  absent option and now passes 8/8 device cases; the APIX Studio payload flow
  passes. Focused Wan provider/routing/runtime/repeat suite passes 120 tests;
  migration chain has one head at `053_wan_kie_primary_fallback`.
- Final local gates: Ruff, compileall, diff check, TypeScript, Vite production
  build and 148 frontend units pass. Offline PostgreSQL Alembic SQL shows one
  transactional constraint replacement and head update. The broad Windows
  Python 3.14 run retains unrelated current-main/platform fixture failures;
  exact-head protected CI on the repository Python is authoritative. No focused
  Wan, migration-chain or changed-surface test failed.
- Remaining gates: full relevant lint/tests/review; PR and exact-head protected
  checks; merge/autodeploy; exact-SHA, migration, container and health checks;
  authenticated route update for Standard and Prime plus immutable audit
  verification.
- PR #315 first exact-head gates all passed, but required Codex review correctly
  blocked merge on a P1 durable-journal flaw: the KIE marker prevented the
  Neironych fallback from starting and would have selected the wrong result
  binder. A real SQLite checkout-context RED reproduced it. The amended flow
  records a definite KIE rejection, atomically transfers `kie-submit:*` to a
  Neironych submission marker before POST, switches in-memory binder ownership,
  and rejects an impossible late KIE callback. Related admission/routing/feed/
  callback tests pass 164/164; Ruff, compileall and diff check pass. Updated-head
  CI and review are required again before merge.
- PR #315 merged as `530fdd17`; its updated-head review then identified a P2
  crash window before the Neironych catalog check. Follow-up work persists the
  confirmed no-task KIE response as `definite_rejected_neironych_pending`
  immediately, transfers only from that durable state, and lets the bounded
  recovery worker resume the first Neironych POST with the original validated
  Wan request and idempotency key without replaying KIE. A synthetic restart
  regression covers the durable marker, resumed fallback, result binding and
  exactly-one KIE POST. Production route policy remains `kie_only` until this
  follow-up passes exact-head gates, review, merge and deployment verification.
- Follow-up PR #318 review identified three recovery correctness gaps. The
  amendment immediately refunds a resumed Neironych admission rejection under
  the exact task-id lock, preserves the original KIE `rejected_at` and records
  `fallback_started_at` separately, and makes the SQL expiry lane use the
  active Neironych submission clock so recovered rows cannot starve the batch.
  Focused admission/timeout/recovery coverage passes 132/132; updated-head CI
  and review remain required before production policy activation.

## 2026-10-28 — lilac branded bottom-navigation icons

- Baseline `ac79030`; branch `feat/lilac-nav-icons-v5`. The approved reference
  uses a restrained five-item bottom bar with consistent outline glyphs and a
  circular branded Create medallion. APIX keeps its black/lilac palette and the
  existing labels/actions: `Главная`, `Идеи`, `Создать`, `Пополнить`, `Профиль`.
- Scope is Mini App presentation only: no navigation route, balance/top-up,
  permission, backend, schema, price or provider change. The four semantic
  destinations retain Lucide outline icons; Create receives an accessible,
  CSS-rendered APIX aperture mark inside the existing touch target.
- Acceptance: five existing destinations and accessible names unchanged;
  exactly four consistent outline glyphs plus one circular brand mark; selected
  state remains visible beyond color alone; touch targets stay at least 44px;
  no horizontal overflow at 320/375/390px or phone landscape; focus, safe area,
  press feedback and reduced-motion behavior remain intact.
- Direction: **Lilac Noir navigation medallions** — luxury/refined, with the
  branded circular Create control as the sole visual anchor. Guidance: UI UX
  Pro Max and `.agents` frontend-design. Steps: [x] source/reference preflight;
  [x] RED visual contract; [x] React/CSS implementation; [x] focused/full
  frontend checks and screenshot review; [ ] protected PR and production proof.
- Evidence: the new contract failed against the previous build with zero of four
  expected outline-glyph wrappers, then passed after implementation. TypeScript
  and Vite production build passed; all 148 unit tests and all 285 maintained
  UX2 browser journeys passed. The final 390px screenshot was inspected with
  the branded circular medallion, four aligned outline glyphs, unchanged labels,
  active-state panel, focus treatment and no overflow. No paid or production
  mutation was used during verification.
- PR #317 review found that a later legacy glow declaration replaced the new
  inactive medallion's complete `box-shadow` stack. The obsolete declaration
  was removed and the browser contract now requires the inactive Create control
  to retain its inset black/lilac rings as well as its outer glow.
