"""Wan repeats must preserve original paid operation semantics and media slots."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import wan30_launch
from api.wan30_contract import Wan30Request
from bot.handlers import video_gen

IMAGE1 = "https://example.test/face1.png"
IMAGE2 = "https://example.test/face2.png"
VIDEO1 = "https://example.test/camera.mp4"
VIDEO2 = "https://example.test/dance.mp4"
AUDIO1 = "https://example.test/voice.wav"
FILE1 = "https://example.test/script.pdf"
LINK1 = "https://example.test/materials"
FIRST = "https://example.test/first.png"
LAST = "https://example.test/last.png"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,media", [
    ("reference", {"reference_image_urls": (IMAGE1, IMAGE2)}),
    ("reference", {"reference_image_urls": (IMAGE1,)}),
    ("reference", {"reference_video_urls": (VIDEO1,),
                   "reference_video_durations": (5.0,)}),
    ("reference", {"reference_image_urls": (IMAGE1,),
                   "reference_video_urls": (VIDEO1,),
                   "reference_video_durations": (5.0,)}),
    ("reference", {"reference_audio_urls": (AUDIO1,),
                   "reference_audio_durations": (4.0,)}),
    ("edit", {"reference_video_urls": (VIDEO1, VIDEO2),
              "reference_video_durations": (4.0, 5.0),
              "reference_image_urls": (IMAGE1,)}),
    ("first", {"first_frame_url": FIRST}),
    ("first_last", {"first_frame_url": FIRST, "last_frame_url": LAST}),
    ("file", {"reference_file_urls": (FILE1,)}),
    ("link", {"reference_link_urls": (LINK1,)}),
])
async def test_restored_wan_request_round_trips_mode_and_reference_roles(monkeypatch, mode, media):
    req = Wan30Request(
        model="wan/3-0-video", prompt="Recreate original with tiny changes",
        mode=mode, duration=5, resolution="720p", aspect_ratio="adaptive",
        audio=False, nsfw_checker=True, seed=17,
        **media,
    )
    # Real source of truth: the validated Wan checkout was persisted in history.
    from api.wan30_launch import Wan30Quote
    prev = SimpleNamespace(
        model=req.model, task_id="kie-previous", parent_generation_id=None,
        input_params=json.dumps(Wan30Quote(
            request=req, billable_seconds=12, rate=12, credits=144,
            resolution="720p",
        ).stored_params()),
    )
    monkeypatch.setattr(
        video_gen.video_service.kieai_client, "get_task_status",
        AsyncMock(side_effect=AssertionError("Do not fetch provider for repeat")),
    )
    params = await video_gen._video_repeat_params_for_generation(AsyncMock(), prev)
    state = video_gen._video_state_from_repeat_params(req.model, params)
    assert state["wan_source_mode"] == mode
    assert video_gen._video_state_has_required_input(state)

    async def measured(url, kind):
        return 5.0 if str(url) in (VIDEO1, VIDEO2) else 4.0
    monkeypatch.setattr(wan30_launch, "_duration_for_owned_media", measured)
    restored = await wan30_launch.create_wan30_request(
        model=req.model, prompt=req.prompt,
        mode=state["mode"], image_urls=state["image_url"],
        video_url=state["reference_video_url"],
        duration=state["duration"], resolution=state["resolution"],
        aspect_ratio=state["aspect_ratio"],
        options={
            "audio": state["wan_audio"], "nsfw_checker": state["wan_nsfw_checker"],
            "seed": state["seed"],
            "reference_image_urls": state["wan_reference_image_urls"],
            "reference_video_urls": state["wan_reference_video_urls"],
            "reference_audio_urls": state["wan_reference_audio_urls"],
            "reference_file_urls": state["wan_reference_file_urls"],
            "reference_link_urls": state["wan_reference_link_urls"],
            "first_frame_url": state["wan_first_frame_url"],
            "last_frame_url": state["wan_last_frame_url"],
        },
    )
    assert restored.mode == mode
    for field in (
        "first_frame_url", "last_frame_url",
        "reference_image_urls", "reference_video_urls",
        "reference_audio_urls", "reference_file_urls", "reference_link_urls",
        "duration", "resolution", "aspect_ratio", "audio", "nsfw_checker", "seed",
    ):
        assert getattr(restored, field) == getattr(req, field), field
