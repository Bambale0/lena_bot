# Protected main delivery — 2026-09-27

Request: publish the navigation fix to main; prohibit direct main pushes; merge automatically after green CI and deploy automatically.

Baseline: 8a9bbae on origin/main; reviewed navigation branch at bc7ad00. GitHub already enforces PRs for main, includes administrators, requires up-to-date backend-quality/webapp/provider-contracts checks, blocks force pushes and deletion, and requires resolved conversations. Native auto-merge is already available. Existing production workflow deploys only main after backend and webapp, with configured production SSH secrets and SHA verification in deploy-production.sh.

Changes: add mandatory bot-navigation CI (196 focused cases); make deployment depend on it and explicitly wait for the separate provider-contracts check on the exact main SHA. Extend branch protection with bot-navigation without removing prior requirements. Restrict the production environment to protected branches. Document PR-only delivery and native auto-merge enrollment in root AGENTS.md.

Native GitHub auto-merge is enabled per ready PR by the submitting maintainer/agent (`gh pr merge --auto --squash`); it is not indiscriminately enabled for every incoming external PR. No new broad-scope bot token or token-triggered merge workflow is introduced. Existing push-triggered deployment is retained.

Verification plan: YAML/job dependency validation, review workflow changes, PR CI including existing maintained gates, native automatic merge, main CI and Production Autodeploy success, source SHA and public health. No migrations/provider/pricing/config changes. Existing full-suite baseline failures are documented in NAVIGATION_DEBUG_20260927.md.

Skills: team-lead, devops, project requesting-code-review; prior navigation guidance in NAVIGATION_DEBUG_20260927.md remains applicable. No newly required runtime secret.
