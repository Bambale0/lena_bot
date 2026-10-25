# Bug Report — APIX Studio home previews — 2026-10-25

## Summary
- Critical: 0 open, 1 fixed
- Intermediate: 0 open, 0 fixed
- Normal: 0 open, 0 fixed

## 🔴 Critical

None.

## 🟡 Intermediate

### BUG-001: Video trends are rendered as images on the Studio home page — Fixed 2026-10-25
- **File:** artflow/webapp/src/features/lilac/home-screen.tsx:23
- **Issue:** `HomeThumbnail` always created an `<img>`, even when a trend preview was an MP4 video.
- **Trigger:** Open the black-red Studio home page while the curated trend list contains video trends.
- **Impact:** Every live trend tile failed media decoding and fell back to the spark placeholder; the video background for “Оживить фото” also failed.
- **Suggested Fix:** Pass the media kind into `HomeThumbnail` and render safe video previews with muted inline autoplay/loop semantics while preserving the existing failed-media fallback.
- **Status:** Resolved in `a690fb5`; independently reviewed with no findings.

## 🟢 Normal

None.

## ✅ Resolved

None.
