# QA Checklist — APIX Prompt Riot Site

## 1. Public

- `/` opens.
- Hero explains product.
- CTA login works.
- Feed preview loads or shows graceful empty.
- Prompt preview loads or shows graceful empty.
- No stale price/model text.
- Social preview meta present.

## 2. Auth

- Guest cannot run generation.
- Login gate appears for protected action.
- Telegram login success shows profile.
- Login failure has retry.
- No `token=` in URL.
- No `init_data=` in logs.

## 3. Studio

- Stepper visible.
- Required fields validated.
- Run disabled until ready.
- Model and cost shown before run.
- Review panel shows refs/settings.
- Form errors near fields.
- Mobile 390px no horizontal scroll.

## 4. Queue

- Queue item appears after run.
- WS connected state is not noisy.
- Lost WS uses polling fallback.
- Done updates result/history/balance.
- Failed shows reason and refund state.
- No duplicate toast for same generation.

## 5. Results

- Image result card renders.
- Video result card renders.
- Music result card renders.
- Broken media URL shows fallback.
- Multi-result gallery shows all URLs.
- Detail drawer opens.
- Next actions prefill studio correctly.

## 6. Feed

- Recent filter works.
- Top day filter works.
- Detail opens.
- Like disabled during request.
- Share disabled during request.
- Remix explains author idea usage.
- Unsupported media action disabled with reason.

## 7. Prompts

- Catalog loads.
- Popular loads.
- Best loads.
- My prompts loads.
- Tag/category filter works.
- Prompt detail opens.
- Use prompt prefills studio.
- Submit flow reaches pending status.
- Rejected prompt shows reason.

## 8. Billing

- Balance shown.
- Plans loaded dynamically.
- Only enabled methods shown.
- Payment click creates pending state.
- Double-click does not create UI chaos.
- Paid updates balance without refresh.
- Failed/refunded visible.

## 9. Profile/referrals

- Telegram identity visible.
- Referral link copy works.
- Fallback copy works.
- Levels visible.
- Withdrawal validation visible.
- Pending withdrawals shown.

## 10. Admin

- Admin link visible only for admin.
- Pending prompts visible.
- Approve works.
- Reject requires reason.
- Deactivate works.

## 11. Accessibility

- Keyboard navigation works.
- Focus states visible.
- Labels present.
- `aria-live` for queue/status.
- Color not the only status indicator.

## 12. Release commands

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
- viewport 390px
