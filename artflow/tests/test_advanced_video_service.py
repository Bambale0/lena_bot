from __future__ import annotations

import pytest

from api import advanced_video_service as service
from api.advanced_video_service import SeedanceModel


@pytest.mark.asyncio
async def test_seedance_text_to_video_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append({"payload": payload, "callback_url": callback_url})
        return {"code": 200, "data": {"taskId": "seedance_text"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    result = await service.create_seedance_task(
        SeedanceModel.QUALITY,
        "A beach at sunset",
        resolution="1080p",
        aspect_ratio="16:9",
        duration=15,
        generate_audio=True,
        return_last_frame=True,
        web_search=True,
        callback_url="https://example.test/callback",
    )

    assert result.task_id == "seedance_text"
    assert sent == [
        {
            "payload": {
                "model": "bytedance/seedance-2",
                "input": {
                    "prompt": "A beach at sunset",
                    "return_last_frame": True,
                    "generate_audio": True,
                    "resolution": "1080p",
                    "aspect_ratio": "16:9",
                    "duration": 15,
                    "web_search": True,
                },
            },
            "callback_url": "https://example.test/callback",
        }
    ]


@pytest.mark.asyncio
async def test_seedance_first_and_last_frame_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "seedance_frames"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_seedance_task(
        SeedanceModel.FAST,
        "Transition between frames",
        first_frame_url="https://example.test/first.png",
        last_frame_url="https://example.test/last.png",
        resolution="720p",
        duration=5,
    )

    assert sent[0]["input"]["first_frame_url"] == "https://example.test/first.png"
    assert sent[0]["input"]["last_frame_url"] == "https://example.test/last.png"
    assert "reference_image_urls" not in sent[0]["input"]


@pytest.mark.asyncio
async def test_seedance_multimodal_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "seedance_multi"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_seedance_task(
        SeedanceModel.MINI,
        "Use image one, video one and this audio",
        reference_image_urls=["https://example.test/ref.png"],
        reference_video_urls=["https://example.test/ref.mp4"],
        reference_audio_urls=["https://example.test/ref.mp3"],
        resolution="720p",
        duration=10,
    )

    assert sent[0]["input"]["reference_image_urls"] == ["https://example.test/ref.png"]
    assert sent[0]["input"]["reference_video_urls"] == ["https://example.test/ref.mp4"]
    assert sent[0]["input"]["reference_audio_urls"] == ["https://example.test/ref.mp3"]


@pytest.mark.asyncio
async def test_seedance_rejects_frames_mixed_with_multimodal_refs(monkeypatch) -> None:
    async def forbidden_create(payload: dict, callback_url: str | None = None) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(service.kieai_client, "create_task", forbidden_create)

    with pytest.raises(ValueError, match="mutually exclusive"):
        await service.create_seedance_task(
            SeedanceModel.QUALITY,
            "Invalid mixed request",
            first_frame_url="https://example.test/first.png",
            reference_video_urls=["https://example.test/ref.mp4"],
        )


@pytest.mark.asyncio
async def test_wan_text_to_video_supports_audio(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "wan_text"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_wan_text_to_video(
        "Neon city",
        negative_prompt="flicker",
        audio_url="https://example.test/music.mp3",
        seed=123,
    )

    assert sent[0] == {
        "model": "wan/2-7-text-to-video",
        "input": {
            "prompt": "Neon city",
            "negative_prompt": "flicker",
            "audio_url": "https://example.test/music.mp3",
            "resolution": "1080p",
            "ratio": "16:9",
            "duration": 5,
            "prompt_extend": True,
            "watermark": False,
            "seed": 123,
        },
    }


@pytest.mark.asyncio
async def test_wan_continuation_is_exclusive(monkeypatch) -> None:
    async def forbidden_create(payload: dict, callback_url: str | None = None) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(service.kieai_client, "create_task", forbidden_create)

    with pytest.raises(ValueError, match="cannot be mixed"):
        await service.create_wan_image_to_video(
            "Continue",
            first_clip_url="https://example.test/clip.mp4",
            first_frame_url="https://example.test/frame.png",
        )


@pytest.mark.asyncio
async def test_wan_reference_to_video_exact_fields(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "wan_r2v"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_wan_reference_to_video(
        "Image 1 eats while video 1 sings",
        reference_image_urls=["https://example.test/ref1.png"],
        reference_video_urls=["https://example.test/ref1.mp4"],
        first_frame_url="https://example.test/first.png",
        reference_voice_url="https://example.test/voice.mp3",
        seed=77,
    )

    assert sent[0]["model"] == "wan/2-7-r2v"
    assert sent[0]["input"]["reference_image"] == ["https://example.test/ref1.png"]
    assert sent[0]["input"]["reference_video"] == ["https://example.test/ref1.mp4"]
    assert sent[0]["input"]["first_frame"] == "https://example.test/first.png"
    assert sent[0]["input"]["reference_voice"] == "https://example.test/voice.mp3"


@pytest.mark.asyncio
async def test_wan_video_edit_exact_fields(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "wan_edit"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_wan_video_edit(
        "Change the outfit",
        video_url="https://example.test/source.mp4",
        reference_image_url="https://example.test/outfit.png",
        audio_setting="keep",
    )

    assert sent[0]["model"] == "wan/2-7-videoedit"
    assert sent[0]["input"]["video_url"] == "https://example.test/source.mp4"
    assert sent[0]["input"]["reference_image"] == "https://example.test/outfit.png"
    assert sent[0]["input"]["audio_setting"] == "keep"


@pytest.mark.asyncio
async def test_happyhorse_v11_and_reference_models(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": f"task_{len(sent)}"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_happyhorse_text_to_video(
        "A dog running",
        version_11=True,
    )
    await service.create_happyhorse_image_to_video(
        "A cat running",
        image_urls=["https://example.test/cat.png"],
        version_11=True,
    )
    await service.create_happyhorse_reference_to_video(
        "character1 walks through the city",
        reference_image_urls=["https://example.test/character.png"],
        version_11=False,
    )

    assert sent[0]["model"] == "happyhorse-1-1/text-to-video"
    assert sent[1]["model"] == "happyhorse-1-1/image-to-video"
    assert sent[1]["input"]["image_urls"] == ["https://example.test/cat.png"]
    assert sent[2]["model"] == "happyhorse/reference-to-video"
    assert sent[2]["input"]["reference_image"] == ["https://example.test/character.png"]


@pytest.mark.asyncio
async def test_happyhorse_video_edit_uses_reference_image_without_typo(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "hh_edit"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_happyhorse_video_edit(
        "Use the striped sweater",
        video_url="https://example.test/video.mp4",
        reference_image_urls=["https://example.test/sweater.png"],
    )

    assert "reference_image" in sent[0]["input"]
    assert "reference_image " not in sent[0]["input"]
