
## 2026-10-09 — Repeat, checkout and video-prompt fixes

Baseline: main `07595403a7375ecba50347c820b6a645c301b8ef`.

### Changes
- Align feed quote and launch validation, preserve supported references, and use
  measured source-video duration for Seedance edit billing before spending
- Restrict checkout choices to the selected plan and show provider currencies
- Use published media and user inputs for personalized repeats while preserving
  ordinary repeat references and protecting private prompt text in responses
- Add nullable `image_sessions.prompt_provenance` in migration
  `038_image_session_provenance`, after `037_provider_routing_settings`. No
  historical rewrite or deletion; unknown restored prompt text gets a clear
  reentry notice. The additive column can remain unused after an application revert
- Validate video-prompt response structure and send Qwen FPS beside video_url
  (`COMET_VIDEO_PROMPT_FPS`, default 2.0, range 0.1–10). Preserve the 100 MiB file cap
  with 101 MiB multipart limits and 240-second read timeouts on the two exact
  video-prompt routes; retain the 180-second provider deadline and unrelated limits
- Describe automatic provider-status checking accurately. Preserve existing
  polling, held-credit, terminal settlement and no-replay safeguards
- Correct the PostgreSQL admission predicate's JSON boolean boundary. FPS and
  admission fixes are adapted from PR205 at 4704fe87d35007ab924e95a39f7d1d2187661f52

### Verification and release limits
- Maintained backend: 939 passed, 12 local environment skips; bot: 351 passed;
  frontend unit: 19 passed. TypeScript/build, lint and static checks passed
- Exact-commit CI must execute the nine PostgreSQL admission cases, migration
  roundtrip, two canonical Nginx tests and browser suites before release
- Site, Mini App and Telegram use the applicable shared contracts. No live paid
  generation, payment or refund was used for these checks
- Provider output quality and production upload capacity remain unverified.
  Unknown submissions without a recoverable provider identity remain a separate
  upstream limitation. General natural-language missing-media refusals are not
  universally classified; PR205's broader prose classifier is not included
