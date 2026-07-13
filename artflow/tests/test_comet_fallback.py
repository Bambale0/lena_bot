from __future__ import annotations

import pytest

from api import comet_fallback, image_service, video_service
from api.image_service import ImageModel
from api.video_service import VideoModel


@pytest.mark.asyncio
async def test_generate_image_fallback_passes_reference_urls(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"data": [{"url": "https://cdn.example.test/result.jpg"}]}

    monkeypatch.setattr(comet_fallback.comet_client, "post", fake_post)

    result = await comet_fallback.generate_image(
        model_key="wan/2-7-image-pro",
        prompt="make a campaign visual",
        reference_urls=["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"],
        aspect_ratio="16:9",
        count=2,
    )

    assert result.urls == ["https://cdn.example.test/result.jpg"]
    assert calls[0][0] == "/v1/images/generations"
    assert calls[0][1]["model"] == "doubao-seedream-4-5-251128"
    assert calls[0][1]["image"] == ["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"]
    assert calls[0][1]["n"] == 2
    assert calls[0][1]["size"] == "2848x1600"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_model", "comet_model"),
    [
        ("nano-banana-2", "gemini-3.1-flash-image-preview"),
        ("nano-banana-pro", "gemini-3-pro-image-preview"),
    ],
)
async def test_generate_nano_banana_fallback_uses_gemini_with_inline_references(
    monkeypatch,
    source_model: str,
    comet_model: str,
) -> None:
    calls: list[tuple[str, dict]] = []
    saved: list[tuple[bytes, str | None]] = []

    async def fake_inline_image_part(url: str) -> dict:
        return {"inlineData": {"mimeType": "image/jpeg", "data": f"encoded:{url}"}}

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"inlineData": {"mimeType": "image/png", "data": "aW1n"}},
                        ],
                    },
                },
            ],
        }

    def fake_save_public_file(data: bytes, content_type: str | None = None) -> str:
        saved.append((data, content_type))
        return "https://cdn.example.test/gemini-result.png"

    monkeypatch.setattr(comet_fallback, "_inline_image_part_from_url", fake_inline_image_part)
    monkeypatch.setattr(comet_fallback.comet_client, "post", fake_post)
    monkeypatch.setattr(comet_fallback, "save_public_file", fake_save_public_file)

    result = await comet_fallback.generate_image(
        model_key=source_model,
        prompt="merge these references",
        reference_urls=["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"],
        aspect_ratio="16:9",
        count=4,
        resolution="4K",
    )

    assert result.urls == ["https://cdn.example.test/gemini-result.png"]
    assert calls[0][0] == f"/v1beta/models/{comet_model}:generateContent"
    payload = calls[0][1]
    assert payload["generationConfig"] == {
        "responseModalities": ["IMAGE"],
        "imageConfig": {"aspectRatio": "16:9", "imageSize": "4K"},
    }
    parts = payload["contents"][0]["parts"]
    assert parts[0] == {"text": "merge these references"}
    assert [part["inlineData"]["data"] for part in parts[1:]] == [
        "encoded:https://example.test/ref1.jpg",
        "encoded:https://example.test/ref2.jpg",
    ]
    assert saved == [(b"img", "image/png")]


@pytest.mark.asyncio
async def test_generate_seedance_video_repeats_reference_fields(monkeypatch) -> None:
    calls: list[tuple[str, dict, list[tuple[str, object]]]] = []

    async def fake_post_multipart(path: str, data: dict, files: list[tuple[str, object]]) -> dict:
        calls.append((path, data, files))
        return {"id": "seedance_task_1", "status": "queued"}

    monkeypatch.setattr(comet_fallback.comet_client, "post_multipart", fake_post_multipart)

    result = await comet_fallback.generate_video(
        model_key="wan/2-7-image-to-video",
        prompt="slow camera push",
        reference_urls=["https://example.test/start.jpg", "https://example.test/style.jpg"],
        duration=5,
        aspect_ratio="9:16",
        resolution="720p",
        callback_url="https://api.example.test/webhook/kie?secret=abc",
    )

    assert result.task_id == "comet:video:seedance_task_1"
    assert result.uses_webhook is True
    assert calls[0][0] == "/v1/videos"
    fields = calls[0][2]
    assert ("model", (None, "doubao-seedance-2-0")) in fields
    assert ("size", (None, "720x1280")) in fields
    assert [value for name, value in fields if name == "input_reference"] == [
        (None, "https://example.test/start.jpg"),
        (None, "https://example.test/style.jpg"),
    ]
    assert ("callback_url", (None, "https://api.example.test/webhook/kie?secret=abc&provider=comet&comet_kind=video")) in fields


@pytest.mark.asyncio
async def test_generate_veo_fallback_omits_unsupported_seconds(monkeypatch) -> None:
    calls: list[list[tuple[str, object]]] = []

    async def fake_post_multipart(path: str, data: dict, files: list[tuple[str, object]]) -> dict:
        calls.append(files)
        return {"id": "veo_task_1", "status": "queued"}

    monkeypatch.setattr(comet_fallback.comet_client, "post_multipart", fake_post_multipart)

    result = await comet_fallback.generate_video(
        model_key="veo3_fast",
        prompt="paper kite over a field",
        reference_urls="https://example.test/start.jpg",
        duration=15,
        aspect_ratio="16:9",
    )

    assert result.task_id == "comet:video:veo_task_1"
    assert ("model", (None, "veo3-fast")) in calls[0]
    assert ("size", (None, "16x9")) in calls[0]
    assert "seconds" not in {name for name, _value in calls[0]}


@pytest.mark.asyncio
async def test_generate_kling_multi_reference_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"data": {"task_id": "kling_task_1"}}

    monkeypatch.setattr(comet_fallback.comet_client, "post", fake_post)

    result = await comet_fallback.generate_video(
        model_key="kling-3.0/video",
        prompt="subject walks forward",
        reference_urls=["https://example.test/person.jpg", "https://example.test/outfit.jpg"],
        duration=10,
        resolution="1080p",
    )

    assert result.task_id == "comet:kling-multi-image2video:kling_task_1"
    assert result.uses_webhook is False
    assert calls[0][0] == "/kling/v1/videos/multi-image2video"
    assert calls[0][1]["image_list"] == [
        {"image": "https://example.test/person.jpg"},
        {"image": "https://example.test/outfit.jpg"},
    ]
    assert calls[0][1]["mode"] == "pro"


@pytest.mark.asyncio
async def test_generate_kling_adds_webhook_callback_with_kind(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"data": {"task_id": "kling_task_1"}}

    monkeypatch.setattr(comet_fallback.comet_client, "post", fake_post)

    result = await comet_fallback.generate_video(
        model_key="kling-2.6/image-to-video",
        prompt="subject waves",
        reference_urls="https://example.test/person.jpg",
        duration=5,
        callback_url="https://api.example.test/webhook/kie?secret=abc",
    )

    assert result.task_id == "comet:kling-image2video:kling_task_1"
    assert result.uses_webhook is True
    assert calls[0][1]["callback_url"] == (
        "https://api.example.test/webhook/kie?secret=abc&provider=comet&comet_kind=kling-image2video"
    )


@pytest.mark.asyncio
async def test_generate_kling_prefers_provider_task_id_over_request_id(monkeypatch) -> None:
    async def fake_post(path: str, payload: dict) -> dict:
        return {"request_id": "query_request", "data": {"task_id": "provider_task"}}

    monkeypatch.setattr(comet_fallback.comet_client, "post", fake_post)

    result = await comet_fallback.generate_video(
        model_key="kling-2.6/text-to-video",
        prompt="tiny camera move",
        duration=5,
    )

    assert result.task_id == "comet:kling-text2video:provider_task"


@pytest.mark.asyncio
async def test_poll_kling_status_reads_nested_video_url(monkeypatch) -> None:
    paths: list[str] = []

    async def fake_get(path: str) -> dict:
        paths.append(path)
        return {
            "data": {
                "task_status": "succeed",
                "task_result": {"videos": [{"url": "https://cdn.example.test/video.mp4"}]},
            }
        }

    monkeypatch.setattr(comet_fallback.comet_client, "get", fake_get)

    assert await comet_fallback.poll_status("comet:kling-image2video:task_1") == "https://cdn.example.test/video.mp4"
    assert paths == ["/kling/v1/videos/image2video/task_1"]


@pytest.mark.asyncio
async def test_image_service_uses_comet_fallback_after_kie_create_error(monkeypatch) -> None:
    comet_calls: list[dict] = []

    async def fake_create_task(payload: dict, callback_url: str | None = None) -> dict:
        raise RuntimeError("kie down")

    async def fake_generate_image(**kwargs):
        comet_calls.append(kwargs)
        return comet_fallback.CometImageResult(urls=["https://cdn.example.test/image.jpg"])

    monkeypatch.setattr(image_service.kieai_client, "create_task", fake_create_task)
    monkeypatch.setattr(image_service.comet_fallback, "generate_image", fake_generate_image)

    result = await image_service.generate_image(
        ImageModel.WAN_27_PRO,
        "new editorial look",
        image_url=["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"],
        aspect_ratio="3:4",
        n=1,
        quality="2K",
    )

    assert result.is_async is False
    assert result.url == "https://cdn.example.test/image.jpg"
    assert result.result_urls == ["https://cdn.example.test/image.jpg"]
    assert comet_calls[0]["reference_urls"] == ["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"]
    assert comet_calls[0]["resolution"] == "2K"
    assert comet_calls[0]["prompt"] == "new editorial look"


@pytest.mark.asyncio
async def test_image_service_passes_nano_banana_params_to_comet_fallback(monkeypatch) -> None:
    comet_calls: list[dict] = []

    async def fake_create_task(payload: dict, callback_url: str | None = None) -> dict:
        raise RuntimeError("kie down")

    async def fake_generate_image(**kwargs):
        comet_calls.append(kwargs)
        return comet_fallback.CometImageResult(urls=["https://cdn.example.test/image.jpg"])

    monkeypatch.setattr(image_service.kieai_client, "create_task", fake_create_task)
    monkeypatch.setattr(image_service.comet_fallback, "generate_image", fake_generate_image)

    result = await image_service.generate_image(
        ImageModel.NANO_BANANA_2,
        "new editorial look",
        image_url=["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"],
        aspect_ratio="16:9",
        n=4,
        quality="4K",
    )

    assert result.is_async is False
    assert result.url == "https://cdn.example.test/image.jpg"
    assert comet_calls[0]["model_key"] == "nano-banana-2"
    assert comet_calls[0]["reference_urls"] == ["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"]
    assert comet_calls[0]["aspect_ratio"] == "16:9"
    assert comet_calls[0]["resolution"] == "4K"


@pytest.mark.asyncio
async def test_video_service_uses_comet_fallback_after_kie_create_error(monkeypatch) -> None:
    comet_calls: list[dict] = []

    async def fake_create_task(payload: dict, callback_url: str | None = None) -> dict:
        raise RuntimeError("kie down")

    async def fake_generate_video(**kwargs):
        comet_calls.append(kwargs)
        return comet_fallback.CometVideoResult(task_id="comet:video:task_1")

    monkeypatch.setattr(video_service.kieai_client, "create_task", fake_create_task)
    monkeypatch.setattr(video_service.comet_fallback, "generate_video", fake_generate_video)

    result = await video_service.generate_video(
        VideoModel.SEEDANCE_2,
        "animate the reference",
        image_url=["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"],
        duration=5,
        aspect_ratio="16:9",
        callback_url="https://api.example.test/webhook/kie?secret=abc",
    )

    assert result.provider == "comet"
    assert result.task_id == "comet:video:task_1"
    assert comet_calls[0]["callback_url"] == "https://api.example.test/webhook/kie?secret=abc"
    assert comet_calls[0]["reference_urls"] == ["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"]
