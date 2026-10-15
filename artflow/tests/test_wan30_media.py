"""No Wan job may be completed against an ephemeral upstream CDN URL."""
from unittest.mock import AsyncMock

import pytest

from api import wan30_media


@pytest.mark.asyncio
async def test_wan_result_is_owned_mp4_url(monkeypatch, tmp_path):
    video=tmp_path/"result.mp4"
    video.write_bytes(b"placeholder")
    saved="https://apixbotai.com/static/upload/provider-results/result.mp4"
    mirror=AsyncMock(return_value=saved)
    monkeypatch.setattr(wan30_media,"mirror_url",mirror)
    monkeypatch.setattr(wan30_media,"local_upload_path_from_url",lambda url: video if url==saved else None)
    assert await wan30_media.mirror_wan30_result("https://provider.example.test/result.mp4")==saved
    mirror.assert_awaited_once_with("https://provider.example.test/result.mp4",subdir="provider-results")


@pytest.mark.asyncio
async def test_wan_raw_expiring_provider_link_does_not_count_as_delivered(monkeypatch):
    upstream="https://provider.example.test/result.mp4"
    monkeypatch.setattr(wan30_media,"mirror_url",AsyncMock(return_value=upstream))
    monkeypatch.setattr(wan30_media,"local_upload_path_from_url",lambda url:None)
    with pytest.raises(RuntimeError,match="stored"):
        await wan30_media.mirror_wan30_result(upstream)


@pytest.mark.asyncio
async def test_wan_bad_result_file_extension_rejected(monkeypatch, tmp_path):
    video = tmp_path / "result.jpg"
    video.write_bytes(b"not-mp4")
    monkeypatch.setattr(wan30_media,"mirror_url",AsyncMock(return_value="https://example.test/result.jpg"))
    monkeypatch.setattr(wan30_media,"local_upload_path_from_url",lambda url:video)
    with pytest.raises(RuntimeError,match="video file"):
        await wan30_media.mirror_wan30_result("https://provider.example.test/result.mp4")
