from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def test_seedance20_single_image_maps_to_neironych_frame_contract() -> None:
    from api.neironych_seedance_runtime import build_product_payload

    model, payload = build_product_payload(
        product_model="bytedance/seedance-2",
        prompt="animate",
        image_urls=["https://cdn.example.test/start.jpg"],
        duration=5,
        aspect_ratio="9:16",
        resolution="720p",
    )

    assert model == "seedance-2.0"
    assert payload["start_image"] == {"url": "https://cdn.example.test/start.jpg"}
    assert "reference_images" not in payload
    assert payload["duration"] == 5
    assert payload["aspect_ratio"] == "9:16"


def test_seedance25_multimodal_maps_to_reference_contract_and_omits_adaptive() -> None:
    from api.neironych_seedance_runtime import build_product_payload

    model, payload = build_product_payload(
        product_model="bytedance/seedance-2-5",
        prompt="keep the person and use the reference",
        image_urls=["https://cdn.example.test/person.jpg"],
        video_urls=["https://cdn.example.test/motion.mp4"],
        audio_urls=["https://cdn.example.test/voice.mp3"],
        duration=10,
        aspect_ratio="adaptive",
        resolution="720p",
    )

    assert model == "seedance-2.5"
    assert payload["omni_reference_task_type"] == "reference"
    assert payload["reference_images"] == [{"url": "https://cdn.example.test/person.jpg"}]
    assert payload["reference_videos"] == [{"url": "https://cdn.example.test/motion.mp4"}]
    assert payload["reference_audios"] == [{"url": "https://cdn.example.test/voice.mp3"}]
    assert "aspect_ratio" not in payload


def test_seedance25_identity_edit_maps_to_edit_contract() -> None:
    from api.neironych_seedance_runtime import build_product_payload

    model, payload = build_product_payload(
        product_model="bytedance/seedance-2-5",
        prompt="replace the clothes",
        image_urls=["https://cdn.example.test/clothes.jpg"],
        video_urls=["https://cdn.example.test/source.mp4"],
        duration=-1,
        aspect_ratio="adaptive",
        resolution="720p",
        edit=True,
    )

    assert model == "seedance-2.5"
    assert payload["omni_reference_task_type"] == "edit"
    assert payload["reference_videos"] == [{"url": "https://cdn.example.test/source.mp4"}]
    assert payload["duration"] == -1
    assert payload["aspect_ratio"] == "adaptive"


@pytest.mark.asyncio
async def test_seedance20_video_service_uses_neironych_not_kie(monkeypatch) -> None:
    from api import neironych_seedance_runtime, video_service

    submit = AsyncMock(return_value="neur-request-20")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", submit)
    kie_submit = AsyncMock()
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie_submit)

    result = await video_service.generate_video(
        video_service.VideoModel.SEEDANCE_2,
        "move slowly",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
    )

    assert result.task_id == "neur-request-20"
    assert result.provider == "neironych"
    assert result.uses_webhook is False
    submit.assert_awaited_once()
    kie_submit.assert_not_awaited()


def test_neironych_is_registered_as_video_poller() -> None:
    from api import neironych_seedance_runtime, video_service

    assert video_service.get_poll_fn("neironych") is neironych_seedance_runtime.poll_product_video
