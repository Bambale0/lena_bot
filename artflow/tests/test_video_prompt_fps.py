"""Qwen OpenAI-compatible video sampling contract; no provider request."""
from __future__ import annotations

import pytest

from api import video_prompt_service


def test_default_sampling_is_explicit_and_sibling_to_video_url():
    item = video_prompt_service._video_prompt_chat_messages("https://example.test/video.mp4")[1]["content"][0]
    assert item == {"type": "video_url", "video_url": {"url": "https://example.test/video.mp4"}, "fps": 2.0}


@pytest.mark.parametrize("fps", [0.1, 1.0, 10.0])
def test_custom_sampling_uses_supported_top_level_field(fps):
    item = video_prompt_service._video_prompt_chat_messages("https://example.test/video.mp4", fps=fps)[1]["content"][0]
    assert item["fps"] == fps
    assert set(item["video_url"]) == {"url"}


@pytest.mark.parametrize("fps", [0, 0.09, 10.01, float("nan"), float("inf")])
def test_invalid_sampling_cannot_reach_provider(fps):
    with pytest.raises(ValueError, match="FPS"):
        video_prompt_service._video_prompt_chat_messages("https://example.test/video.mp4", fps=fps)


@pytest.mark.asyncio
@pytest.mark.parametrize("fps", [0, 0.1, 2.0, 10.01, float("nan")])
async def test_live_kie_video_route_rejects_unverified_sampling_before_paid_request(fps, monkeypatch):
    async def no_provider_request(*args, **kwargs):
        raise AssertionError("paid provider request must not occur")

    monkeypatch.setattr(video_prompt_service, "_post_json", no_provider_request)
    with pytest.raises(ValueError, match="FPS sampling is unavailable"):
        await video_prompt_service.generate_prompt_from_video_url("https://example.test/video.mp4", fps=fps)
