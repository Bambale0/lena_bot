from __future__ import annotations

import compileall
from pathlib import Path


def test_project_python_sources_compile() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [root / "api", root / "bot", root / "core", root / "db", root / "main.py"]
    assert all(compileall.compile_file(str(path), quiet=1) if path.is_file() else compileall.compile_dir(str(path), quiet=1) for path in targets)


def test_bot_tester_skill_archive_contains_skill_md() -> None:
    from zipfile import ZipFile

    root = Path(__file__).resolve().parents[1]
    with ZipFile(root / "bot-tester.skill") as archive:
        assert "bot-tester/SKILL.md" in archive.namelist()
