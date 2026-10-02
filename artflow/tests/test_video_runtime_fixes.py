from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import neironych_seedance_runtime, seedance25_adapter, video_service
from api.video_runtime_fixes import VEO_PUBLIC_CAPS, install_video_runtime_fixes
from bot.services.veo_ui import install_veo_handler_presentation


@pytest.mark.asyncio
async def test_seedance_runtime_sends_prompt_inside_neironych_request(monkeypatch):
    install_video_runtime_fixes()
    submit = AsyncMock(return_value="seedance-task")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", submit)

    result = await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "оживи фото",
        image_url="https://example.test/ref.jpg",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
        callback_url="https://example.test/callback",
    )

    assert result.task_id == "neironych:seedance-task"
    assert result.provider == "neironych"
    kwargs = submit.await_args.kwargs
    assert kwargs["prompt"] == "оживи фото"
    assert kwargs["image_urls"] == ["https://example.test/ref.jpg"]
    assert kwargs["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_seedance_runtime_forwards_video_references_to_neironych(monkeypatch):
    install_video_runtime_fixes()
    submit = AsyncMock(return_value="seedance-video-ref-task")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", submit)

    result = await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "use the motion from the reference video",
        image_url=["https://example.test/person.jpg"],
        reference_video_url=[
            "https://example.test/motion-a.mp4",
            "https://example.test/motion-b.mov",
        ],
        duration=10,
        aspect_ratio="9:16",
        resolution="720p",
    )

    assert result.task_id == "neironych:seedance-video-ref-task"
    kwargs = submit.await_args.kwargs
    assert kwargs["image_urls"] == ["https://example.test/person.jpg"]
    assert kwargs["video_urls"] == [
        "https://example.test/motion-a.mp4",
        "https://example.test/motion-b.mov",
    ]

@pytest.mark.asyncio
async def test_seedance_edit_billing_uses_reference_video_duration(monkeypatch):
    from api import video_runtime_fixes as runtime

    monkeypatch.setattr(runtime, "local_upload_path_from_url", lambda _url: SimpleNamespace())
    monkeypatch.setattr(
        runtime,
        "probe_local_media",
        AsyncMock(return_value=SimpleNamespace(width=720, height=1280, duration_seconds=28.8)),
    )

    duration = await runtime.seedance25_edit_billing_duration(
        "Замени людей на видео и сохрани движения",
        ["https://example.test/source.mp4"],
    )

    assert duration == 29


@pytest.mark.asyncio
async def test_seedance_edit_billing_rejects_external_url_before_charge(monkeypatch) -> None:
    from api import video_runtime_fixes as runtime

    monkeypatch.setattr(runtime, "local_upload_path_from_url", lambda _url: None)

    with pytest.raises(ValueError, match="загрузи исходный ролик файлом"):
        await runtime.seedance25_edit_billing_duration(
            "Замени человека на видео",
            ["https://external.example/source.mp4"],
        )


@pytest.mark.asyncio
async def test_seedance_edit_billing_rejects_multiple_source_videos() -> None:
    from api import video_runtime_fixes as runtime

    with pytest.raises(ValueError, match="one reference video"):
        await runtime.seedance25_edit_billing_duration(
            "Replace the people in the video",
            ["https://example.test/a.mp4", "https://example.test/b.mp4"],
        )


@pytest.mark.asyncio
async def test_seedance_runtime_normalizes_explicit_video_edit_request(monkeypatch):
    install_video_runtime_fixes()
    submit = AsyncMock(return_value="seedance-edit-task")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", submit)

    await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "Замени людей на видео на людей с загруженных фото и сохрани движения",
        image_url=["https://example.test/a.jpg", "https://example.test/b.jpg"],
        reference_video_url=["https://example.test/source.mp4"],
        duration=30,
        aspect_ratio="9:16",
        resolution="480p",
    )

    kwargs = submit.await_args.kwargs
    assert kwargs["video_urls"] == ["https://example.test/source.mp4"]
    assert kwargs["edit"] is True


@pytest.mark.asyncio
async def test_seedance_runtime_multimodal_prompt_is_not_lost(monkeypatch):
    install_video_runtime_fixes()
    submit = AsyncMock(return_value="seedance-ref-task")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", submit)

    await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "камера медленно приближается",
        image_url=["https://example.test/a.jpg", "https://example.test/b.jpg"],
        duration=8,
        aspect_ratio="9:16",
        resolution="720p",
    )

    kwargs = submit.await_args.kwargs
    assert kwargs["prompt"] == "камера медленно приближается"
    assert kwargs["image_urls"] == [
        "https://example.test/a.jpg",
        "https://example.test/b.jpg",
    ]
    assert kwargs["edit"] is False

def test_veo_public_caps_remove_fake_controls_and_enable_image_input():
    assert VEO_PUBLIC_CAPS["veo3"]["modes"] == ["text", "image"]
    assert VEO_PUBLIC_CAPS["veo3"]["duration_options"] == [8]
    assert VEO_PUBLIC_CAPS["veo3"]["has_resolution"] is False
    assert VEO_PUBLIC_CAPS["veo3_fast"]["max_refs"] == 3
    assert VEO_PUBLIC_CAPS["veo3_lite"]["max_refs"] == 3


def test_veo_telegram_defaults_are_not_legacy_five_seconds():
    fake = SimpleNamespace(
        _DEFAULT_DURATION={"veo3": 5, "veo3_fast": 5, "veo3_lite": 5},
        _DEFAULT_RES={"veo3": "720p", "veo3_fast": "720p", "veo3_lite": "720p"},
    )
    install_veo_handler_presentation(fake)
    assert fake._DEFAULT_DURATION == {"veo3": 8, "veo3_fast": 8, "veo3_lite": 8}
    assert fake._DEFAULT_RES == {}


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
