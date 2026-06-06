from __future__ import annotations

import pytest

from api import image_service, openrouter_client, video_service
from api.image_service import ImageModel
from api.video_service import VideoModel


def test_openrouter_model_maps_exclude_legacy_google_nano_banana() -> None:
    assert openrouter_client.image_model_for_source("google/nano-banana") is None
    assert openrouter_client.image_model_for_source("nano-banana-2") == "google/gemini-3.1-flash-image-preview"
    assert openrouter_client.image_model_for_source("nano-banana-pro") == "google/gemini-3-pro-image-preview"
    assert openrouter_client.image_model_for_source("gpt-image-2-text-to-image") == "openai/gpt-5.4-image-2"
    assert openrouter_client.video_model_for_source("wan/2-7-text-to-video") == "alibaba/wan-2.7"
    assert openrouter_client.video_model_for_source("veo3_fast") == "google/veo-3.1-fast"


def test_openrouter_kling_30_routes_pro_to_pro_model_and_std_to_std() -> None:
    assert openrouter_client.video_model_for_source("kling-3.0/video") == "kwaivgi/kling-v3.0-pro"
    assert openrouter_client._video_model_for_request("kling-3.0/video", None) == "kwaivgi/kling-v3.0-pro"
    assert openrouter_client._video_model_for_request("kling-3.0/video", "pro") == "kwaivgi/kling-v3.0-pro"
    assert openrouter_client._video_model_for_request("kling-3.0/video", "std") == "kwaivgi/kling-v3.0-std"


@pytest.mark.asyncio
async def test_image_service_uses_openrouter_primary_for_migrated_model(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_generate_image(**kwargs):
        calls.append(kwargs)
        return openrouter_client.OpenRouterImageResult(urls=["https://cdn.example.test/or.png"])

    async def fail_kie(*_args, **_kwargs):
        raise AssertionError("KIE should not be called when OpenRouter succeeds")

    monkeypatch.setattr(openrouter_client, "configured", lambda: True)
    monkeypatch.setattr(openrouter_client, "generate_image", fake_generate_image)
    monkeypatch.setattr(image_service.kieai_client, "create_task", fail_kie)

    result = await image_service.generate_image(
        ImageModel.NANO_BANANA_PRO,
        "editorial portrait",
        image_url=["https://example.test/ref.jpg"],
        aspect_ratio="9:16",
        quality="4K",
    )

    assert result.is_async is False
    assert result.url == "https://cdn.example.test/or.png"
    assert calls[0]["source_model"] == "nano-banana-pro"
    assert calls[0]["reference_urls"] == ["https://example.test/ref.jpg"]
    assert calls[0]["resolution"] == "4K"


@pytest.mark.asyncio
async def test_image_service_keeps_google_nano_banana_on_existing_provider(monkeypatch) -> None:
    created_payloads: list[dict] = []

    async def fake_create_task(payload: dict, callback_url: str | None = None) -> dict:
        created_payloads.append(payload)
        return {"code": 200, "data": {"taskId": "kie_task"}}

    async def fail_openrouter(*_args, **_kwargs):
        raise AssertionError("google/nano-banana must not be migrated")

    monkeypatch.setattr(openrouter_client, "configured", lambda: True)
    monkeypatch.setattr(openrouter_client, "generate_image", fail_openrouter)
    monkeypatch.setattr(image_service.kieai_client, "create_task", fake_create_task)

    result = await image_service.generate_image(
        ImageModel.NANO_BANANA,
        "small banana icon",
        aspect_ratio="1:1",
    )

    assert result.is_async is True
    assert result.task_id == "kie_task"
    assert created_payloads[0]["model"] == "google/nano-banana"


@pytest.mark.asyncio
async def test_image_service_force_openrouter_blocks_existing_provider_fallback(monkeypatch) -> None:
    async def fail_openrouter(*_args, **_kwargs):
        raise RuntimeError("openrouter down")

    async def fail_kie(*_args, **_kwargs):
        raise AssertionError("KIE should not be called when OpenRouter is forced")

    monkeypatch.setattr(openrouter_client, "configured", lambda: True)
    monkeypatch.setattr(openrouter_client, "force_migrated_models", lambda: True)
    monkeypatch.setattr(openrouter_client, "generate_image", fail_openrouter)
    monkeypatch.setattr(image_service.kieai_client, "create_task", fail_kie)

    with pytest.raises(RuntimeError, match="OpenRouter image generation failed"):
        await image_service.generate_image(
            ImageModel.NANO_BANANA_PRO,
            "editorial portrait",
            aspect_ratio="9:16",
        )


@pytest.mark.asyncio
async def test_video_service_uses_openrouter_primary_for_migrated_model(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_generate_video(**kwargs):
        calls.append(kwargs)
        return openrouter_client.OpenRouterVideoResult(task_id="openrouter:video:job_1")

    async def fail_kie(*_args, **_kwargs):
        raise AssertionError("KIE should not be called when OpenRouter succeeds")

    monkeypatch.setattr(openrouter_client, "configured", lambda: True)
    monkeypatch.setattr(openrouter_client, "generate_video", fake_generate_video)
    monkeypatch.setattr(video_service.kieai_client, "create_task", fail_kie)

    result = await video_service.generate_video(
        VideoModel.WAN_27_T2V,
        "cinematic river shot",
        duration=5,
        aspect_ratio="16:9",
        resolution="1080p",
    )

    assert result.provider == "openrouter"
    assert result.task_id == "openrouter:video:job_1"
    assert result.uses_webhook is False
    assert calls[0]["source_model"] == "wan/2-7-text-to-video"


@pytest.mark.asyncio
async def test_video_service_force_openrouter_blocks_existing_provider_fallback(monkeypatch) -> None:
    async def fail_openrouter(*_args, **_kwargs):
        raise RuntimeError("openrouter down")

    async def fail_kie(*_args, **_kwargs):
        raise AssertionError("KIE should not be called when OpenRouter is forced")

    monkeypatch.setattr(openrouter_client, "configured", lambda: True)
    monkeypatch.setattr(openrouter_client, "force_migrated_models", lambda: True)
    monkeypatch.setattr(openrouter_client, "generate_video", fail_openrouter)
    monkeypatch.setattr(video_service.kieai_client, "create_task", fail_kie)

    with pytest.raises(RuntimeError, match="OpenRouter video generation failed"):
        await video_service.generate_video(
            VideoModel.WAN_27_T2V,
            "cinematic river shot",
            duration=5,
            aspect_ratio="16:9",
            resolution="1080p",
        )


@pytest.mark.asyncio
async def test_openrouter_video_poll_returns_unsigned_url(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_request(method: str, path: str, *, json: dict | None = None) -> dict:
        calls.append((method, path))
        return {"status": "completed", "unsigned_urls": ["https://cdn.example.test/video.mp4"]}

    monkeypatch.setattr(openrouter_client, "_request_with_retry", fake_request)

    assert await openrouter_client.poll_video_status("openrouter:video:job_1") == "https://cdn.example.test/video.mp4"
    assert calls == [("GET", "/videos/job_1")]


@pytest.mark.asyncio
async def test_assistant_text_model_aliases_use_openrouter_ids() -> None:
    assert openrouter_client.text_model_for_source("gpt-5-4") == "openai/gpt-5.4"
    assert openrouter_client.text_model_for_source("gpt-5.4-mini") == "openai/gpt-5.4-mini"
    assert openrouter_client.text_model_for_source("claude-sonnet-4-5") == "anthropic/claude-sonnet-4.5"
