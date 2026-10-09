"""Qwen OpenAI-compatible video sampling contract; no provider request."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api import video_prompt_service
from core.config import Settings


def test_default_sampling_is_explicit_and_sibling_to_video_url(monkeypatch):
    monkeypatch.setattr(video_prompt_service, "settings", SimpleNamespace(COMET_VIDEO_PROMPT_FPS=2.0))
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


@pytest.mark.parametrize("fps", [-1, 0, 10.01])
def test_sampling_configuration_is_validated(fps):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, COMET_VIDEO_PROMPT_FPS=fps)
