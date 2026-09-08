from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers import music_gen
from bot.states import MusicFSM
from db.models import GenerationType
from tests.factories import make_callback, make_message


def _music_cost(value: float = 20.0):
    return SimpleNamespace(
        model_key="suno/v5.5",
        display_name="Suno 5.5",
        credits=value,
        gen_type=GenerationType.music,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_music_prompt_stops_at_review_without_spending() -> None:
    msg = make_message(text="cinematic synthwave")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"instrumental": False, "music_model_key": "suno/v5.5"})
    user = SimpleNamespace(id=42, credits=100)
    repo_mock = AsyncMock()
    repo_mock.spend_credits = AsyncMock()

    session = AsyncMock()
    with (
        patch("bot.handlers.music_gen._resolve_music_model_for_key", AsyncMock(return_value=_music_cost(20))),
        patch("bot.handlers.music_gen.repo", repo_mock),
    ):
        await music_gen.music_prompt(msg, state, session, user)

    repo_mock.spend_credits.assert_not_awaited()
    state.set_state.assert_awaited_with(MusicFSM.review)
    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "Проверь перед запуском" in text
    assert "20 💋" in text
    assert "спишутся только после" in text


@pytest.mark.asyncio
async def test_music_review_launch_spends_only_after_confirmation() -> None:
    call = make_callback(data="music:review:launch")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "music_review_kind": "prompt",
        "music_review_prompt": "cinematic synthwave",
        "music_review_cost": 20.0,
        "music_model_key": "suno/v5.5",
        "music_model_name": "Suno 5.5",
        "instrumental": False,
    })
    user = SimpleNamespace(id=42, credits=100)
    generation = SimpleNamespace(id=77)
    repo_mock = AsyncMock()
    repo_mock.spend_credits = AsyncMock(return_value=True)
    repo_mock.create_generation = AsyncMock(return_value=generation)
    repo_mock.update_generation_task = AsyncMock()

    session = AsyncMock()
    with (
        patch("bot.handlers.music_gen._resolve_music_model_for_key", AsyncMock(return_value=_music_cost(20))),
        patch("bot.handlers.music_gen.repo", repo_mock),
        patch("bot.handlers.music_gen.create_music_task", AsyncMock(return_value="task-123")),
        patch("bot.handlers.music_gen.register_task"),
        patch("bot.handlers.music_gen.register_miniapp_task"),
        patch("bot.handlers.music_gen.safe_edit_message", AsyncMock()),
        patch("bot.handlers.music_gen.safe_answer_callback", AsyncMock()),
    ):
        await music_gen.music_review_launch(call, state, session, user)

    repo_mock.spend_credits.assert_awaited_once_with(session, 42, 20.0)


@pytest.mark.asyncio
async def test_music_review_price_change_requires_second_confirmation_without_spending() -> None:
    call = make_callback(data="music:review:launch")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "music_review_kind": "prompt",
        "music_review_prompt": "cinematic synthwave",
        "music_review_cost": 20.0,
        "music_model_key": "suno/v5.5",
        "music_model_name": "Suno 5.5",
        "instrumental": False,
    })
    user = SimpleNamespace(id=42, credits=100)
    repo_mock = AsyncMock()
    repo_mock.spend_credits = AsyncMock()
    session = AsyncMock()

    with (
        patch("bot.handlers.music_gen._resolve_music_model_for_key", AsyncMock(return_value=_music_cost(25))),
        patch("bot.handlers.music_gen.repo", repo_mock),
        patch("bot.handlers.music_gen.safe_edit_message", AsyncMock()) as edit_message,
        patch("bot.handlers.music_gen.safe_answer_callback", AsyncMock()) as answer_callback,
    ):
        await music_gen.music_review_launch(call, state, session, user)

    repo_mock.spend_credits.assert_not_awaited()
    state.update_data.assert_awaited_with(music_review_cost=25.0)
    assert "25 💋" in edit_message.await_args.args[1]
    answer_callback.assert_awaited_with(call, "Цена обновилась — проверь ещё раз", show_alert=True)


@pytest.mark.asyncio
async def test_source_audio_prompt_also_stops_at_review_without_spending() -> None:
    msg = make_message(text="more cinematic")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "suno_source_operation": "cover",
        "suno_source_url": "https://example.com/source.mp3",
        "suno_source_duration": 12.0,
        "music_model_key": "suno/v5.5",
        "instrumental": False,
    })
    user = SimpleNamespace(id=42, credits=100)
    repo_mock = AsyncMock()
    repo_mock.spend_credits = AsyncMock()
    session = AsyncMock()

    with (
        patch("bot.handlers.music_gen._resolve_music_model_for_key", AsyncMock(return_value=_music_cost(20))),
        patch("bot.handlers.music_gen.repo", repo_mock),
        patch("bot.handlers.music_gen.create_source_audio_generation", AsyncMock()) as source_launch,
    ):
        await music_gen.music_source_prompt(msg, state, session, user)

    source_launch.assert_not_awaited()
    repo_mock.spend_credits.assert_not_awaited()
    state.set_state.assert_awaited_with(MusicFSM.review)
    assert "Проверь перед запуском" in msg.answer.await_args.args[0]
