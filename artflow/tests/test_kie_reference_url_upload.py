from unittest.mock import AsyncMock

import httpx
import pytest

from api import kieai_client, public_files


def uploaded(**overrides):
    data = {
        "downloadUrl": "https://kie-files.test/staged.png", "fileSize": 1024,
        "mimeType": "image/png",
    }
    data.update(overrides)
    return {"code": 200, "success": True, "data": data}


@pytest.mark.asyncio
async def test_remote_reference_is_fetched_by_kie_not_apix(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.host == "kieai.redpandaai.co"
        assert request.url.path == "/api/file-url-upload"
        import json
        assert json.loads(request.content) == {
            "fileUrl": "https://remote.test/ref.png", "uploadPath": "images/apix-refs",
        }
        return httpx.Response(200, json=uploaded())

    monkeypatch.setattr(public_files, "download_public_url", AsyncMock(side_effect=AssertionError("no APIX remote fetch")))
    async with httpx.AsyncClient(base_url="https://kieai.redpandaai.co", transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(kieai_client, "get_upload_client", lambda: client)
        assert await kieai_client.upload_reference_image_url("https://remote.test/ref.png") == "https://kie-files.test/staged.png"
    assert len(requests) == 1
    public_files.download_public_url.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"code": 400, "msg": "URL could not be downloaded"},
    {"code": 200, "success": False},
    {"code": 200},
    uploaded(mimeType="text/html"),
    uploaded(fileSize=31 * 1024 * 1024),
    uploaded(fileSize=True),
    uploaded(fileSize=0),
    uploaded(downloadUrl="http://insecure.test/ref.png"),
])
async def test_failed_or_invalid_kie_upload_cannot_authorize_generation(monkeypatch, payload):
    async with httpx.AsyncClient(
        base_url="https://kieai.redpandaai.co",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as client:
        monkeypatch.setattr(kieai_client, "get_upload_client", lambda: client)
        with pytest.raises(ValueError):
            await kieai_client.upload_reference_image_url("https://remote.test/ref.png")


@pytest.mark.asyncio
async def test_free_url_upload_has_bounded_retries(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(503)

    monkeypatch.setattr(kieai_client.asyncio, "sleep", AsyncMock())
    async with httpx.AsyncClient(base_url="https://kieai.redpandaai.co", transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(kieai_client, "get_upload_client", lambda: client)
        with pytest.raises(RuntimeError, match="exhausted"):
            await kieai_client.upload_reference_image_url("https://remote.test/ref.png")
    assert len(requests) == 3
