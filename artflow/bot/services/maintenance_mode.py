from __future__ import annotations

from pathlib import Path

_FLAG_PATH = Path("logs/maintenance_mode.flag")


def is_maintenance_mode() -> bool:
    try:
        return _FLAG_PATH.read_text(encoding="utf-8").strip() == "1"
    except FileNotFoundError:
        return False


def set_maintenance_mode(enabled: bool) -> None:
    _FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _FLAG_PATH.write_text("1" if enabled else "0", encoding="utf-8")
