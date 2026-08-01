# APIX V4 Release Audit

## Scope

Audit target: `artflow` Telegram Mini App V4 production integration.

Branch:

```text
feat/apix-miniapp-v4-production
```

PR:

```text
#53 feat: clean APIX v4 production Mini App
```

## Executive summary

V4 corrects the main architectural issue from the previous prototype: the Mini App is no longer built by stacking visual override layers on top of a legacy shell.

The current production approach is cleaner:

- one React entrypoint;
- one V4 app shell;
- one V4 CSS layer;
- explicit `.v4*` namespace;
- static regression tests against legacy class leaks;
- real backend API contract retained.

## What improved

### 1. Entrypoint hygiene

`main.jsx` now imports only:

```text
AppV4.jsx
apix.v4.css
```

This removes CSS precedence ambiguity from the prior implementation.

### 2. Visual namespace isolation

V4 uses `.v4*` classes only. This prevents accidental inheritance from old classes such as:

```text
apixHero
studioCard
bottomNav
feedFeature
```

### 3. Telegram Mini App constraints

The CSS includes:

```text
env(safe-area-inset-top)
env(safe-area-inset-bottom)
touch-action: manipulation
prefers-reduced-motion
```

This is appropriate for a Telegram WebView surface.

### 4. Feed-first IA

The feed starts with tabs/filters and content. There is no oversized marketing hero above the masonry grid. This matches the product goal: visual discovery first, not a landing page.

### 5. Media safety

V4 separates real playable video from static image previews by extension:

```text
.mp4
.mov
.webm
```

This prevents `.webp` previews from being mounted as `<video>`.

### 6. API continuity

The V4 frontend keeps current API routes and headers. No backend route is invented for payments or generation.

## Risks still present

### 1. Demo assets are still inline

`archiveAssets.js` contains inline WebP data URIs. This is acceptable for preview, but not ideal for a long-term production repository.

Recommendation:

```text
Move demo media to hashed .webp files under public/feed/ or CDN.
```

### 2. AppV4 is still a large single file

`AppV4.jsx` is acceptable for a controlled production cut, but not ideal for long-term maintenance.

Recommended decomposition after approval:

```text
src/apix-v4/
  App.jsx
  api.js
  components/
  screens/
  styles/
```

### 3. Browser preview and Telegram runtime behave differently

The app intentionally supports browser preview fallback, but final approval must happen inside Telegram WebView.

### 4. Payment flow depends on plan URLs

Balance sheet opens `invoice_url`, `pay_url`, or `url` if backend returns them. It does not invent a payment endpoint. This is correct but should be product-verified.

### 5. CI coverage is static-heavy

Current regression tests protect contracts and structure. They do not replace real visual QA in Telegram.

## Release blockers

Before production merge:

- CI must be green or any failure must be explicitly classified as unrelated;
- `npm run build` must pass on server;
- V4 bundle marker must be found in `dist/assets`;
- legacy UI markers must be absent;
- Telegram WebView screenshot must be approved;
- one successful image generation flow must be tested;
- one successful video generation flow must be tested;
- rollback commit must be saved.

## Commercial QA checklist

### Visual

- Feed looks materially different from legacy UI.
- No large rectangular hero blocks above the feed.
- Cards render media without broken image icons.
- Glassmorphism is subtle, not heavy plastic.
- Bottom nav does not feel like a large block.
- CTA states are obvious.

### UX

- One tap to move from feed item to remix.
- Create flow is understandable without instructions.
- Prompt by photo is discoverable.
- Prompt improve is discoverable.
- Empty/error states are calm and useful.
- No dev/debug labels are visible in production.

### Technical

- No legacy style imports.
- No transform plugins.
- API headers are preserved.
- WebP/JPG previews are not rendered as video.
- Safe area is respected.
- Reduced motion is respected.
- No horizontal scroll on normal mobile widths.

### Operations

- Docker image is rebuilt without cache for staging approval.
- Cloudflare `/app/*` cache is purged after deployment.
- `index.html` is not cached aggressively.
- Healthcheck returns OK.

## Recommendation

Proceed with PR #53 as the production candidate, not PR #52.

Keep PR #53 draft until:

1. Provider Contract Compliance is green.
2. APIX CI/CD is green.
3. Server build is verified.
4. Telegram WebView screenshot is approved.

After that, mark PR #53 ready for review and merge only with explicit approval.
