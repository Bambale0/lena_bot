from __future__ import annotations

import pytest

from api import video_service
from api.video_service import VideoGenerationType, VideoModel


@pytest.mark.asyncio
async def test_video_failure_never_calls_cross_model_fallback(monkeypatch) -> None:
    comet_called = False

    async def fail_kie(payload: dict, callback_url: str | None = None) -> dict:
        raise RuntimeError("provider unavailable")

    async def forbidden_comet(**_kwargs):
        nonlocal comet_called
        comet_called = True
        raise AssertionError("cross-model fallback must not run")

    monkeypatch.setattr(video_service.kieai_client, "create_task", fail_kie)
    monkeypatch.setattr(video_service.comet_fallback, "generate_video", forbidden_comet)

    with pytest.raises(RuntimeError, match="cross-model fallback is disabled"):
        await video_service.generate_video(
            VideoModel.SEEDANCE_2,
            "A cinematic scene",
            duration=5,
            aspect_ratio="16:9",
            resolution="720p",
        )

    assert comet_called is False


@pytest.mark.asyncio
async def test_grok_i2v_requires_source_task_id_before_provider_call(monkeypatch) -> None:
    provider_called = False

    async def forbidden_create_task(payload: dict, callback_url: str | None = None) -> dict:
        nonlocal provider_called
        provider_called = True
        raise AssertionError("provider must not be called without source_task_id")

    monkeypatch.setattr(video_service.kieai_client, "create_task", forbidden_create_task)

    with pytest.raises(RuntimeError, match="requires source_task_id"):
        await video_service.generate_video(
            VideoModel.GROK_I2V,
            "Animate the subject",
            image_url="https://cdn.example.test/source.png",
            duration=6,
            aspect_ratio="16:9",
            resolution="480p",
        )

    assert provider_called is False


@pytest.mark.asyncio
async def test_grok_i2v_sends_official_task_id_and_image_urls(monkeypatch) -> None:
    created: list[dict] = []

    async def fake_create_task(payload: dict, callback_url: str | None = None) -> dict:
        created.append(payload)
        return {"code": 200, "data": {"taskId": "grok_video_task"}}

    monkeypatch.setattr(video_service.kieai_client, "create_task", fake_create_task)

    result = await video_service.generate_video(
        VideoModel.GROK_I2V,
        "Animate the subject",
        image_url="https://cdn.example.test/source.png",
        duration=6,
        aspect_ratio="16:9",
        resolution="480p",
        source_task_id="task_grok_source_123",
    )

    assert result.task_id == "grok_video_task"
    assert created == [
        {
            "model": "grok-imagine/image-to-video",
            "input": {
                "prompt": "Animate the subject",
                "mode": "normal",
                "duration": "6",
                "resolution": "480p",
                "nsfw_checker": False,
                "image_urls": ["https://cdn.example.test/source.png"],
                "image_url": "https://cdn.example.test/source.png",
                "task_id": "task_grok_source_123",
                "aspect_ratio": "16:9",
            },
        }
    ]


@pytest.mark.asyncio
async def test_gemini_character_uses_singular_description_field(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create_character(payload: dict) -> dict:
        sent.append(payload)
        return {
            "code": 200,
            "data": {
                "characterId": "character_123",
                "characterName": "Jenny",
                "imageUrl": "https://cdn.example.test/jenny.png",
            },
        }

    monkeypatch.setattr(video_service.kieai_client, "create_omni_character", fake_create_character)

    result = await video_service.create_gemini_omni_character(
        descriptions="A cyberpunk courier",
        image_urls="https://cdn.example.test/reference.png",
        character_name="Jenny",
    )

    assert result.character_id == "character_123"
    assert sent == [
        {
            "description": "A cyberpunk courier",
            "image_urls": ["https://cdn.example.test/reference.png"],
            "character_name": "Jenny",
        }
    ]


@pytest.mark.asyncio
async def test_veo_text_mode_uses_official_generation_type(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create_veo(payload: dict) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "veo_text_task"}}

    monkeypatch.setattr(video_service.kieai_client, "create_veo_task", fake_create_veo)

    result = await video_service._veo_generate(
        VideoModel.VEO_3,
        "A dog playing in a park",
        None,
        "16:9",
        resolution="1080p",
    )

    assert result.task_id == "veo_text_task"
    assert sent == [
        {
            "prompt": "A dog playing in a park",
            "model": "veo3",
            "aspect_ratio": "16:9",
            "enableTranslation": False,
            "enableFallback": False,
            "generationType": "TEXT_2_VIDEO",
        }
    ]


@pytest.mark.asyncio
async def test_veo_first_and_last_frame_mode(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create_veo(payload: dict) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "veo_frames_task"}}

    monkeypatch.setattr(video_service.kieai_client, "create_veo_task", fake_create_veo)

    await video_service._veo_generate(
        VideoModel.VEO_3,
        "Create a smooth transition",
        "https://cdn.example.test/first.png",
        "9:16",
        last_frame_url="https://cdn.example.test/last.png",
        generation_type=VideoGenerationType.FIRST_LAST,
    )

    assert sent[0]["generationType"] == "FIRST_AND_LAST_FRAMES_2_VIDEO"
    assert sent[0]["imageUrls"] == [
        "https://cdn.example.test/first.png",
        "https://cdn.example.test/last.png",
    ]


@pytest.mark.asyncio
async def test_veo_material_mode_is_rejected_for_quality_model(monkeypatch) -> None:
    async def forbidden_create_veo(payload: dict) -> dict:
        raise AssertionError("invalid request must fail before provider call")

    monkeypatch.setattr(video_service.kieai_client, "create_veo_task", forbidden_create_veo)

    with pytest.raises(ValueError, match="only by Fast and Lite"):
        await video_service._veo_generate(
            VideoModel.VEO_3,
            "Use the materials",
            ["https://cdn.example.test/a.png"],
            "16:9",
            generation_type=VideoGenerationType.REFERENCE,
        )


@pytest.mark.asyncio
async def test_veo_material_mode_accepts_fast_model(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create_veo(payload: dict) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "veo_reference_task"}}

    monkeypatch.setattr(video_service.kieai_client, "create_veo_task", fake_create_veo)

    await video_service._veo_generate(
        VideoModel.VEO_3_FAST,
        "Use the materials",
        [
            "https://cdn.example.test/a.png",
            "https://cdn.example.test/b.png",
            "https://cdn.example.test/c.png",
        ],
        "16:9",
        generation_type=VideoGenerationType.REFERENCE,
        watermark="APIX",
        enable_translation=True,
    )

    assert sent[0]["generationType"] == "REFERENCE_2_VIDEO"
    assert sent[0]["watermark"] == "APIX"
    assert sent[0]["enableTranslation"] is True


@pytest.mark.asyncio
async def test_veo_4k_uses_current_official_endpoint(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 200, "data": {"taskId": "veo_4k_task"}}

    monkeypatch.setattr(video_service.kieai_client, "post", fake_post)

    result = await video_service.generate_video_4k(
        "veo_source_task",
        index=1,
        callback_url="https://example.test/callback",
    )

    assert result.task_id == "veo_4k_task"
    assert calls == [
        (
            "/api/v1/veo/get-4k-video",
            {
                "taskId": "veo_source_task",
                "index": 1,
                "callBackUrl": "https://example.test/callback",
            },
        )
    ]


@pytest.mark.asyncio
async def test_veo_1080_uses_current_official_endpoint(monkeypatch) -> None:
    paths: list[str] = []

    async def fake_get(path: str) -> dict:
        paths.append(path)
        return {"code": 200, "data": {"resultUrl": "https://cdn.example.test/1080.mp4"}}

    monkeypatch.setattr(video_service.kieai_client, "get", fake_get)

    url = await video_service.get_veo_1080p_url("veo_source_task", index=0)

    assert url == "https://cdn.example.test/1080.mp4"
    assert paths == ["/api/v1/veo/get-1080p-video?taskId=veo_source_task&index=0"]
