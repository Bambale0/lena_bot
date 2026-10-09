# APIX Seedance reference/edit correction

Baseline: `26d4ebb82d675abf762baf341b378e428ada8839`; production at investigation
was `64f7753`. The newer main change is unrelated photo-upload resilience.

## Evidence and intended outcome
The shared Neironych adapter unconditionally maps product edit intent to the
provider's single-video edit mode. Mixed photo/video feed personalization thus
reaches an incompatible contract. Source dimensions were already probed before
pricing, but the provider wrappers replace duration/ratio with -1/adaptive.

Keep single-video text edits as edit; translate mixed-reference personalization
to reference with all assets preserved and measured source-derived output
seconds and closest supported ratio. No silent deletion or frame-mode switch.
The gateway remains strict. Raw admin edit inputs must match its contract.

## Scope / safety / parity
site and mini_app share the API flow; telegram_bot and both service wrappers
reach the same Neironych adapter. KIE behavior and configured provider priority
remain unchanged. Tariffs remain DB-backed; no price/config/migration changes.
Quote rounding and source-derived output seconds must agree. Admission hashes,
idempotency, uncertain-submit reconciliation, refunds and history are untouched.
No retry of historical failures and no new paid tests in this work.

Only already-owned local media may be probed; no new remote fetch/SSRF surface.
Fail closed before provider POST and durable admission when metadata is missing.
Log model/mode/counts/dimensions only, never prompts, media URLs or credentials.

## Acceptance checks and progress
1. [x] Inspect running revision, instructions, current main and shared pathways.
2. [x] Baseline focused suite: 94 tests passed.
3. [x] Reproduce incorrect wire mode / invalid metadata acceptance in tests.
4. [x] Implement minimal adapter correction plus local contract parity.
5. [x] Verify real adapter/client serialization, feed quote, bot, fallback,
   idempotency and reconciliation regressions; add maintained CI coverage.
6. [ ] PR checks, native auto-merge, exact-SHA production autodeploy and live
   read-only payload validation of historical shapes with no paid replay.

Guidance: local test-driven-development and code-showcase-systematic-debugging;
legacy characterization principles used only for behavior that must be retained.
Provider basis: https://argolink.io/en/models/seedance-2.5 (Reference / Edit).

## Implementation and local verification
- The new regression was run first: 16 expected failures and two existing valid
  scenarios. The wire contained edit instead of reference; invalid metadata was
  not consulted; raw edits accepted extra assets; false audio was rejected.
- Shared adapter now measures an owned local source when mixed edit intent needs
  reference mode. Ceil duration matches quote rounding; ratio comes from source
  dimensions and the existing supported-ratio list, not a hardcoded portrait.
- Valid single-video edit omits duration/ratio exactly as before. Ordinary
  reference requests preserve the user's duration/ratio. KIE is unchanged.
- Raw admin contract now rejects mixed edit explicitly and supports the already
  corrected gateway silent-video boolean for 2.5 (2.0 unchanged).
- 294 focused tests passed after the repair, covering actual HTTP serialization,
  both wrappers, bot/feed paths, quote/charge consistency, admission hashes,
  fallback/reconciliation and delivery. Changed Python files pass Ruff;
  git diff --check is clean. Maintained CI includes the new regression file.
- No destructive changes, migrations, secrets, production data changes or paid
  requests were made. Exact-SHA CI/deployment remains to be verified.
