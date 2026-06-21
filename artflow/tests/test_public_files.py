from __future__ import annotations

from api import public_files

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00"


def test_detect_image_extension_reads_magic_bytes() -> None:
    assert public_files.detect_image_extension(PNG) == ".png"


def test_ensure_public_image_url_creates_jpg_for_legacy_bin(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "WEBHOOK_URL", "https://example.test")
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")
    legacy = tmp_path / "legacy.bin"
    legacy.write_bytes(JPEG)

    url = public_files.ensure_public_image_url("https://example.test/static/upload/legacy.bin")

    assert url == "https://example.test/static/upload/legacy.jpg"
    assert (tmp_path / "legacy.jpg").read_bytes().startswith(b"\xff\xd8\xff")


def test_local_upload_path_ignores_external_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    assert public_files.local_upload_path_from_url("https://cdn.test/file.jpg") is None


def test_public_url_is_available_filters_missing_local_upload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")

    assert public_files.public_url_is_available("https://example.test/static/upload/missing.jpg") is False
    assert public_files.public_url_is_available("https://cdn.test/file.jpg") is True


def test_public_url_is_available_accepts_existing_local_upload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")
    (tmp_path / "ok.jpg").write_bytes(JPEG)

    assert public_files.public_url_is_available("https://example.test/static/upload/ok.jpg") is True
