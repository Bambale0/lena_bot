from types import SimpleNamespace

import pytest

from api.web import generations


@pytest.mark.asyncio
async def test_upload_policy_uses_the_same_limit_as_server_validation(monkeypatch):
    monkeypatch.setattr(generations, "MAX_WEB_REFERENCE_IMAGE_BYTES", 12345)
    result = await generations.upload_media_policy(SimpleNamespace(id=7))
    assert result["data"]["image_max_bytes"] == 12345
    assert result["data"]["image_formats"] == ["jpeg", "png", "webp"]


@pytest.mark.asyncio
async def test_upload_policy_requires_an_authenticated_actor():
    response = await generations.upload_media_policy(None)
    assert response.status_code == 401


@pytest.mark.parametrize(("header", "mime"), [(b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "image/png"), (b"RIFF1234WEBP", "image/webp")])
def test_advertised_formats_match_existing_validator(header, mime):
    assert generations._file_upload_error_or_kind(header, mime) == (None, "image")


@pytest.mark.asyncio
async def test_upload_acknowledgement_keeps_real_media_metadata(monkeypatch):
    from io import BytesIO

    from fastapi import UploadFile
    from starlette.datastructures import Headers
    data = b"\x89PNG\r\n\x1a\n" + b"sample"
    monkeypatch.setattr(generations, "save_public_file", lambda content, mime, subdir: "https://media.example.test/file.png")
    file = UploadFile(BytesIO(data), filename="file.png", headers=Headers({"content-type": "image/png"}))
    result = await generations.upload_media(file, SimpleNamespace(id=7))
    assert result["data"] == {"url": "https://media.example.test/file.png", "kind": "image", "content_type": "image/png", "size": len(data)}


@pytest.mark.asyncio
async def test_unauthenticated_upload_does_not_read_or_save_bytes():
    from unittest.mock import AsyncMock
    file = SimpleNamespace(read=AsyncMock())
    result = await generations.upload_media(file, None)
    assert result.status_code == 401
    file.read.assert_not_awaited()
