# APIX provider contract coverage

This dashboard is generated from `api/provider_contract_catalog.py` and validated by `scripts/check_provider_contracts_ci.py`.

## Current program snapshot

| Metric | Status |
|---|---:|
| Registered contracts | 87 |
| Image models represented | 19 / 19 |
| Primary video models represented | 20 / 20 |
| Advanced video operations represented | 13 / 13 |
| Suno operations represented | 20 / 20 |
| Midjourney operations represented | 10 / 10 |
| LLM / vision contracts represented | 5 / 5 |
| Contracts with declared smoke scenario IDs | 85 / 87 |
| Contracts currently exposed to a user surface | 47 / 87 |

`fetch` and `list-by-condition` Midjourney operations do not consume credits and therefore do not require standalone paid smoke scenarios.

## Readiness levels

### Contract-valid

A contract is contract-valid when all of the following are present:

- a current official documentation reference;
- a documentation verification date;
- at least one callable backend entrypoint;
- at least one contract-test file;
- explicit modes for the model or operation.

Run:

```bash
cd artflow
python scripts/check_provider_contracts_ci.py
```

### Product-ready

A contract is product-ready only when it is also available through Telegram, Mini App or the public API and has an executable live-smoke scenario.

Run the strict report:

```bash
cd artflow
python scripts/check_provider_contract_coverage.py --strict-product
```

The strict check is intentionally not enabled in CI on this branch because advanced video and Suno operations still need public API/UI wiring. The final integration branch must enable it and bring the missing user-surface count to zero.

## Generated artifacts

To regenerate the complete per-contract Markdown and JSON tables:

```bash
cd artflow
python scripts/check_provider_contract_coverage.py --write
```

Do not maintain model inventories manually in frontend code. New models must first be added to the typed provider contract catalog and must include docs, backend, tests, billing behavior, user exposure and a smoke ID.
