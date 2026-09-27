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

    assert normalized["reference_video_url"] == ["https://example.test/source.mp4"]
    assert normalized["image_url"] is None



@pytest.mark.asyncio
async def test_seedance_feed_repeat_edit_uses_source_video_and_source_duration_before_charge(monkeypatch) -> None:
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from api import miniapp_routes as routes
    from db.models import GenerationStatus, GenerationType

    source = SimpleNamespace(
        id=88,
        model="bytedance/seedance-2-5",
        gen_type=GenerationType.video,
        prompt="Keep the source scene.",
        result_url="https://example.test/static/upload/source.mp4",
        result_urls=None,
    )
    user = SimpleNamespace(id=1, credits=1000)
    session = AsyncMock()

    edit_duration = AsyncMock(return_value=7)
    video_generate = AsyncMock(
        return_value=SimpleNamespace(task_id="seedance-edit-task", is_async=True)
    )
    created: dict[str, object] = {}

    async def fake_create_generation(
        _session,
        _user_id,
        model,
        gen_type,
        prompt,
        credits_spent,
        **kwargs,
    ):
        created["prompt"] = prompt
        created["input_params"] = kwargs.get("input_params")
        return SimpleNamespace(
            id=901,
            model=model,
            gen_type=gen_type,
            prompt=prompt,
            status=GenerationStatus.processing,
            result_url=None,
            result_urls=None,
            credits_spent=credits_spent,
            created_at=datetime.now(timezone.utc),
            is_public_feed=False,
            is_prompt_library=False,
            source_feed_gen_id=kwargs.get("source_feed_gen_id"),
        )

    monkeypatch.setattr(
        routes.repo,
        "get_public_feed_generation",
        AsyncMock(return_value=source),
    )
    monkeypatch.setattr(
        routes.repo,
        "resolve_video_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=3)),
    )
    monkeypatch.setattr(
        routes.repo,
        "count_user_active_generations",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(routes.repo, "spend_credits", AsyncMock(return_value=True))
    monkeypatch.setattr(routes.repo, "create_generation", fake_create_generation)
    monkeypatch.setattr(routes.repo, "update_generation_task", AsyncMock())
    monkeypatch.setattr(routes.repo, "increment_feed_share", AsyncMock())
    monkeypatch.setattr(routes, "seedance25_edit_billing_duration", edit_duration)
    monkeypatch.setattr(routes.video_service, "generate_video", video_generate)

    body = routes.FeedRemixRequest(
        model="bytedance/seedance-2-5",
        duration=5,
        aspect_ratio="adaptive",
        resolution="720p",
        video_url=source.result_url,
        seedance_edit_number="25",
        seedance_edit_outfit="чёрная куртка",
    )

    result = await routes.remix_feed_post(
        88,
        body,
        session=session,
        user=user,
    )

    edit_duration.assert_awaited_once()
    assert result.prompt_hidden is True
    assert "25" in str(created["prompt"])
    assert "чёрная куртка" in str(created["prompt"])
    params = created["input_params"]
    assert isinstance(params, dict)
    assert params["reference_video_url"] == [source.result_url]
    assert params["image_url"] is None
    assert params["duration"] == 7
    assert video_generate.await_args.kwargs["reference_video_url"] == [source.result_url]


@pytest.mark.asyncio
async def test_seedance_router_opens_repeat_edit_flow_for_feed_video(monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from bot.handlers import seedance25_references as refs
    from bot.states import VideoGenFSM

    call = SimpleNamespace(
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "feed_use_gen_type": "video",
        "feed_use_prompt": "hidden source prompt",
        "feed_source_video_url": "https://example.test/source.mp4",
        "feed_force_reference": True,
    })
    model_cost = SimpleNamespace(credits=3, display_name="Seedance 2.5")
    monkeypatch.setattr(
        refs.repo,
        "resolve_video_model_cost",
        AsyncMock(return_value=model_cost),
    )
    monkeypatch.setattr(refs, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(refs, "safe_answer_callback", AsyncMock())

    await refs.choose_seedance25(
        call,
        state,
        session=AsyncMock(),
        db_user=SimpleNamespace(credits=1000),
    )

    state.set_state.assert_awaited_once_with(VideoGenFSM.seedance_repeat_number)
    update = state.update_data.await_args.kwargs
    assert update["seedance_repeat_edit"] is True
    assert update["reference_video_url"] == ["https://example.test/source.mp4"]
    assert update["feed_force_reference"] is False
