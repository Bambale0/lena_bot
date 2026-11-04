# VIP image cards through Neironych — 2026-11-04

Baseline: 2b957b4569c5273bb876ad4ad2298bba4ca108bf. User explicitly requests both Nexus VIP cards to use Neironych and clarifies the provider exposes unified models without VIP suffixes.

## Preflight and contract evidence
Production currently dispatches both VIP keys directly to Nexus. Existing non-VIP family routes are typed, DB-backed, authenticated and audited; runtime family defaults are Neironych. Reuse those controls for each family including its VIP alias; do not introduce duplicate configuration or change commercial names/prices/public keys. No schema change or migration is required. All site/mini_app/telegram_bot launch paths, protected feed repeat, durable admission, canonical provider status, completed-response recovery and signed Nexus fallback need VIP coverage.

Read repository AGENTS files and relevant guidance: /root/claw-tools/.agents/skills/backend-integration/SKILL.md, local verification-before-completion, /root/skills/release-it/SKILL.md and /root/bambale-skills/skills/engineering/code-review/SKILL.md. Scanned local .agents/.clinerules and Anthropic source; general Node-specific backend guide is not applicable to Python framework details. Baseline worktree clean; production has unrelated untracked ops data left untouched.

Actual Neironych running contracts/registry.py confirms nano-banana-pro accepts 14 references and 10 explicit aspect ratios, 1K/2K/4K; gpt-image-2 accepts 16 references (APIX public VIP remains four). Prior APIX adapter's four-reference Nano cap was narrower. Keep unverified/auto formats on existing same-public-model Nexus reserve. Never fallback on ambiguous paid outcomes. VIP GPT uses the existing basic quality default, without adding public quality controls.

## Scope and acceptance
Map nano-banana-pro-vip -> nano-banana-pro and gpt-image-2-vip -> gpt-image-2 only at the provider boundary. Preserve public model identity in frozen admission and recovery, family admin routing, distinct pricing, references and order, task guards, atomic billing/refunds, hidden prompt privacy and delivery. No duplicate paid POST after timeout/5xx. Validate all surfaces and signed fallback, provider inventory, full pytest/Ruff, two-axis review, exact-head CI, native auto-merge and automatic production deploy. Verify deployed routes and source identity plus live text/edit requests.

## Steps
1. Audit complete: source, provider runtime contract, config/admin, billing/recovery, tests and CI inspected.
2. Write failing VIP regressions; implement shared family aliases and durable identity.
3. Run focused/full checks and independent Standards/Spec reviews; resolve findings.
4. Deliver via PR/native auto-merge; verify CI, deploy, health and running alias routes.

## Implementation and verification

Step 2 complete: both VIP keys use shared family routing on all surfaces; canonical model mapping only at the native boundary; public identity is frozen and required by admission/recovery; Nano Pro native contract now preserves 14 references and all 10 explicit ratios. Signed Nexus callbacks and strict canonical status include VIP aliases. Catalog/docs/admin family labels updated; names and price rows unchanged.

Step 3: red regression failed against baseline as expected; focused tests passed. Full isolated Python suite: **4228 passed, 101 skipped, 4 existing warnings in 27.72s**. Full Ruff and provider inventory passed. Local skips need optional PostgreSQL/Nginx/integration services; required CI supplies its maintained environment. Initial test-container infrastructure failures (Docker/Node absent) were corrected by completing the isolated test image; no test gate was weakened. Independent review and live provider smokes pending.
