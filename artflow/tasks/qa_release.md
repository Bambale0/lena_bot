# Codex Task — QA and Release

## Add smoke tests

If Playwright exists:

- public home;
- login mock/dev token;
- studio form fill;
- queue item render;
- feed card actions;
- prompt drawer;
- missing media fallback;
- mobile 390px screenshot.

If Playwright does not exist:

- add manual QA checklist to docs;
- add lightweight browser smoke script if possible.

## Release checks

```bash
node --check landing/js/riot-site.js
tools/codex_static_checks.sh
nginx -t
```

Manual:

- `/api/web/health`
- `/`
- `/api/v1/ws/generations`
- missing `/static/upload/missing.jpg`
- `.logs/bot.log` no secrets
- mobile 390px
