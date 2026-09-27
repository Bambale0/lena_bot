from __future__ import annotations

from pathlib import Path

import pytest


def test_seedance_repeat_edit_prompt_applies_number_and_outfit_as_priority_overrides() -> None:
    from core.seedance_repeat_edit import build_seedance_repeat_edit_prompt

    prompt = build_seedance_repeat_edit_prompt(
        "Keep the source scene and motion.",
        number_value="25",
        outfit_value="чёрная кожаная куртка",
    )

    assert prompt.startswith("Keep the source scene and motion.")
    assert "25" in prompt
    assert "чёрная кожаная куртка" in prompt
    assert "Replace" in prompt
    assert "priority" in prompt.lower()
    assert "Preserve all other" in prompt


def test_seedance_repeat_edit_prompt_without_changes_is_exactly_unchanged() -> None:
    from core.seedance_repeat_edit import build_seedance_repeat_edit_prompt

    base = "Keep everything unchanged."
    assert (
        build_seedance_repeat_edit_prompt(
            base,
            number_value="  ",
            outfit_value=None,
        )
        == base
    )


def test_seedance_repeat_edit_prompt_rejects_provider_limit_overflow() -> None:
    from core.seedance_repeat_edit import SeedanceRepeatEditError, build_seedance_repeat_edit_prompt

    with pytest.raises(SeedanceRepeatEditError, match="30,000"):
        build_seedance_repeat_edit_prompt(
            "x" * 30_000,
            number_value="25",
            outfit_value="black jacket",
        )


def test_feed_remix_contract_has_seedance_specific_edit_fields() -> None:
    from api.miniapp_routes import FeedRemixRequest

    body = FeedRemixRequest(
        model="bytedance/seedance-2-5",
        seedance_edit_number="25",
        seedance_edit_outfit="чёрная кожаная куртка",
    )

    assert body.seedance_edit_number == "25"
    assert body.seedance_edit_outfit == "чёрная кожаная куртка"


def test_feed_remix_runner_exposes_seedance_repeat_edit_controls() -> None:
    source = Path("webapp/src/features/feed-remix-runner.tsx").read_text(encoding="utf-8")

    assert "Seedance · изменить детали" in source
    assert "Цифра / надпись" in source
    assert "Одежда" in source
    assert "seedance_edit_number" in source
    assert "seedance_edit_outfit" in source


def test_telegram_seedance_repeat_has_dedicated_edit_states_and_fields() -> None:
    states = Path("bot/states/__init__.py").read_text(encoding="utf-8")
    handler = Path("bot/handlers/video_gen.py").read_text(encoding="utf-8")
    feed = Path("bot/handlers/feed.py").read_text(encoding="utf-8")

    assert "seedance_repeat_number = State()" in states
    assert "seedance_repeat_outfit = State()" in states
    assert "seedance_repeat_number" in handler
    assert "seedance_repeat_outfit" in handler
    assert "feed_source_video_url" in feed


def test_seedance_video_request_accepts_source_video_for_edit() -> None:
    from api.miniapp_routes import _normalize_video_request

    normalized = _normalize_video_request(
        model_key="bytedance/seedance-2-5",
        mode="video",
        duration=5,
        aspect_ratio="adaptive",
        resolution="720p",
        image_url=None,
        reference_urls=[],
        video_url="https://example.test/source.mp4",
    )

    assert normalized["reference_video_url"] == "https://example.test/source.mp4"
    assert normalized["image_url"] is None
