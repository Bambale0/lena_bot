from __future__ import annotations

import pytest

from api import kieai_client


@pytest.mark.asyncio
async def test_upload_file_stream_uses_upload_path_form_field(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": {"downloadUrl": "https://cdn.example.test/ref.png"}}

    class FakeClient:
        async def post(self, path: str, *, data: dict, files: dict) -> FakeResponse:
            calls.append({"path": path, "data": data, "files": files})
            return FakeResponse()

    monkeypatch.setattr(kieai_client, "get_upload_client", lambda: FakeClient())

    url = await kieai_client.upload_file_stream(
        b"\x89PNG\r\n\x1a\npayload",
        filename="ref.png",
        content_type="image/png",
        upload_path="images/custom",
    )

    assert url == "https://cdn.example.test/ref.png"
    assert calls[0]["path"] == "/api/file-stream-upload"
    assert calls[0]["data"] == {"uploadPath": "images/custom"}
