from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from api.web import generations
from api.web.deps import get_web_user_or_none


@pytest.mark.asyncio
async def test_reference_check_requires_authentication():
    app = FastAPI()
    app.include_router(generations.router, prefix="/api/web")
    app.dependency_overrides[get_web_user_or_none] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/web/upload-media/check", json={"url": "https://example.test/a.png"})
    assert response.status_code == 401


@pytest.fixture
def storage_root(monkeypatch, tmp_path):
    from api import public_files
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_PUBLIC_URL_PATH", "/static/upload")
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_PUBLIC_BASE_URL", "https://media.example.test")
    monkeypatch.setattr(public_files.settings, "WEBHOOK_URL", "https://app.example.test")
    path = tmp_path / "miniapp" / ("a" * 32 + ".png")
    path.parent.mkdir()
    path.write_bytes(b"image fixture")
    return path


@pytest.mark.parametrize("prefix", ["https://media.example.test", "https://app.example.test", ""])
def test_existing_generated_upload_is_available(storage_root, prefix):
    from api.reference_availability import inspect_local_photo_reference
    assert inspect_local_photo_reference(prefix + "/static/upload/miniapp/" + storage_root.name) == "available"


def test_missing_upload_is_not_available(storage_root):
    from api.reference_availability import inspect_local_photo_reference
    storage_root.unlink()
    assert inspect_local_photo_reference("/static/upload/miniapp/" + storage_root.name) == "missing"


def test_empty_file_is_not_available(storage_root):
    from api.reference_availability import inspect_local_photo_reference
    storage_root.write_bytes(b"")
    assert inspect_local_photo_reference("/static/upload/miniapp/" + storage_root.name) == "missing"


def test_filesystem_denial_is_not_a_missing_file(storage_root, monkeypatch):
    from pathlib import Path

    from api.reference_availability import inspect_local_photo_reference
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path == storage_root and kwargs.get("follow_symlinks", True):
            raise PermissionError("synthetic access failure")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "stat", stat)
    assert inspect_local_photo_reference("/static/upload/miniapp/" + storage_root.name) == "temporary_error"


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "http:/static/upload/miniapp/a.png", "//127.0.0.1/secret",
    "https://name:password@media.example.test/static/upload/x.png", "https://localhost/a.png",
    "https://127.0.0.1/a.png", "http://169.254.169.254/latest/meta-data/", "http://[::1]/a.png",
    "/static/upload/miniapp/../private.png", "/static/upload/miniapp/%2e%2e/private.png",
    "/static/upload/miniapp/%252e%252e/private.png", "/static/upload/miniapp/%00.png",
    " https://media.example.test/a.png", "https://media.example.test:invalid/a.png",
])
def test_unsafe_urls_fail_closed_without_network(storage_root, monkeypatch, url):
    import socket

    from api.reference_availability import inspect_local_photo_reference
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS must not be used"))
    assert inspect_local_photo_reference(url) == "forbidden"


@pytest.mark.parametrize("url", ["https://external.example/a.png", "https://media.example.test/secret/a.png", "/static/upload/private/" + "a"*32 + ".png", "/static/upload/miniapp/arbitrary.txt", "/static/upload/miniapp/" + "a"*32 + ".png?signature=unverified"])
def test_unverified_sources_are_unknown_and_never_fetched(storage_root, monkeypatch, url):
    import socket
    import urllib.request

    from api.reference_availability import inspect_local_photo_reference
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: pytest.fail("No DNS for external URL"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("No outbound request/redirect"))
    assert inspect_local_photo_reference(url) == "unknown"


def test_symlink_escape_cannot_expose_a_private_file(storage_root, tmp_path):
    from api.reference_availability import inspect_local_photo_reference
    target = tmp_path.parent / "private-test-file"
    target.write_text("private fixture")
    storage_root.unlink()
    storage_root.symlink_to(target)
    assert inspect_local_photo_reference("/static/upload/miniapp/" + storage_root.name) == "forbidden"


@pytest.mark.parametrize(("tg_id", "expected"), [(123, 200), (456, 403)])
@pytest.mark.asyncio
async def test_http_admin_scope_and_no_private_response_fields(storage_root, monkeypatch, tg_id, expected):
    from api import miniapp_routes
    monkeypatch.setattr(miniapp_routes.settings, "ADMIN_IDS", [123])
    app = FastAPI()
    app.include_router(generations.router, prefix="/api/web")
    app.dependency_overrides[get_web_user_or_none] = lambda: SimpleNamespace(id=7, tg_id=tg_id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/web/upload-media/check", json={"url": "/static/upload/miniapp/" + storage_root.name})
    assert response.status_code == expected
    if expected == 200:
        assert response.json() == {"ok": True, "data": {"status": "available"}}
    assert str(storage_root) not in response.text
    assert storage_root.name not in response.text


@pytest.mark.asyncio
async def test_read_only_check_does_not_log_urls_or_signatures(storage_root, monkeypatch, caplog):
    from api import miniapp_routes
    monkeypatch.setattr(miniapp_routes.settings, "ADMIN_IDS", [123])
    with caplog.at_level("INFO"):
        result = await generations.check_reference_availability(generations.ReferenceCheckRequest(url="https://other.example/photo?private_signature=test-value"), SimpleNamespace(id=7, tg_id=123))
    assert result["data"]["status"] == "unknown"
    assert "ux2_reference_check" in caplog.text
    assert "other.example" not in caplog.text and "private_signature" not in caplog.text
