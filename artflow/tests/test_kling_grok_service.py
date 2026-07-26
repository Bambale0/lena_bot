from __future__ import annotations

import pytest

from api import kling_grok_service as service
from api.kling_grok_service import KlingElement, KlingElementKind, KlingShot


@pytest.mark.asyncio
async def test_kling_26_text_exact_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "k26_text"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_kling_26_text_to_video(
        "A city at night",
        sound=False,
        aspect_ratio="9:16",
        duration=10,
    )

    assert sent == [
        {
            "model": "kling-2.6/text-to-video",
            "input": {
                "prompt": "A city at night",
                "sound": False,
                "aspect_ratio": "9:16",
                "duration": "10",
            },
        }
    ]


@pytest.mark.asyncio
async def test_kling_26_image_exact_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "k26_image"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_kling_26_image_to_video(
        "Transition",
        image_urls=[
            "https://example.test/first.png",
            "https://example.test/last.png",
        ],
        duration=5,
    )

    assert sent[0]["input"]["image_urls"] == [
        "https://example.test/first.png",
        "https://example.test/last.png",
    ]
    assert sent[0]["input"]["duration"] == "5"


@pytest.mark.asyncio
async def test_kling_30_single_shot_with_image_element(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "k30_single"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_kling_30_video(
        "A dog runs through the studio @element_dog",
        image_urls=["https://example.test/first.png"],
        duration=5,
        mode="pro",
        elements=[
            KlingElement(
                name="element_dog",
                description="dog",
                kind=KlingElementKind.IMAGE,
                media_urls=(
                    "https://example.test/dog1.png",
                    "https://example.test/dog2.png",
                ),
            )
        ],
    )

    assert sent == [
        {
            "model": "kling-3.0/video",
            "input": {
                "prompt": "A dog runs through the studio @element_dog",
                "image_urls": ["https://example.test/first.png"],
                "sound": True,
                "duration": "5",
                "aspect_ratio": "16:9",
                "mode": "pro",
                "multi_shots": False,
                "kling_elements": [
                    {
                        "name": "element_dog",
                        "description": "dog",
                        "element_input_urls": [
                            "https://example.test/dog1.png",
                            "https://example.test/dog2.png",
                        ],
                    }
                ],
            },
        }
    ]


@pytest.mark.asyncio
async def test_kling_30_multi_shot_with_video_audio_element(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "k30_multi"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_kling_30_video(
        duration=6,
        mode="4K",
        shots=[
            KlingShot("The person walks @element_actor", 3),
            KlingShot("The person turns @element_actor", 3),
        ],
        elements=[
            KlingElement(
                name="element_actor",
                description="actor",
                kind=KlingElementKind.VIDEO,
                media_urls=("https://example.test/actor.mov",),
                audio_urls=("https://example.test/voice.mp3",),
                start_time_ms=0,
                end_time_ms=6000,
            )
        ],
    )

    payload = sent[0]["input"]
    assert payload["multi_shots"] is True
    assert payload["duration"] == "6"
    assert payload["mode"] == "4K"
    assert payload["multi_prompt"] == [
        {"prompt": "The person walks @element_actor", "duration": 3},
        {"prompt": "The person turns @element_actor", "duration": 3},
    ]
    assert payload["kling_elements"] == [
        {
            "name": "element_actor",
            "description": "actor",
            "element_input_urls": ["https://example.test/actor.mov"],
            "element_input_audio_urls": ["https://example.test/voice.mp3"],
            "start_time": 0,
            "end_time": 6000,
        }
    ]


@pytest.mark.asyncio
async def test_kling_multi_shot_requires_total_duration_match(monkeypatch) -> None:
    async def forbidden_create(payload: dict, callback_url: str | None = None) -> dict:
        raise AssertionError("invalid payload must not reach provider")

    monkeypatch.setattr(service.kieai_client, "create_task", forbidden_create)

    with pytest.raises(ValueError, match="must equal total duration"):
        await service.create_kling_30_video(
            duration=5,
            shots=[KlingShot("one", 3), KlingShot("two", 3)],
        )


@pytest.mark.asyncio
async def test_kling_rejects_undefined_element_reference(monkeypatch) -> None:
    async def forbidden_create(payload: dict, callback_url: str | None = None) -> dict:
        raise AssertionError("invalid payload must not reach provider")

    monkeypatch.setattr(service.kieai_client, "create_task", forbidden_create)

    with pytest.raises(ValueError, match="undefined Kling elements"):
        await service.create_kling_30_video(
            "A dog runs @element_missing",
            duration=5,
        )


@pytest.mark.asyncio
async def test_kling_26_motion_exact_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "motion26"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_kling_motion_control(
        "The character dances",
        image_url="https://example.test/person.png",
        video_url="https://example.test/motion.mkv",
        version="2.6",
        mode="1080p",
        character_orientation="video",
    )

    assert sent[0] == {
        "model": "kling-2.6/motion-control",
        "input": {
            "prompt": "The character dances",
            "input_urls": ["https://example.test/person.png"],
            "video_urls": ["https://example.test/motion.mkv"],
            "mode": "1080p",
            "character_orientation": "video",
        },
    }


@pytest.mark.asyncio
async def test_kling_30_motion_exact_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "motion30"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_kling_motion_control(
        "The character dances",
        image_url="https://example.test/person.png",
        video_url="https://example.test/motion.mov",
        version="3.0",
        mode="720p",
        background_source="input_image",
    )

    assert sent[0]["model"] == "kling-3.0/motion-control"
    assert sent[0]["input"]["background_source"] == "input_image"


@pytest.mark.asyncio
async def test_kling_v3_turbo_operations(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": f"turbo_{len(sent)}"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_kling_v3_turbo_text(
        "Dialogue scene",
        duration=15,
        aspect_ratio="1:1",
        resolution="1080p",
    )
    await service.create_kling_v3_turbo_image(
        "Animate",
        image_urls=["https://example.test/frame.png"],
        duration=8,
        resolution="720p",
    )

    assert sent[0]["model"] == "kling/v3-turbo-text-to-video"
    assert sent[0]["input"]["duration"] == "15"
    assert sent[1]["model"] == "kling/v3-turbo-image-to-video"
    assert sent[1]["input"]["image_urls"] == ["https://example.test/frame.png"]


@pytest.mark.asyncio
async def test_grok_upscale_exact_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "upscaled"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_grok_upscale("task_grok_123")

    assert sent == [
        {
            "model": "grok-imagine/upscale",
            "input": {"task_id": "task_grok_123"},
        }
    ]


@pytest.mark.asyncio
async def test_grok_extend_exact_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "extended"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_grok_extend(
        "task_grok_123",
        prompt="Continue the camera movement",
        extend_at=2,
        extend_times=6,
    )

    assert sent[0] == {
        "model": "grok-imagine/extend",
        "input": {
            "task_id": "task_grok_123",
            "prompt": "Continue the camera movement",
            "extend_at": 2,
            "extend_times": "6",
        },
    }


@pytest.mark.asyncio
async def test_grok_preview_15_exact_payload(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        sent.append(payload)
        return {"code": 200, "data": {"taskId": "preview"}}

    monkeypatch.setattr(service.kieai_client, "create_task", fake_create)

    await service.create_grok_preview_15(
        "A dramatic reveal",
        image_urls=["https://example.test/ref.png"],
        aspect_ratio="16:9",
        resolution="720p",
        duration=8,
    )

    assert sent[0] == {
        "model": "grok-imagine-video-1-5-preview",
        "input": {
            "prompt": "A dramatic reveal",
            "image_urls": ["https://example.test/ref.png"],
            "aspect_ratio": "16:9",
            "resolution": "720p",
            "duration": 8,
        },
    }
