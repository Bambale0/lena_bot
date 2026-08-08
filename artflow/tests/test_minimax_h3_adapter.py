from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import minimax_h3_adapter as h3
from api import video_service
from api.minimax_h3_pricing import (
    T2V_RESOLUTION_CREDITS,
    credits_per_second,
    minimax_h3_model_cost_rows,
)


def test_minimax_h3_text_payload_matches_kie_contract() -> None:
    assert h3._t2v_input(
        prompt="cinematic city",
        duration=15,
        aspect_ratio="21:9",
        resolution="2K",
    ) == {
        "prompt": "cinematic city",
        "duration": 15,
        "aspect_ratio": "21:9",
        "resolution": "2K",
    }


def test_minimax_h3_image_payload_supports_first_and_last_frame() -> None:
    assert h3._i2v_input(
        prompt="move naturally",
        duration=8,
        images=["https://example.test/first.jpg", "https://example.test/last.jpg"],
    ) == {
        "prompt": "move naturally",
        "duration": 8,
        "first_frame_url": "https://example.test/first.jpg",
        "last_frame_url": "https://example.test/last.jpg",
    }


def test_minimax_h3_reference_payload_supports_all_reference_modalities() -> None:
    assert h3._reference_input(
        prompt="keep the character consistent",
        duration=12,
        aspect_ratio="adaptive",
        images=["https://example.test/character.jpg"],
        videos=["https://example.test/motion.mp4"],
        audios=["https://example.test/voice.wav"],
    ) == {
        "prompt": "keep the character consistent",
        "duration": 12,
        "aspect_ratio": "adaptive",
        "reference_image_urls": ["https://example.test/character.jpg"],
        "reference_video_urls": ["https://example.test/motion.mp4"],
        "reference_audio_urls": ["https://example.test/voice.wav"],
    }


def test_minimax_h3_reference_requires_reference() -> None:
    with pytest.raises(ValueError, match="at least one reference"):
        h3._reference_input(
            prompt="empty",
            duration=6,
            aspect_ratio="adaptive",
            images=[],
            videos=[],
            audios=[],
        )


def test_minimax_h3_caps_expose_all_three_models() -> None:
    assert h3.VIDEO_CAPS[h3.T2V_MODEL]["modes"] == ["text"]
    assert h3.VIDEO_CAPS[h3.I2V_MODEL]["modes"] == ["image"]
    reference = h3.VIDEO_CAPS[h3.REFERENCE_MODEL]
    assert reference["supports_video_input"] is True
    assert reference["supports_audio_references"] is True
    assert reference["max_refs"] == h3.MAX_REFERENCE_IMAGES
    assert reference["max_video_refs"] == h3.MAX_REFERENCE_VIDEOS


def test_minimax_h3_models_are_registered_in_video_enum() -> None:
    assert video_service.VideoModel(h3.T2V_MODEL).value == h3.T2V_MODEL
    assert video_service.VideoModel(h3.I2V_MODEL).value == h3.I2V_MODEL
    assert video_service.VideoModel(h3.REFERENCE_MODEL).value == h3.REFERENCE_MODEL


def test_minimax_h3_pricing_seed_has_three_base_rows_and_t2v_variants() -> None:
    rows = minimax_h3_model_cost_rows()
    keys = {row["model_key"] for row in rows}
    assert h3.T2V_MODEL in keys
    assert h3.I2V_MODEL in keys
    assert h3.REFERENCE_MODEL in keys
    assert len(rows) == 3 + len(T2V_RESOLUTION_CREDITS)
    assert credits_per_second(h3.T2V_MODEL, resolution="768P") == 10
    assert credits_per_second(h3.T2V_MODEL, resolution="2K") == 14


class _FakeHTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _fake_routes():
    def normalize_urls(*urls):
        return [str(url) for url in urls if str(url or "").strip()]

    def original(**kwargs):
        return kwargs

    return SimpleNamespace(
        _normalize_video_request=original,
        _normalize_public_urls=normalize_urls,
        HTTPException=_FakeHTTPException,
        VIDEO_CAPS={},
        _VIDEO_MODEL_ORDER=[],
        _FRIENDLY_MODEL_NAMES={},
    )


def test_minimax_h3_miniapp_normalizes_reference_images_video_and_audio(monkeypatch) -> None:
    routes = _fake_routes()
    monkeypatch.setattr(h3, "install_minimax_h3_provider_support", lambda: None)
    h3.install_minimax_h3_miniapp(routes)

    normalized = routes._normalize_video_request(
        model_key=h3.REFERENCE_MODEL,
        mode="image",
        duration=10,
        aspect_ratio="adaptive",
        resolution=None,
        image_url="https://example.test/a.jpg",
        reference_urls=["https://example.test/b.jpg"],
        video_url="https://example.test/a.mp4",
        audio_ids=["https://example.test/a.wav"],
        character_ids=["https://example.test/b.mp4"],
        video_start=None,
        video_end=None,
        seed=None,
        grok_mode=None,
    )

    assert normalized["image_url"] == [
        "https://example.test/a.jpg",
        "https://example.test/b.jpg",
    ]
    assert normalized["reference_video_url"] == [
        "https://example.test/a.mp4",
        "https://example.test/b.mp4",
    ]
    assert normalized["audio_ids"] == ["https://example.test/a.wav"]
    assert normalized["duration"] == 10
    assert normalized["aspect_ratio"] == "adaptive"


@pytest.mark.asyncio
async def test_minimax_h3_generate_wrapper_calls_exact_kie_reference_model(monkeypatch) -> None:
    calls: list[tuple[dict, str | None]] = []

    async def create_task(payload, callback_url=None):
        calls.append((payload, callback_url))
        return {"code": 200, "data": {"taskId": "h3-task"}}

    async def prepare_images(value):
        return [value] if isinstance(value, str) else list(value or [])

    async def prepare_video(value):
        return value

    async def upload_media(value, upload_path):
        return value

    monkeypatch.setattr(video_service.kieai_client, "create_task", create_task)
    monkeypatch.setattr(video_service, "_prepare_video_reference_urls", prepare_images)
    monkeypatch.setattr(video_service, "_prepare_reference_video_url", prepare_video)
    monkeypatch.setattr(video_service, "_upload_local_media", upload_media)

    result = await video_service.generate_video(
        video_service.VideoModel(h3.REFERENCE_MODEL),
        "reference scene",
        image_url="https://example.test/person.jpg",
        duration=6,
        aspect_ratio="adaptive",
        reference_video_url="https://example.test/motion.mp4",
        audio_ids=["https://example.test/beat.wav"],
        callback_url="https://example.test/callback",
    )

    assert result.task_id == "h3-task"
    assert calls[0][0] == {
        "model": h3.REFERENCE_MODEL,
        "input": {
            "prompt": "reference scene",
            "duration": 6,
            "aspect_ratio": "adaptive",
            "reference_image_urls": ["https://example.test/person.jpg"],
            "reference_video_urls": ["https://example.test/motion.mp4"],
            "reference_audio_urls": ["https://example.test/beat.wav"],
        },
    }
    assert calls[0][1] == "https://example.test/callback"
