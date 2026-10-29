# UX2 video first-frame repair — 2026-10-29

## Goal and baseline
- User reports that not all feed previews are visible after the gallery redesign; the supplied screenshot shows four video cards with the Lilac media background and Play controls, without a visible video frame.
- Baseline main/production: `5b0560e5006d84f82307729d2e7b3dba71f4d3ba` (PR #325).
- Work is isolated on `fix/ux2-video-preview-20261029`; the production checkout is not edited manually.
- Skills: diagnosing-bugs and TDD, existing frontend-react, frontend-design and repository verification/delivery guidance. Tool skill repositories refreshed with fast-forward-only pulls.

## Existing implementation and hypotheses
- Feed video previews preserve the canonical result URL and rely on a paused HTML video plus the global feed-video-stabilizer. Video preview URLs are aliases of the original result; image-only preview.webp/display.webp endpoints are not video posters.
- Confirmed control-flow defect: the stabilizer can seek and mark a frame primed before a subsequent unconditional load() resets media state. The flag then prevents later priming. Merely assigning currentTime also does not confirm that a frame was decoded and painted.
- Other hypotheses to distinguish with actual media: pending/range/codec/network failure, and a CSS/compositing obstruction despite a decoded frame. A separate extensionless preview alias is not automatically a valid image poster.
- Existing gallery tests abort video requests and check source binding/error handling. The previous real-media visual check only asserts image decoding. Neither asserts that video pixels become visible.

## Acceptance and scope
- A visible video card paints a real decoded frame without the user opening playback, both on initial view and after scrolling to a preloaded card.
- Verify real published media and a deterministic decodable MP4 fixture, including actual screenshot pixels; do not repair media from inside the test by calling play(), load() or assigning currentTime.
- Preserve canonical result ordering, full bound URLs, counters, hidden-prompt protections and explicit repeat/paid launch. No generation or payment writes are part of verification.
- Keep near-viewport activation and paused/silent feed behavior. Handle event ordering, source replacement and removed elements without false readiness.
- No schema, provider, price or admin configuration change is intended. Client media lifecycle is not a mutable business parameter.
- mini_app: affected shared React feed. site/text Telegram bot: no HTML feed-preview lifecycle applies; source and business contracts stay consistent.
- Observability uses temporary redacted media-event, readiness and network diagnostics plus visible pixels; no real prompts, credentials or private references in Git.

## Execution
1. [x] Verify production/main baseline and screenshot; inspect media/source/lifecycle/test contracts.
2. [x] Capture eight published video references using a read-only database transaction; anonymize fixture authors and keep the fixture outside Git.
3. [x] Establish two failing regressions before implementation: premature frame readiness after load reset, and ignored HTTP byte ranges.
4. [x] Repair the lifecycle and native media delivery; pass focused Chromium/WebKit, source/counter and Nginx checks.
5. [ ] Independent review and exact-head CI; native squash auto-merge.
6. [ ] Exact merge-SHA autodeploy, deployed artifact verification and real-media confirmation.

## Evidence
- Public feed HTTP endpoints correctly require authentication (401); no auth bypass was introduced. Diagnostic media comes only from existing public publications, read through an explicitly read-only transaction.
- Initial source audit identified the load/seek ordering bug but does not yet establish it as the cause of every card on the screenshot.

## Confirmed transport defect and bounded repair
- Eight existing public MP4s returned HTTP 200 with the entire 4.2–14.3 MB file for `Range: bytes=0-65535`, without `Content-Range` or `Accept-Ranges`. Six have their MP4 `moov` metadata after `mdat`, near the end of the file. The missing byte-range support forces a full transfer before those files can expose their metadata/first frame.
- The canonical APIX HTTPS vhosts previously proxied these legacy `/static/upload/feed/` URLs to the application's static-file response. Nginx already has the same upload directory mounted read-only; a narrow native alias supplies byte ranges without changing URLs, rewriting publications or modifying media.
- The alias serves GET/HEAD natively, retains file validators and existing allowed-origin CORS, disables indexes and symlinks, and rejects hidden paths. OPTIONS alone delegates to the existing application through a named location, preserving method, URI/query and request headers; the application remains the authority for preflight decisions. Sibling uploads retain their existing application route. Errors have `no-store`; successful files do not acquire a new long cache lifetime. The status-derived map is volatile because the range filter can change a response to 416 after the first header evaluation.
- No database, schema, price, provider, admin configuration, Compose mount or dependency changes. No paid generations or production data writes. This is fixed HTTP/media lifecycle behavior, not mutable product configuration.

## Test-first evidence and limits
- Unit RED on baseline: `a metadata-ready preview is primed only after the post-load seek produces a frame` fails because the old implementation leaves `apixFramePrimed=1` after load resets the seek. GREEN: all 150 unit tests pass after moving load before seek and confirming a decoded current frame with no pending seek.
- Nginx RED on baseline: all four new transport/security/CORS cases fail; the primary range assertion observes 200/full body instead of 206. The harness uses the actual canonical configurations, synthetic TLS, isolated random loopback ports, a read-only synthetic upload mount and an old-behavior upstream. No production certificates or services enter the harness.
- Nginx GREEN: all 21 module tests pass, including exact prefix/middle/suffix/open-ended bytes, 416, GET/HEAD, 304, If-Range, allowed/disallowed origins, denied writes, hidden/encoded paths, symlinks, directories and unchanged sibling routing. The additional preflight delegation regression was first witnessed RED (403) and is now GREEN for trusted and untrusted origins across all three HTTPS hostnames. CI explicitly enables this official-image harness, so these checks do not silently skip there.
- Build/typecheck and 12 focused Chromium cases pass (gallery, counters and first frames). The two focused WebKit first-frame cases pass. The new pixel cases decode a checked-in 2,294-byte H.264 fixture and inspect rendered screenshot pixels for every video, on initial view and after offscreen metadata has loaded. They do not call play/load/seek from the test.
- The tiny-MP4 pixel cases also passed on the baseline; they close the previous coverage gap but are not the RED proof. The unit and actual Nginx transport cases provide that proof.
- Direct baseline Chromium inspection of eight public videos paints all eight on the fast server network, despite receiving full HTTP 200 bodies. This does not invalidate the transport defect or establish that every possible real file is repaired.
- The Linux WebKit diagnostic initially rejects the public media TLS chain (`Unacceptable TLS certificate`, media error 4); Node HTTPS inside the same container and the host's normal Python TLS verifier both validate the public certificate. Decode isolation uses the real unmodified HTTPS responses fetched with normal TLS verification, not an insecure production change. Deterministic browser CI does not depend on external media or disable TLS verification.
- With the repaired client, all eight sampled public videos decode and paint in Chromium with direct media requests, and all eight paint in WebKit through that verified HTTPS transport. No API writes occur. These pre-release runs still use the old public media server; native range delivery must also be checked after normal autodeploy.
- Independent reviewers found no blocking issues in the lifecycle change, decoded-frame cases, focused WebKit CI configuration or the bounded Nginx alias. Existing Chromium gates, workflow permissions and other CI jobs remain unchanged.

## Delivery and verification still required
- The required exact-head GitHub checks and normal protected-branch squash auto-merge must complete before production is considered repaired.
- The merge SHA must pass Production Autodeploy and public health. Verify the served Nginx configuration and the actual deployed web artifact, then check public prefix/suffix/invalid ranges and real rendered video frames again.
- Final merge/deploy identifiers and runtime evidence belong in the delivery PR because they do not exist when this source commit is written. Stop the owned QA container after verification.
