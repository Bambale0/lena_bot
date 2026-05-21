"""Тесты хендлеров video_gen — покрытие видео-флоу."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers import video_gen
from bot.states import VideoGenFSM
from db.models import GenerationType
from tests.factories import make_callback, make_message

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_video_model_cost(model_key="kling-3.0/video", credits=8, display_name="Kling 3.0"):
    return SimpleNamespace(
        model_key=model_key, display_name=display_name,
        credits=credits, gen_type=GenerationType.video,
    )


def _fake_state(**initial: object):
    """
    FSMContext-стаб:
    • get_data()  → настоящий мутабельный dict,
    • update_data() — AsyncMock с side_effect (отслеживает вызовы И мутирует dict),
    • set_state()  — AsyncMock (await-able + assertions).
    """
    real_data = dict(initial)

    async def _do_update(**kwargs: object) -> None:
        real_data.update(kwargs)

    state = AsyncMock()
    state.get_data = AsyncMock(return_value=real_data)
    state.update_data = AsyncMock(side_effect=_do_update)
    state.set_state = AsyncMock()
    return state


# ── menu:video ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_video_menu_opens_menu() -> None:
    call = make_callback(data="menu:video")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    await video_gen.cb_video_menu(call, AsyncMock(), AsyncMock())
    call.message.edit_text.assert_awaited_once()
    assert "Генерация видео" in call.message.edit_text.call_args[0][0]
    call.answer.assert_awaited_once()


# ── vid_group ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_video_group_shows_models() -> None:
    call = make_callback(data="vid_group:fast")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_costs = [
        _make_video_model_cost("kling-3.0/video", 8),
        _make_video_model_cost("kling-2.6/text-to-video", 5),
    ]
    with patch("bot.handlers.video_gen.repo", AsyncMock(get_all_model_costs=AsyncMock(return_value=mock_costs))):
        await video_gen.cb_video_group(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()


# ── vid_model ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_video_model_insufficient_credits() -> None:
    call = make_callback(data="vid_model:kling-3.0/video")
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=5, language="ru")
    mock_cost = _make_video_model_cost("kling-3.0/video", credits=8)
    with patch("bot.handlers.video_gen.repo", AsyncMock(resolve_video_model_cost=AsyncMock(return_value=mock_cost))):
        await video_gen.cb_video_model(call, AsyncMock(), AsyncMock(), mock_db_user)
    call.answer.assert_awaited_once()
    assert "Недостаточно" in call.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_video_model_grok_uses_per_second_price() -> None:
    call = make_callback(data="vid_model:grok-imagine/text-to-video")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=300, language="ru")
    mock_cost = _make_video_model_cost("grok-imagine/text-to-video", credits=35, display_name="Grok T2V")
    mock_state = _fake_state()
    with patch("bot.handlers.video_gen.repo", AsyncMock(resolve_video_model_cost=AsyncMock(return_value=mock_cost))):
        with patch("bot.handlers.video_gen.video_params_kb", return_value=MagicMock()):
            await video_gen.cb_video_model(call, AsyncMock(), mock_state, mock_db_user)
    mock_state.set_state.assert_called_once_with(VideoGenFSM.params_select)


@pytest.mark.asyncio
async def test_cb_video_model_no_cost_found() -> None:
    call = make_callback(data="vid_model:unknown_model")
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    with patch("bot.handlers.video_gen.repo", AsyncMock(resolve_video_model_cost=AsyncMock(return_value=None))):
        await video_gen.cb_video_model(call, AsyncMock(), AsyncMock(), mock_db_user)
    call.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_video_model_single_mode() -> None:
    """kling-2.6/text-to-video has only 'text' mode — goes to params directly."""
    call = make_callback(data="vid_model:kling-2.6/text-to-video")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    mock_cost = _make_video_model_cost("kling-2.6/text-to-video", credits=5, display_name="Kling 2.6 T2V")
    mock_state = _fake_state(
        model_key="kling-2.6/text-to-video", duration=5,
        aspect_ratio="16:9", resolution="720p", grok_mode=None,
    )
    with patch("bot.handlers.video_gen.repo", AsyncMock(resolve_video_model_cost=AsyncMock(return_value=mock_cost))):
        with patch("bot.handlers.video_gen.video_params_kb", return_value=MagicMock()):
            await video_gen.cb_video_model(call, AsyncMock(), mock_state, mock_db_user)
    mock_state.set_state.assert_called_once_with(VideoGenFSM.params_select)


# ── vid_mode ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_video_mode_selects_mode() -> None:
    """kling-3.0 has both text and image modes → goes to params_select."""
    call = make_callback(data="vid_mode:text:kling-3.0/video")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_state = _fake_state(
        model_key="kling-3.0/video", duration=5,
        aspect_ratio="16:9", resolution="2K", grok_mode=None,
    )
    mock_cost = _make_video_model_cost("kling-3.0/video", 10, "Kling 3.0")
    with patch("bot.handlers.video_gen.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        with patch("bot.handlers.video_gen.video_params_kb", return_value=MagicMock()):
            await video_gen.cb_video_mode(call, mock_state, AsyncMock())
    mock_state.update_data.assert_awaited_once()
    mock_state.set_state.assert_called_with(VideoGenFSM.params_select)


# ── handle_video_upload ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_video_upload_wrong_step() -> None:
    msg = make_message(text="test")
    msg.video = MagicMock()
    msg.video.duration = 10
    msg.video.file_id = "file_123"
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"motion_step": "person", "model_key": "kling-2.6/motion-control"})
    await video_gen.handle_video_upload(msg, mock_state, AsyncMock(), SimpleNamespace(id=42, credits=500, language="ru"), AsyncMock())
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_video_upload_insufficient_credits() -> None:
    msg = make_message(text="test")
    msg.video = MagicMock()
    msg.video.duration = 60
    msg.video.file_id = "file_123"
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"motion_step": "video_url", "model_key": "kling-3.0/video", "credits": 10})
    mock_db_user = SimpleNamespace(id=42, credits=50, language="ru")
    mock_cost = _make_video_model_cost("kling-3.0/video", credits=10)
    with patch("bot.handlers.video_gen.repo", AsyncMock(resolve_video_model_cost=AsyncMock(return_value=mock_cost))):
        await video_gen.handle_video_upload(msg, mock_state, AsyncMock(), mock_db_user, AsyncMock())
    msg.answer.assert_awaited_once()
    assert "недостаточно" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_video_upload_accepts_gemini_omni_video_mode() -> None:
    msg = make_message(text="test")
    msg.video = MagicMock()
    msg.video.duration = 9
    msg.video.file_id = "video_123"
    msg.answer = AsyncMock()
    mock_state = _fake_state(
        model_key="gemini-omni-video",
        mode="video",
        duration=4,
        aspect_ratio="16:9",
        resolution="720p",
        credits=90,
    )
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    mock_cost = _make_video_model_cost("gemini-omni-video", credits=240, display_name="Gemini Omni")

    with patch("bot.handlers.video_gen.repo", SimpleNamespace(
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        get_model_cost=AsyncMock(return_value=mock_cost),
    )):
        with patch("bot.handlers.video_gen.mirror_telegram_file", AsyncMock(return_value="https://cdn.test/video.mp4")):
            await video_gen.handle_video_upload(msg, mock_state, MagicMock(), mock_db_user, MagicMock())

    mock_state.set_state.assert_awaited_with(VideoGenFSM.params_select)
    updated = await mock_state.get_data()
    assert updated["reference_video_url"] == "https://cdn.test/video.mp4"
    assert updated["video_clip_end"] == 9


@pytest.mark.asyncio
async def test_handle_omni_ids_input_rejects_multiple_audio_ids() -> None:
    msg = make_message(text="audio_1,audio_2")
    msg.answer = AsyncMock()
    mock_state = _fake_state(
        model_key="gemini-omni-video",
        omni_input_target="audio",
    )

    await video_gen.handle_omni_ids_input(msg, mock_state, AsyncMock())

    msg.answer.assert_awaited_once()
    assert "audio_ids supports at most 1" in msg.answer.call_args.args[0]


# ── handle_image_upload ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_image_upload_motion_person_step() -> None:
    msg = make_message(text="test")
    msg.photo = [MagicMock()]
    msg.photo[0].file_size = 1000
    msg.photo[0].file_id = "photo_123"
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"model_key": "kling-2.6/motion-control", "motion_step": "person"})

    async def fake_mirror(*a, **kw):
        return "https://storage.example.com/photo_123.jpg"

    with patch("bot.handlers.video_gen.mirror_telegram_file", side_effect=fake_mirror):
        await video_gen.handle_image_upload(msg, mock_state, AsyncMock())
    assert mock_state.update_data.call_args[1].get("motion_step") == "video_url"


# ── _params_summary ───────────────────────────────────────────────────────────

def test_params_summary_with_all_params() -> None:
    data = {"aspect_ratio": "16:9", "duration": 10, "resolution": "1080p", "grok_mode": "turbo"}
    result = video_gen._params_summary(data)
    assert "16:9" in result
    assert "10 сек" in result


def test_params_summary_empty() -> None:
    assert video_gen._params_summary({}) == "по умолчанию"


# ── _has_params ───────────────────────────────────────────────────────────────

def test_has_params_true() -> None:
    assert video_gen._has_params("kling-3.0/video") is True


def test_has_params_true_for_motion() -> None:
    assert video_gen._has_params("kling-2.6/motion-control") is True


def test_has_params_false() -> None:
    assert video_gen._has_params("nonexistent_model") is False


# ── handle_video_prompt ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_video_prompt_insufficient_credits() -> None:
    msg = make_message(text="some prompt")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"model_key": "kling-3.0/video", "duration": 5, "credits": 10})
    mock_db_user = SimpleNamespace(id=42, credits=3, language="ru")
    with patch("bot.handlers.video_gen.repo", AsyncMock(spend_credits=AsyncMock(return_value=False))):
        await video_gen.handle_video_prompt(msg, mock_state, AsyncMock(), mock_db_user, AsyncMock())
    msg.answer.assert_awaited_once()
    assert "недостаточно" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_video_prompt_generates() -> None:
    msg = make_message(text="a beautiful sunset")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru", username="test", full_name="Test", is_banned=False)
    mock_state = _fake_state(
        model_key="kling-3.0/video", duration=5,
        aspect_ratio="16:9", resolution="1080p",
        mode="text", credits=10, grok_mode="normal",
    )
    mock_cost = _make_video_model_cost("kling-3.0/video", 10, "Kling 3.0")
    mock_gen = SimpleNamespace(id=100, task_id=None, model="kling-3.0/video")

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )):
        with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_abc", provider="direct")),
            get_poll_fn=MagicMock(return_value=MagicMock()),
        )):
            with patch("bot.handlers.video_gen.polling", new=SimpleNamespace(poll_until_done=AsyncMock())):
                await video_gen.handle_video_prompt(msg, mock_state, mock_session, mock_db_user, mock_bot)

    mock_state.set_state.assert_awaited_once_with(VideoGenFSM.generating)


@pytest.mark.asyncio
async def test_handle_video_prompt_grok_spends_per_second_price() -> None:
    msg = make_message(text="dramatic storm over sea")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=100, language="ru", username="test", full_name="Test", is_banned=False)
    mock_state = _fake_state(
        model_key="grok-imagine/text-to-video", duration=6,
        aspect_ratio="16:9", resolution="480p",
        mode="text", credits=35, grok_mode="normal",
    )
    mock_cost = _make_video_model_cost("grok-imagine/text-to-video", 35, "Grok T2V")
    mock_gen = SimpleNamespace(id=101, task_id=None, model="grok-imagine/text-to-video")
    spend_credits = AsyncMock(return_value=True)

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        spend_credits=spend_credits,
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )):
        with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_grok", provider="direct")),
            get_poll_fn=MagicMock(return_value=MagicMock()),
        )):
            with patch("bot.handlers.video_gen.polling", new=SimpleNamespace(poll_until_done=AsyncMock())):
                await video_gen.handle_video_prompt(msg, mock_state, mock_session, mock_db_user, mock_bot)

    assert spend_credits.await_args.args[1:] == (42, 210)


@pytest.mark.asyncio
async def test_handle_video_prompt_motion_control_keeps_user_prompt() -> None:
    msg = make_message(text="camera push in")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru", username="test", full_name="Test", is_banned=False)
    mock_state = _fake_state(
        model_key="kling-2.6/motion-control",
        duration=5,
        resolution="720p",
        mode="motion",
        credits=7,
        motion_step="prompt",
        image_url="https://example.test/person.jpg",
        reference_video_url="https://example.test/ref.mp4",
    )
    mock_cost = _make_video_model_cost("kling-2.6/motion-control", 7, "Kling 2.6 Motion")
    mock_gen = SimpleNamespace(id=101, task_id=None, model="kling-2.6/motion-control")

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )) as mock_repo:
        with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_motion", provider="kieai")),
            get_poll_fn=MagicMock(),
        )) as mock_video_service:
            await video_gen.handle_video_prompt(msg, mock_state, mock_session, mock_db_user, mock_bot)

    assert mock_repo.create_generation.await_args.args[4] == "camera push in"
    assert mock_video_service.generate_video.await_args.args[1] == "camera push in"


@pytest.mark.asyncio
async def test_handle_video_prompt_passes_gemini_omni_extras() -> None:
    msg = make_message(text="multimodal video")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru", username="test", full_name="Test", is_banned=False)
    mock_state = _fake_state(
        model_key="gemini-omni-video",
        duration=4,
        aspect_ratio="16:9",
        resolution="720p",
        mode="video",
        credits=240,
        grok_mode="normal",
        reference_video_url="https://cdn.test/source.mp4",
        video_clip_start=0,
        video_clip_end=8,
        audio_ids=["audio_1"],
        character_ids=["character_1"],
        seed=99,
    )
    mock_cost = _make_video_model_cost("gemini-omni-video", 240, "Gemini Omni")
    mock_gen = SimpleNamespace(id=102, task_id=None, model="gemini-omni-video")

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )):
        with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_omni", provider="kieai")),
            get_poll_fn=MagicMock(),
        )) as mock_video_service:
            await video_gen.handle_video_prompt(msg, mock_state, mock_session, mock_db_user, mock_bot)

    kwargs = mock_video_service.generate_video.await_args.kwargs
    assert kwargs["reference_video_url"] == "https://cdn.test/source.mp4"
    assert kwargs["audio_ids"] == ["audio_1"]
    assert kwargs["character_ids"] == ["character_1"]
    assert kwargs["video_end"] == 8
    assert kwargs["seed"] == 99
