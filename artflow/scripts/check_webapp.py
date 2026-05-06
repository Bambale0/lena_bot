from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    for module in ("api.webapp_auth", "api.webapp_routes", "main"):
        importlib.import_module(module)
    print("webapp imports ok")


if __name__ == "__main__":
    main()
