# APIX UX convergence audit

Base production SHA: `cbbdf84682530e468aaffe4e0862de216165f675`

Scope: public website, Telegram Mini App, text bot and their shared generation/payment/referral journeys.

## Product goal

APIX should feel like one product across every surface. Users choose the result they want, see only the controls needed for that task, always see the exact price before a paid launch, and use one customer-facing balance language everywhere.

## Priority findings

### P0 / High

- [x] Unify customer-facing currency language: `💋 / поцелуи`; keep `credits` only in internal code/admin technical contexts.
- [x] Align Telegram image generation with the scenario-first video flow instead of forcing model-first entry.
- [x] Add an explicit review/confirmation step before paid music generation.

### P1 / Medium

- [x] Reduce Mini App primary navigation to the core destinations and move secondary destinations behind `Ещё`/profile/services.
- [x] Remove tiny 6–9 px product copy/badges from active mobile surfaces.
- [x] Make Services a real tools catalog, not duplicate navigation.
- [x] Fix Pinterest price symbol from `💎` to `💋`.
- [x] Replace Telegram history's technical list with user-facing task cards/actions.
- [x] Replace zero-count flash/skeleton problems on the public model catalog and remove `credits` wording.

### P2 / Cleanup

- [ ] Remove unreachable/dead Mini App `StudioScreen` after compatibility coverage.
- [ ] Retire shadowed legacy Telegram handlers only after characterization tests prove current entrypoint ownership.
- [ ] Collapse duplicate site authentication generations and keep only Telegram + email/password in the visible product layer.

## Acceptance contract

1. A customer never needs to understand provider route keys or internal `credits` terminology.
2. Every paid generation has a visible final cost before balance is charged.
3. Image, video and music use the same conceptual flow: goal/scenario → model/defaults → inputs → review → launch.
4. Mini App primary navigation fits the core IA without requiring discovery-by-horizontal-scroll.
5. Existing provider payloads, pricing rules, hidden prompts, repeat behavior and payment accounting remain unchanged unless explicitly covered by a task in this document.
6. Existing production dirty files are not used as a development base and are not overwritten by this branch.

## Verification

- [x] Backend focused tests
- [x] Telegram handler/keyboard regression tests
- [ ] Mini App Playwright smoke
- [ ] 300 user-journey Mini App suite
- [x] Website internal-link audit
- [x] Changed-file lint/type checks
