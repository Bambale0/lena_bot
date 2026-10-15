"""No Wan job may be completed against an ephemeral upstream CDN URL."""
from unittest.mock import AsyncMock

import pytest

from api import wan30_media


@pytest.mark.asyncio
async def test_wan_result_is_owned_mp4_url(monkeypatch, tmp_path):
    video=tmp_path/"result.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 24)
    saved="https://apixbotai.com/static/upload/provider-results/result.mp4"
    from api.media_gateway import MediaProbe

    monkeypatch.setattr(
        wan30_media, "probe_local_media", AsyncMock(return_value=MediaProbe(
            width=1280, height=720, duration_seconds=5.0,
        )),
    )
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

@pytest.mark.asyncio
async def test_wan_mirrored_mp4_html_body_with_mp4_suffix_is_not_final(monkeypatch, tmp_path):
    blob = tmp_path / "error.mp4"
    blob.write_bytes(b"<html>503 upstream</html>")
    url = "https://apixbotai.com/static/upload/provider-results/error.mp4"
    monkeypatch.setattr(wan30_media, "mirror_url", AsyncMock(return_value=url))
    monkeypatch.setattr(wan30_media, "local_upload_path_from_url", lambda _: blob)
    with pytest.raises(RuntimeError, match="MP4"):
        await wan30_media.mirror_wan30_result("https://provider.example.test/clip.mp4")


@pytest.mark.asyncio
async def test_wan_probe_rejects_truncated_mp4_even_with_ftyp_header(monkeypatch, tmp_path):
    from api.media_gateway import MediaProbe

    blob=tmp_path/"broken.mp4"
    blob.write_bytes(b"\x00\x00\x00\x18ftypisom"+b"\x00"*20)
    url="https://apixbotai.com/static/upload/provider-results/broken.mp4"
    monkeypatch.setattr(wan30_media,"mirror_url",AsyncMock(return_value=url))
    monkeypatch.setattr(wan30_media,"local_upload_path_from_url",lambda _:blob)
    probe=AsyncMock(return_value=MediaProbe(width=None,height=None,duration_seconds=None))
    monkeypatch.setattr(wan30_media,"probe_local_media",probe,raising=False)
    with pytest.raises(RuntimeError,match="MP4"):
        await wan30_media.mirror_wan30_result("https://provider.example.test/clip.mp4")


@pytest.mark.asyncio
async def test_wan_probe_rejects_mov_even_with_mp4_name(monkeypatch, tmp_path):
    blob=tmp_path/"pretend.mp4"
    blob.write_bytes(b"\x00\x00\x00\x18ftypqt  "+b"\x00"*20)
    url="https://apixbotai.com/static/upload/provider-results/pretend.mp4"
    monkeypatch.setattr(wan30_media,"mirror_url",AsyncMock(return_value=url))
    monkeypatch.setattr(wan30_media,"local_upload_path_from_url",lambda _:blob)
    with pytest.raises(RuntimeError,match="MP4"):
        await wan30_media.mirror_wan30_result("https://provider.example.test/clip.mp4")
