from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import seedance25_adapter as s25


@pytest.mark.asyncio
async def test_seedance25_generate_payload_keeps_prompt() -> None:
    captured: dict = {}

    async def create_task(payload, callback_url=None):
        captured["payload"] = payload
        captured["callback_url"] = callback_url
        return {"code": 200, "data": {"taskId": "seedance-task"}}

    async def prepare_images(value):
        if not value:
            return []
        return [value] if isinstance(value, str) else list(value)

    async def prepare_video(value):
        return value

    async def upload_media(value, *, upload_path):
        return value

    async def original_generate(*args, **kwargs):
        raise AssertionError("Seedance 2.5 must use its provider wrapper")

    class VideoModel:
        _value2member_map_ = {}
        _member_names_: list[str] = []
        _member_map_: dict[str, object] = {}

        def __new__(cls, value):
            member = cls._value2member_map_.get(value)
            if member is None:
                raise ValueError(value)
            return member

    video_service = SimpleNamespace(
        VideoModel=VideoModel,
        generate_video=original_generate,
        _prepare_video_reference_urls=prepare_images,
        _prepare_reference_video_url=prepare_video,
        _upload_local_media=upload_media,
        kieai_client=SimpleNamespace(create_task=create_task),
        VideoResult=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    s25._install_enum_value(VideoModel, "SEEDANCE_25", s25.MODEL_KEY)
    s25._install_seedance25_generate_wrapper(video_service)

    prompt = "A red dress moving in a soft studio breeze"
    await video_service.generate_video(
        VideoModel(s25.MODEL_KEY),
        prompt,
        duration=5,
        aspect_ratio="9:16",
        resolution="720p",
    )

    assert captured["payload"]["model"] == s25.MODEL_KEY
    assert captured["payload"]["input"]["prompt"] == prompt
