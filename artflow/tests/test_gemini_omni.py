from __future__ import annotations

import pytest
from fastapi import HTTPException

from api import video_service
from api.miniapp_routes import _normalize_video_request
from core.gemini_omni import (
    build_gemini_omni_audio_payload,
    build_gemini_omni_character_payload,
    gemini_omni_video_credits,
)


def test_gemini_omni_video_credits_use_stable_720p_tier() -> None:
    assert gemini_omni_video_credits(duration=4, resolution="720p") == 90
    assert gemini_omni_video_credits(duration=10, resolution="4K") == 180
    assert gemini_omni_video_credits(duration=4, resolution="4k", has_video_input=True) == 240


def test_gemini_omni_auxiliary_payloads() -> None:
    audio_payload = build_gemini_omni_audio_payload(
        audio_id="achernar",
        name="Narrator",
        voice_description="calm",
        example_dialogue="Hello",
    )
    assert audio_payload == {
        "audio_id": "achernar",
        "name": "Narrator",
        "voice_description": "calm",
        "example_dialogue": "Hello",
    }

    character_payload = build_gemini_omni_character_payload(
        descriptions="silver-haired pilot",
        image_urls="https://example.test/hero.png",
        audio_ids=["audio_1"],
        character_name="Lena",
    )
    assert character_payload["descriptions"] == "silver-haired pilot"
    assert character_payload["image_urls"] == ["https://example.test/hero.png"]
    assert character_payload["audio_ids"] == ["audio_1"]
    assert character_payload["character_name"] == "Lena"


def test_gemini_omni_character_payload_allows_one_audio_id() -> None:
    with pytest.raises(ValueError, match="audio_ids supports at most 1"):
        build_gemini_omni_character_payload(
            descriptions="silver-haired pilot",
            image_urls="https://example.test/hero.png",
            audio_ids=["audio_1", "audio_2"],
        )


@pytest.mark.asyncio
async def test_gemini_omni_audio_service_accepts_live_audio_id_response(monkeypatch) -> None:
    async def fake_create_omni_audio(payload: dict) -> dict:
        return {"code": 200, "msg": "success", "data": {"audioId": "audio_live", "name": payload["name"]}}

    monkeypatch.setattr(video_service.kieai_client, "create_omni_audio", fake_create_omni_audio)

    result = await video_service.create_gemini_omni_audio(audio_id="achernar", name="Narrator")

    assert result.audio_id == "audio_live"
    assert result.name == "Narrator"


@pytest.mark.asyncio
async def test_gemini_omni_character_service_accepts_id_alias(monkeypatch) -> None:
    async def fake_create_omni_character(payload: dict) -> dict:
        return {"code": 200, "msg": "success", "data": {"id": "character_live", "characterName": "Hero"}}

    monkeypatch.setattr(video_service.kieai_client, "create_omni_character", fake_create_omni_character)

    result = await video_service.create_gemini_omni_character(
        descriptions="silver-haired pilot",
        image_urls="https://example.test/hero.png",
    )

    assert result.character_id == "character_live"
    assert result.character_name == "Hero"


@pytest.mark.asyncio
async def test_poll_kieai_status_accepts_video_url_result_json(monkeypatch) -> None:
    async def fake_get_task_status(task_id: str) -> dict:
        return {"data": {"state": "success", "resultJson": '{"videoUrl":"https://cdn.test/result.mp4"}'}}

    monkeypatch.setattr(video_service.kieai_client, "get_task_status", fake_get_task_status)

    assert await video_service.poll_kieai_status("task_1") == "https://cdn.test/result.mp4"


def test_miniapp_normalizes_gemini_omni_video_request() -> None:
    normalized = _normalize_video_request(
        model_key="gemini-omni-video",
        mode="video",
        duration=5,
        aspect_ratio=None,
        resolution="4K",
        image_url=None,
        reference_urls=None,
        video_url="https://example.test/source.mp4",
        video_start=2,
        video_end=9,
        audio_ids=["audio_1"],
        character_ids=["character_1"],
        seed=7,
        grok_mode=None,
    )

    assert normalized["duration"] == 4
    assert normalized["resolution"] == "720p"
    assert normalized["reference_video_url"] == "https://example.test/source.mp4"
    assert normalized["video_start"] == 2
    assert normalized["video_end"] == 9
    assert normalized["audio_ids"] == ["audio_1"]
    assert normalized["character_ids"] == ["character_1"]
    assert normalized["seed"] == 7


def test_miniapp_rejects_multiple_gemini_omni_audio_ids() -> None:
    with pytest.raises(HTTPException) as exc:
        _normalize_video_request(
            model_key="gemini-omni-video",
            mode="text",
            duration=4,
            aspect_ratio="16:9",
            resolution="720p",
            image_url=None,
            reference_urls=None,
            audio_ids=["audio_1", "audio_2"],
        )

    assert exc.value.status_code == 422
    assert "audio_ids supports at most 1" in str(exc.value.detail)


def test_miniapp_rejects_gemini_omni_media_quota_overflow() -> None:
    with pytest.raises(HTTPException) as exc:
        _normalize_video_request(
            model_key="gemini-omni-video",
            mode="image",
            duration=4,
            aspect_ratio="16:9",
            resolution="720p",
            image_url="https://example.test/1.png",
            reference_urls=[
                "https://example.test/2.png",
                "https://example.test/3.png",
                "https://example.test/4.png",
                "https://example.test/5.png",
                "https://example.test/6.png",
            ],
            video_url="https://example.test/source.mp4",
            video_start=0,
            video_end=4,
            audio_ids=[],
            character_ids=["character_1", "character_2"],
            seed=None,
            grok_mode=None,
        )

    assert exc.value.status_code == 422
