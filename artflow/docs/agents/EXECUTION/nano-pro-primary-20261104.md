# Nano Banana 2 and Pro primary routing — 2026-11-04

Baseline 851e27f4a35ffd85a77285ed50e50f58aed0cce9.
Existing: #333 implements durable Nano Banana 2 routing, frozen request evidence, bounded HTTPS transport, safe Nexus fallback, exact completed-response recovery, admin controls. Pro has only an isolated lab; production still routes to Nexus.
Acceptance: Neironych primary for 2 and Pro across site, Mini App, Telegram and feed repeats; preserve reference/quality and financial invariants. Nexus remains compatibility/definitive rejection reserve; no duplicate POST after ambiguous failure.
Plan: (1) red routing test (observed Pro uses Nexus), (2) reuse Nano 2 production pattern for Pro, (3) contract/admission/recovery/admin/all-surface tests, (4) review and exact-head CI then normal autodeploy, (5) live DB route/health/runtime verification.
No schema change: reuse ProviderRoutingSetting + append-only audit. Pro selection from typed environment default and authenticated DB override. No copied tariffs or credentials.
Seams: HTTP adapter, persisted pre-submit snapshot, guarded completion, signed fallback webhook, shared launch paths and admin routing. Both models retain independent keys.
Reviewed guidance: existing project-local instructions/TDD, primary engineering TDD, claw FSM flow, wondelai adapter boundaries, Anthropic browser testing; same mandatory tool sources refreshed.
Risk: upstream ambiguity never licenses failover. Pro uses reviewed lab capability subset (fixed supported ratios and up to four HTTPS refs); auto/unsupported ratio preserves Nexus contract. Recovery replay only after authenticated completed status, exact original body/key/scope.
Verification pending.

Verification: full local pytest and Ruff passed; provider inventory valid (100 contracts). Focused new/adjacent tests cover route override, single-use admission, HTTP generation/edit, all five launch paths, status-only recovery, exact cached-response replay, signed Nexus callbacks and task-guarded settlement. Existing provider-specific fixtures explicitly select Nexus for reserve tests. Live Pro 1K text completed in 21.6s, request 828810fd-b495-4337-a96a-a87aeba48643. Nano 2 live DB route confirmed neironych/database. CI/release pending.

Full local suite: 4128 passed, 101 skipped (environment-dependent tests); no failures. Independent production runtime components reviewed; no automatic retry/fallback on uncertain acceptance.
