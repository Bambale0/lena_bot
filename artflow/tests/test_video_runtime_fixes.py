from __future__ import annotations

import pytest

from api import seedance25_adapter, video_service
from api.video_runtime_fixes import VEO_PUBLIC_CAPS, install_video_runtime_fixes


@pytest.mark.asyncio
async def test_seedance_runtime_sends_prompt_inside_provider_input(monkeypatch):
    install_video_runtime_fixes()
    calls = []

    async def create_task(payload, callback_url=None):
        calls.append((payload, callback_url))
        return {"code": 200, "data": {"taskId": "seedance-task"}}

    async def prepare_images(value):
        return value

    async def prepare_video(value):
        return value

    async def upload_media(value, upload_path):
        return value

    monkeypatch.setattr(video_service.kieai_client, "create_task", create_task)
    monkeypatch.setattr(video_service, "_prepare_video_reference_urls", prepare_images)
    monkeypatch.setattr(video_service, "_prepare_reference_video_url", prepare_video)
    monkeypatch.setattr(video_service, "_upload_local_media", upload_media)

    result = await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "оживи фото",
        image_url="https://example.test/ref.jpg",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
        callback_url="https://example.test/callback",
    )

    assert result.task_id == "seedance-task"
    assert calls[0][0]["model"] == seedance25_adapter.MODEL_KEY
    assert calls[0][0]["input"]["prompt"] == "оживи фото"
    assert calls[0][0]["input"]["first_frame_url"] == "https://example.test/ref.jpg"
    assert calls[0][0]["input"]["aspect_ratio"] == "adaptive"


@pytest.mark.asyncio
async def test_seedance_runtime_multimodal_prompt_is_not_lost(monkeypatch):
    install_video_runtime_fixes()
    calls = []

    async def create_task(payload, callback_url=None):
        calls.append(payload)
        return {"code": 200, "data": {"taskId": "seedance-ref-task"}}

    async def prepare_images(value):
        return value

    monkeypatch.setattr(video_service.kieai_client, "create_task", create_task)
    monkeypatch.setattr(video_service, "_prepare_video_reference_urls", prepare_images)

    await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "камера медленно приближается",
        image_url=["https://example.test/a.jpg", "https://example.test/b.jpg"],
        duration=8,
        aspect_ratio="9:16",
        resolution="720p",
    )

    provider_input = calls[0]["input"]
    assert provider_input["prompt"] == "камера медленно приближается"
    assert provider_input["reference_image_urls"] == [
        "https://example.test/a.jpg",
        "https://example.test/b.jpg",
    ]
    assert "first_frame_url" not in provider_input
    assert "last_frame_url" not in provider_input


def test_veo_public_caps_remove_fake_controls_and_enable_image_input():
    assert VEO_PUBLIC_CAPS["veo3"]["modes"] == ["text", "image"]
    assert VEO_PUBLIC_CAPS["veo3"]["duration_options"] == [8]
    assert VEO_PUBLIC_CAPS["veo3"]["has_resolution"] is False
    assert VEO_PUBLIC_CAPS["veo3_fast"]["max_refs"] == 3
    assert VEO_PUBLIC_CAPS["veo3_lite"]["max_refs"] == 3


@pytest.mark.asyncio
async def test_veo_reference_request_uses_documented_kie_fields_only(monkeypatch):
    install_video_runtime_fixes()
    calls = []

    async def create_veo_task(payload):
        calls.append(payload)
        return {"code": 200, "data": {"taskId": "veo-task"}}

    async def prepare_images(value):
        return value

    monkeypatch.setattr(video_service.kieai_client, "create_veo_task", create_veo_task)
    monkeypatch.setattr(video_service, "_prepare_video_reference_urls", prepare_images)

    result = await video_service.generate_video(
        video_service.VideoModel.VEO_3_FAST,
        "consistent product video",
        image_url=[
            "https://example.test/a.jpg",
            "https://example.test/b.jpg",
            "https://example.test/c.jpg",
        ],
        duration=8,
        aspect_ratio="9:16",
        resolution="1080p",
    )

    assert result.task_id == "veo-task"
    payload = calls[0]
    assert payload["generationType"] == "REFERENCE_2_VIDEO"
    assert payload["imageUrls"] == [
        "https://example.test/a.jpg",
        "https://example.test/b.jpg",
        "https://example.test/c.jpg",
    ]
    assert payload["aspect_ratio"] == "9:16"
    assert "duration" not in payload
    assert "resolution" not in payload
