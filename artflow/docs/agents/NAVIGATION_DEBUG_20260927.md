# Telegram navigation debug — 2026-09-27

Baseline: 8a9bbae789617da0731fd11c82c2d37cbc4980ef (clean server tree).
Live container and checkout SHA256 match for video_gen, video_wizard and handlers bootstrap.
Scope: all text-bot navigation, focusing on deterministic parent screens, correct model/mode selection, and isolation from abandoned workflows. No provider, price, database or paid-generation changes.

Evidence:
- video_wizard stores wizard_mode but no consumer reads it; scenario selection can open unrelated modes.
- vpar_back reconstructs a model-mode menu rather than the previous reference collector.
- image_home bypasses model-first entry and opens the old default-model UI.
- menu:create/menu:more/menu:settings render without clearing active FSM; subsequent text can still enter an abandoned generation handler.
- advanced video entry retains previous wizard_mode and media fields.

Acceptance: dispatch real callback sequences through installed router order with MemoryStorage and mocked Telegram/DB boundaries; correct rendered screen and FSM after every back; no paid calls; preserve media when editing parameters; clear discarded task data on new task; stale model callbacks never change a different active model.

Steps:
1. [done] Prepare required tool repositories; inspect local guidance, runtime, bootstrap, keyboards, tests, CI and schema.
2. [done] Write failing navigation regressions and audit all public entry/return callbacks.
3. [done] Correct shared causes with minimal changes.
4. [done] Focused tests, broader bot regression checks, lint and independent review.
5. [done] Apply verified patch and document live verification/rollout status.

Surfaces: telegram_bot affected. site/mini_app do not use Aiogram callback routing/FSM; shared model capabilities, generation APIs, pricing and data contracts unchanged.
Skills: aiogram-codegen, bot-tester, project systematic-debugging; WondelAI working-with-legacy-code (test seams); claw backend-integration inspected (project-specific registry paths absent, general small-change/test guidance applicable); Anthropic catalog inspected (no matching text-bot debugging skill). Copied Superpowers PR guidance in .clinerules is for contributing to Superpowers, not this application.


Implementation and review:
- Explicit video navigation router, registered before legacy callbacks; scenario-compatible models, contextual parents, preserved references, review/edit/return paths.
- Public menu middleware ends abandoned input; repeat/library starts clear unrelated data. Image entry uses model-first flow; image settings and photo-analysis cancellation restore the correct origin.
- Music source back preserves the audio; video-analysis cancel offers a destination; reference collectors offer exits. Unknown/stale callbacks answer explicitly.
- Midjourney results own their originating task; action callbacks include a task fingerprint, preventing old cards from charging an action against a different result. New MJ starts discard prior task IDs before setting new prices.
- Independent code review reproduced two extra issues (Motion URL overwritten by prompt after Back; old MJ result replacing a restarted wizard). Both fixed and regression-covered; reviewer reports no remaining blockers in reviewed changes.
- Fixed undefined `prev.model` when reconstructing an image result session.

Verification (isolated full git archive; Python 3.12, production dependency venv; Telegram/DB/provider boundaries mocked):
- Focused navigation/image/video/photo/MJ/payment/menu/callback suites: **196 passed**.
- Complete original suite: **1283 passed, 42 failed**. Complete patched suite: **1370 passed, 42 failed**. JUnit comparison: identical failure identities; **0 introduced failures**, 87 additional passing regression cases.
- Existing failures include legacy UI string/source assertions and outdated handler signatures, plus provider/API/frontend contract failures. They are not silently removed or relabeled green.
- Ruff on every changed Python file: passed. Compilation: passed.
- Hosted CI was not executed: this change has not been pushed. Local equivalent pytest/lint/compile checks above are the evidence; full suite remains red on baseline as well.
- No paid generation, customer messages, or real payment operations used for tests. Actual Telegram client click-through and provider generation were not exercised.

Rollout:
- Source baseline rechecked clean before rollout. Existing app image c48d8a80d350356659302a2e1215dac6f08b5b130dd308d1b4513e1e237edddd retained for rollback.
- Runtime database and source both at migration 035_trend_user_fields (head). No migration, pricing, provider contract or environment/config changes.
- Apply the reviewed files, build/recreate app only, inspect startup and /health, compare deployed source hashes. Record result in EXECUTION.md.
- Risks: application recreation briefly interrupts requests; previously displayed obsolete action buttons require opening the current menu. Existing unrelated baseline test failures remain follow-up work. No claim of exhaustive defect freedom.

Guidance used: aiogram-codegen, bot-tester, devops; project systematic-debugging and requesting-code-review; claw backend-integration; WondelAI working-with-legacy-code. Anthropic catalog inspected; no applicable specialized skill for this text-bot fix. Public UI business capabilities continue using existing config; no new mutable business setting is hardcoded. Middleware debug logs expose transition names/state only, without prompts or credentials.

Verified rollout: code commit `24fabd0740d0fa9a2303a156a18b5f5dedff93e3`, branch `fix/telegram-navigation-20260927` (not pushed). Image `sha256:956e56c02d5928dc3b19fae84022844b3d882582a2c0d72d99966b0842e92385`. App started successfully at 2026-09-27T12:07:51Z; all 31 changed Python source hashes match checkout; internal /health HTTP 200; no startup traceback/error markers; zero restarts. Backup: `/root/artflow-navigation-backup-20260927`, rollback image `artflow-app:navigation-before-20260927`.
