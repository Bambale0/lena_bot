# Bug Report — APIX Studio home previews — 2026-10-25

## Summary
- Critical: 0 open, 1 fixed
- Intermediate: 0 open, 2 fixed
- Normal: 0 open, 0 fixed

## 🔴 Critical

None.

## 🟡 Intermediate

None.

## 🟢 Normal

None.

## ✅ Resolved

### BUG-001: Video trends are rendered as images on the Studio home page — Fixed 2026-10-25
- **File:** artflow/webapp/src/features/lilac/home-screen.tsx:23
- **Issue:** `HomeThumbnail` always created an `<img>`, even when a trend preview was an MP4 video.
- **Trigger:** Open the black-red Studio home page while the curated trend list contains video trends.
- **Impact:** Every live trend tile failed media decoding and fell back to the spark placeholder; the video background for “Оживить фото” also failed.
- **Suggested Fix:** Pass the media kind into `HomeThumbnail` and render safe video previews with muted inline autoplay/loop semantics while preserving the existing failed-media fallback.
- **Status:** Resolved in `a690fb5`; independently reviewed with no findings.

### BUG-002: Live previews ignore the reduced-motion preference — Fixed 2026-10-25
- **File:** artflow/webapp/src/features/lilac/home-screen.tsx:29
- **Issue:** Every preview autoplayed and called `play()` even when the user requested reduced motion.
- **Trigger:** Open Studio with `prefers-reduced-motion: reduce` enabled.
- **Impact:** Continuous looping motion was forced on users who explicitly disabled it.
- **Suggested Fix:** Gate automatic playback on the media query and present a stable frame when reduced motion is requested.
- **Status:** Resolved in `d4f1388`; final scoped review accepted the behavior.

### BUG-003: Off-screen home previews keep downloading and decoding — Fixed 2026-10-25
- **File:** artflow/webapp/src/features/lilac/home-screen.tsx:29
- **Issue:** Up to eight rail videos plus the duplicate task preview autoplayed outside the viewport.
- **Trigger:** Open the Studio home page with the current video-heavy trend catalog.
- **Impact:** Avoidable concurrent transfers and video decoders increased mobile data, battery and rendering load.
- **Suggested Fix:** Start/pause previews from viewport visibility while preserving the error fallback and visible live behavior.
- **Status:** Resolved across `d4f1388` and `6e43df7`; final scoped review confirmed browser viewport and horizontal clipping behavior.
