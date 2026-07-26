#!/usr/bin/env python3
"""Strict CI gate: every provider contract must be externally executable."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import bindings before reading the registry so primary models use the fullest
# typed implementation.
from api import provider_operation_bindings as _bindings  # noqa: F401,E402
from api.provider_contract_catalog import ALL_CONTRACTS  # noqa: E402
from api.provider_operation_registry import OPERATION_SPECS, PUBLIC_API_CONTRACT_IDS  # noqa: E402


def validate_product_readiness() -> list[str]:
    errors: list[str] = []
    catalog_ids = {contract.contract_id for contract in ALL_CONTRACTS}
    registry_ids = set(OPERATION_SPECS)
    public_ids = set(PUBLIC_API_CONTRACT_IDS)

    if missing := sorted(catalog_ids - registry_ids):
        errors.append(f"catalog contracts missing executors: {missing}")
    if unknown := sorted(registry_ids - catalog_ids):
        errors.append(f"operation registry has unknown contracts: {unknown}")
    if missing := sorted(catalog_ids - public_ids):
        errors.append(f"contracts missing public API exposure: {missing}")

    smoke_ids: list[str] = []
    for contract in ALL_CONTRACTS:
        spec = OPERATION_SPECS.get(contract.contract_id)
        if spec is None:
            continue
        if spec.billable and not contract.live_smoke_id:
            errors.append(f"{contract.contract_id}: billable contract has no live_smoke_id")
        if contract.live_smoke_id:
            smoke_ids.append(contract.live_smoke_id)

    if len(smoke_ids) != len(set(smoke_ids)):
        errors.append("live_smoke_id values must be unique")

    return errors


def main() -> int:
    errors = validate_product_readiness()
    if errors:
        print("Provider product readiness failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Provider product readiness OK: {len(ALL_CONTRACTS)} public contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
