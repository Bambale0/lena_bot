from __future__ import annotations

from pathlib import Path

from aiogram.types import FSInputFile

from bot.handlers.marketplace import _prompt_photo_source


def test_prompt_photo_source_uses_fallback_when_preview_missing() -> None:
    source = _prompt_photo_source(None)
    assert isinstance(source, FSInputFile)


def test_prompt_photo_source_uses_local_upload_file(tmp_path, monkeypatch) -> None:
    from api import public_files

    image = tmp_path / "preview.jpg"
    image.write_bytes(b"\xff\xd8\xff")
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "WEBHOOK_URL", "https://example.test")
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")

    source = _prompt_photo_source("https://example.test/static/upload/preview.jpg")

    assert isinstance(source, FSInputFile)
