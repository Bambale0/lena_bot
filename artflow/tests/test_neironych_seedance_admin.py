from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from api.neironych_seedance import (
    NeironychSeedanceClient,
    NeironychSeedanceError,
    parse_seedance_prices,
)
from core.neironych_seedance_contract import (
    SeedanceContractError,
    build_seedance_payload,
    get_seedance_spec,
    normalize_seedance_request,
)


def test_seedance_specs_match_live_neironych_contract() -> None:
    s20 = get_seedance_spec("seedance-2.0")
    assert (s20.min_duration, s20.max_duration) == (4, 15)
    assert s20.resolutions == ("480p", "720p", "1080p", "4k")
    assert (s20.max_image_refs, s20.max_video_refs, s20.max_audio_refs, s20.max_total_refs) == (9, 3, 3, 12)
    assert s20.supports_edit is False

    s25 = get_seedance_spec("seedance-2.5")
    assert (s25.min_duration, s25.max_duration) == (4, 30)
    assert s25.resolutions == ("480p", "720p", "1080p")
    assert (s25.max_image_refs, s25.max_video_refs, s25.max_audio_refs, s25.max_total_refs) == (30, 10, 10, 50)
    assert s25.supports_edit is True


def test_seedance_20_reference_payload_uses_canonical_fields() -> None:
    payload = build_seedance_payload(
        model="seedance-2.0",
        mode="reference",
        prompt="Use @Image 1 and @Video 1",
        resolution="1080p",
        duration=12,
        aspect_ratio="9:16",
        image_urls=["https://cdn.example/a.jpg"],
        video_urls=["https://cdn.example/motion.mp4"],
        audio_urls=["https://cdn.example/music.mp3"],
    )
    assert payload == {
        "prompt": "Use @Image 1 and @Video 1",
        "resolution": "1080p",
        "duration": 12,
        "aspect_ratio": "9:16",
        "reference_images": [{"url": "https://cdn.example/a.jpg"}],
        "reference_videos": [{"url": "https://cdn.example/motion.mp4"}],
        "reference_audios": [{"url": "https://cdn.example/music.mp3"}],
        "generate_audio": True,
    }


def test_seedance_25_reference_sets_reference_task_type() -> None:
    payload = build_seedance_payload(
        model="seedance-2.5",
        mode="reference",
        prompt="Use @Image1",
        resolution="720p",
        duration=8,
        aspect_ratio="16:9",
        image_urls=["https://cdn.example/a.jpg"],
    )
    assert payload["omni_reference_task_type"] == "reference"
    assert payload["reference_images"] == [{"url": "https://cdn.example/a.jpg"}]


def test_seedance_25_edit_follows_source_video() -> None:
    payload = build_seedance_payload(
        model="seedance-2.5",
        mode="edit",
        prompt="Replace the sky in @Video 1 with a sunset",
        resolution="720p",
        video_urls=["https://cdn.example/source.mp4"],
        image_urls=["https://cdn.example/look.jpg"],
    )
    assert payload["omni_reference_task_type"] == "edit"
    assert payload["reference_videos"][0]["url"].endswith("source.mp4")
    assert "duration" not in payload
    assert payload.get("aspect_ratio") in (None, "adaptive")


def test_seedance_25_frame_is_adaptive_and_does_not_mix_refs() -> None:
    payload = build_seedance_payload(
        model="seedance-2.5",
        mode="frame",
        prompt="Smooth transition",
        resolution="720p",
        duration=5,
        aspect_ratio="16:9",
        start_image_url="https://cdn.example/start.jpg",
        end_image_url="https://cdn.example/end.jpg",
    )
    assert payload["start_image"] == {"url": "https://cdn.example/start.jpg"}
    assert payload["end_image"] == {"url": "https://cdn.example/end.jpg"}
    assert payload["aspect_ratio"] == "adaptive"
    assert "reference_images" not in payload


def test_seedance_20_audio_requires_visual_reference() -> None:
    with pytest.raises(SeedanceContractError, match="фото или видео"):
        build_seedance_payload(
            model="seedance-2.0",
            mode="reference",
            prompt="Use @Audio 1",
            resolution="720p",
            duration=5,
            aspect_ratio="16:9",
            audio_urls=["https://cdn.example/music.mp3"],
        )


def test_prompt_reference_integrity_fails_before_paid_submit() -> None:
    with pytest.raises(SeedanceContractError, match="@Image2"):
        normalize_seedance_request(
            "seedance-2.5",
            {
                "prompt": "Keep @Image 1 and @Image2 consistent",
                "duration": 8,
                "resolution": "720p",
                "aspect_ratio": "16:9",
                "reference_images": [{"url": "https://cdn.example/only.jpg"}],
            },
        )


def test_prompt_limit_is_40000_utf8_bytes() -> None:
    ok = normalize_seedance_request(
        "seedance-2.0",
        {
            "prompt": "я" * 20_000,
            "duration": 8,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        },
    )
    assert len(ok["prompt"].encode()) == 40_000
    with pytest.raises(SeedanceContractError, match="40 000"):
        normalize_seedance_request(
            "seedance-2.0",
            {
                "prompt": "я" * 20_001,
                "duration": 8,
                "resolution": "720p",
                "aspect_ratio": "16:9",
            },
        )


def test_live_price_parser_reads_both_seedance_versions_and_leaves_unpublished_4k_empty() -> None:
    html = """
    <table><tbody>
      <tr><td>seedance-2.0</td><td>default / 480p</td><td class="price-number">6.80</td><td>секунда</td></tr>
      <tr><td>seedance-2.0</td><td>default / 720p</td><td class="price-number">14.11</td><td>секунда</td></tr>
      <tr><td>seedance-2.0</td><td>default / 1080p</td><td class="price-number">35.90</td><td>секунда</td></tr>
      <tr><td>Seedance 2.5</td><td>default / 480p</td><td class="price-number">10.00</td><td>секунда</td></tr>
      <tr><td>Seedance 2.5</td><td>default / 720p</td><td class="price-number">21.80</td><td>секунда</td></tr>
      <tr><td>Seedance 2.5</td><td>default / 1080p</td><td class="price-number">55.13</td><td>секунда</td></tr>
    </tbody></table>
    """
    prices = parse_seedance_prices(html)
    assert prices["seedance-2.0"] == {"480p": 6.8, "720p": 14.11, "1080p": 35.9}
    assert "4k" not in prices["seedance-2.0"]
    assert prices["seedance-2.5"]["1080p"] == 55.13


@pytest.mark.asyncio
async def test_client_uses_documented_async_video_contract(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/v1/models":
            return httpx.Response(200, json={"object": "list", "data": [{"id": "seedance-2.0"}, {"id": "seedance-2.5"}]})
        if request.method == "POST" and request.url.path == "/v1/videos/generations":
            assert request.headers["Authorization"] == "Bearer secret"
            assert request.headers["Idempotency-Key"] == "apix-seedance-test-12345678"
            assert json.loads(request.content) == {
                "model": "seedance-2.5",
                "prompt": "cinematic",
                "duration": 4,
                "resolution": "480p",
                "aspect_ratio": "9:16",
            }
            return httpx.Response(202, json={"request_id": "req-123"})
        if request.method == "GET" and request.url.path == "/v1/videos/req-123":
            return httpx.Response(200, json={"request_id": "req-123", "status": "done", "usage": {"billed_seconds": 4}})
        if request.method == "GET" and request.url.path == "/v1/videos/req-123/content":
            return httpx.Response(200, content=b"mp4", headers={"content-type": "video/mp4"})
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://provider.example") as http_client:
        client = NeironychSeedanceClient("secret", "https://provider.example", client=http_client)
        assert await client.list_models() == ["seedance-2.0", "seedance-2.5"]
        request_id = await client.create_video(
            model="seedance-2.5",
            payload={"prompt": "cinematic", "duration": 4, "resolution": "480p", "aspect_ratio": "9:16"},
            idempotency_key="apix-seedance-test-12345678",
        )
        assert request_id == "req-123"
        result = await client.get_video(request_id)
        assert result.status == "done"
        assert result.billed_seconds == 4
        target = tmp_path / "result.mp4"
        await client.download_content_to(request_id, target, max_bytes=1024)

    assert target.read_bytes() == b"mp4"


@pytest.mark.asyncio
async def test_media_upload_ticket_put_never_leaks_partner_authorization() -> None:
    payload = b"jpeg-bytes"
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            assert request.url.path == "/v1/media/uploads"
            assert request.headers["Authorization"] == "Bearer secret"
            return httpx.Response(201, json={
                "upload_url": "https://storage.example/signed-put",
                "media_url": "https://storage.example/signed-read",
            })
        assert request.method == "PUT"
        assert request.url == httpx.URL("https://storage.example/signed-put")
        assert "Authorization" not in request.headers
        assert request.content == payload
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with (
        httpx.AsyncClient(transport=transport, base_url="https://provider.example") as http_client,
        httpx.AsyncClient(transport=transport) as storage_client,
    ):
        client = NeironychSeedanceClient("secret", "https://provider.example", client=http_client, storage_client=storage_client)
        media_url = await client.upload_media(
            model="seedance-2.5",
            media_type="image",
            content=payload,
            content_type="image/jpeg",
        )
    assert media_url == "https://storage.example/signed-read"


@pytest.mark.asyncio
async def test_client_rejects_new_paid_request_with_short_idempotency_key() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
        base_url="https://provider.example",
    ) as http_client:
        client = NeironychSeedanceClient("secret", "https://provider.example", client=http_client)
        with pytest.raises(NeironychSeedanceError, match="8"):
            await client.create_video(
                model="seedance-2.0",
                payload={"prompt": "x", "duration": 4, "resolution": "480p", "aspect_ratio": "16:9"},
                idempotency_key="short",
            )
