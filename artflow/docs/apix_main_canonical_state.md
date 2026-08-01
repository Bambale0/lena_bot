# APIX Mini App canonical main state

Updated: 2026-08-02

## Decision

`main` is the only canonical production path for the Telegram Mini App.

The current Mini App strategy is:

```text
compact-feed full runtime
+
concept visual skin
+
regression guard
```

Do not use the old experimental V4/V5/frontend prototype PRs as merge targets.

## Current main commit

```text
adadffbb7b67b2e701fb2202eceddfd661505a38
```

This is the documentation commit on top of the Mini App restore commit. If newer docs-only or CI-only commits appear later, the Mini App verification markers below remain the source of truth.

## Mini App restore commit

```text
175390c6d5f3b1e9f040d722571191dfdc048a55
fix: restore full mini app runtime with concept skin
```

This commit was applied as a fast-forward on top of the then-current `main`, so backend and CI changes from `main` were preserved.

## Runtime

Canonical Mini App runtime:

```text
artflow/webapp/src/main.jsx
```

Expected build marker:

```text
20260731-compact-feed-v3
```

This runtime was restored from the pre-category-home compact feed implementation. It keeps the full Mini App contour:

- feed;
- trends;
- image generation;
- video generation;
- music generation;
- Midjourney module;
- prompt library;
- history;
- profile;
- referrals;
- payments/top-up;
- realtime websocket;
- polling fallback;
- owner/admin cockpit.

## Visual layer

`style.css` is intentionally a thin wrapper:

```css
@import "./style-legacy-base.css";
@import "./legacy-concept.css";
```

Files:

```text
artflow/webapp/src/style-legacy-base.css
artflow/webapp/src/legacy-concept.css
```

`style-legacy-base.css` preserves the working legacy layout.
`legacy-concept.css` applies the approved APIX concept-board visual language.

## Forbidden states

The production Mini App must not use these entrypoints/markers:

```text
./apix/AppV4.jsx
./apix-v5/App.jsx
apix.v4.css
apix-v5/styles
20260731-trend-category-home-v4
```

The bad `trend-category-home-v4` state made trends/category scenarios the visual start screen and caused the broken light UI.

## Regression guard

Canonical guard:

```text
artflow/tests/test_apix_legacy_concept_runtime.py
```

It checks:

- `20260731-compact-feed-v3` is present;
- `trend-category-home-v4` is absent;
- full runtime functions are present;
- generation/payment/admin contracts are present;
- concept CSS wraps legacy CSS;
- V4/V5 experimental entrypoints are not used.

## Closed superseded PRs

These PRs were closed as superseded by the canonical `main` state:

```text
#47 feat: Velvet Luxe Mini App front v2
#48 feat: APIX Velvet Neon concept app
#51 prototype: компактный APIX chrome без лишней высоты
#52 feat: premium integrated APIX Mini App
#54 feat: concept skin for compact-feed Mini App runtime
```

They should be treated as design/history references only, not production candidates.

## Verification commands

```bash
cd /root/mkdir/lena_bot

git fetch origin
git switch main
git reset --hard origin/main

git rev-parse HEAD
```

The exact HEAD may be newer than the Mini App restore commit due to docs/CI commits. Verify the actual Mini App state by markers, not by old branch names.

Build check:

```bash
cd artflow/webapp
rm -rf dist node_modules/.vite
npm ci
npm run build
```

Bundle check:

```bash
grep -R "20260731-compact-feed-v3" dist/assets | head
grep -R "trend-category-home-v4" dist/assets | head
grep -R "APIX legacy runtime concept skin" dist/assets | head
```

Expected:

```text
compact-feed-v3: present
trend-category-home-v4: absent
concept skin: present
```

## Deployment note

After deploying, open the Mini App with a cache-bust query:

```text
https://apixbotai.com/app/?v=compact-feed-concept
```

If Telegram still shows an old screen, purge `/app/*` cache and verify the built container contains the expected markers.
