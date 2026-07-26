#!/usr/bin/env python3
"""CI entrypoint for provider contract metadata and runtime coverage."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_provider_contract_coverage import validate_contracts


def main() -> int:
    errors = validate_contracts(strict_product=False)
    if errors:
        print("Provider contract inventory failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Provider contract inventory is complete and structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
