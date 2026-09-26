from __future__ import annotations

import importlib
from unittest.mock import AsyncMock

import pytest


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_higgsfield_seedance25_edit_payload_exposes_published_controls() -> None:
    from api.higgsfield_seedance25_edit import build_video_edit_payload

    payload = build_video_edit_payload(
        prompt="Replace the main character with @Image1 and preserve the source motion",
        video_url="https://cdn.example/source.mp4",
        image_urls=[
            "https://cdn.example/front.jpg",
            "https://cdn.example/three-quarter.jpg",
        ],
        video_urls=["https://cdn.example/motion-ref.mp4"],
        audio_urls=["https://cdn.example/voice.wav"],
        resolution="720p",
        bitrate_mode="high",
        generate_audio=False,
    )

    assert payload == {
        "prompt": "Replace the main character with @Image1 and preserve the source motion",
        "video_url": "https://cdn.example/source.mp4",
        "image_urls": [
            "https://cdn.example/front.jpg",
            "https://cdn.example/three-quarter.jpg",
        ],
        "video_urls": ["https://cdn.example/motion-ref.mp4"],
        "audio_urls": ["https://cdn.example/voice.wav"],
        "resolution": "720p",
        "bitrate_mode": "high",
        "generate_audio": False,
    }


def test_higgsfield_seedance25_edit_payload_validates_provider_limits() -> None:
    from api.higgsfield_seedance25_edit import build_video_edit_payload

    with pytest.raises(ValueError, match="source video"):
        build_video_edit_payload(prompt="edit", video_url="")

    with pytest.raises(ValueError, match="30 image"):
        build_video_edit_payload(
            prompt="edit",
            video_url="https://cdn.example/source.mp4",
            image_urls=[f"https://cdn.example/{i}.jpg" for i in range(31)],
        )

    with pytest.raises(ValueError, match="10 video"):
        build_video_edit_payload(
            prompt="edit",
            video_url="https://cdn.example/source.mp4",
            video_urls=[f"https://cdn.example/{i}.mp4" for i in range(11)],
        )

    with pytest.raises(ValueError, match="10 audio"):
        build_video_edit_payload(
            prompt="edit",
            video_url="https://cdn.example/source.mp4",
            audio_urls=[f"https://cdn.example/{i}.wav" for i in range(11)],
        )

    with pytest.raises(ValueError, match="resolution"):
        build_video_edit_payload(
            prompt="edit",
            video_url="https://cdn.example/source.mp4",
            resolution="1080p",
        )

    with pytest.raises(ValueError, match="bitrate"):
        build_video_edit_payload(
            prompt="edit",
            video_url="https://cdn.example/source.mp4",
            bitrate_mode="turbo",
        )


@pytest.mark.asyncio
async def test_higgsfield_seedance25_edit_submits_exact_endpoint(monkeypatch) -> None:
    from api import higgsfield_seedance25_edit as edit

    submit = AsyncMock(return_value="hf-seedance-task")
    monkeypatch.setattr(edit.higgsfield_client, "submit", submit)

    task_id = await edit.create_video_edit_task(
        prompt="Replace the person with @Image1",
        video_url="https://cdn.example/source.mp4",
        image_urls=["https://cdn.example/person.jpg"],
        resolution="720p",
    )

    assert task_id == "hf-seedance-task"
    submit.assert_awaited_once_with(
        edit.ENDPOINT,
        {
            "prompt": "Replace the person with @Image1",
            "video_url": "https://cdn.example/source.mp4",
            "image_urls": ["https://cdn.example/person.jpg"],
            "resolution": "720p",
            "bitrate_mode": "high",
            "generate_audio": True,
        },
    )



def test_admin_provider_lab_lists_higgsfield_seedance25_video_edit() -> None:
    importlib.import_module("api")
    module = importlib.import_module("bot.handlers.nexus_test")
    markup = module._model_selector_kb()

    assert "nxt:model:hf-seedance25-edit" in _callbacks(markup)
    assert "🧬 Seedance 2.5 · Video Edit" in _labels(markup)


def test_higgsfield_seedance25_lab_is_admin_gated() -> None:
    module = importlib.import_module("bot.handlers.higgsfield_seedance25_test")

    assert module.router.name == "higgsfield_seedance25_edit_test"
