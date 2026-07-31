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


@pytest.mark.asyncio
async def test_cb_video_model_feed_repeat_forces_image_upload() -> None:
    call = make_callback(data="vid_model:kling-3.0/video")
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    mock_cost = _make_video_model_cost("kling-3.0/video", credits=8, display_name="Kling 3.0")
    mock_state = _fake_state(
        feed_use_gen_type="video",
        feed_use_prompt="hidden prompt",
        feed_force_reference=True,
    )

    with patch("bot.handlers.video_gen.repo", AsyncMock(resolve_video_model_cost=AsyncMock(return_value=mock_cost))):
        with patch("bot.handlers.video_gen.safe_edit_message", AsyncMock()) as edit:
            await video_gen.cb_video_model(call, AsyncMock(), mock_state, mock_db_user)

    assert any(call.kwargs == {"mode": "image"} for call in mock_state.update_data.await_args_list)
    mock_state.set_state.assert_awaited_with(VideoGenFSM.image_upload)
    assert "повтор по фото" in edit.await_args.args[1]


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


@pytest.mark.asyncio
async def test_cb_vpar_next_feed_repeat_launches_hidden_prompt() -> None:
    call = make_callback(data="vpar_next")
    status_msg = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
    call.message.answer = AsyncMock(return_value=status_msg)
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    mock_state = _fake_state(
        model_key="kling-3.0/video",
        duration=5,
        aspect_ratio="16:9",
        resolution="1080p",
        mode="image",
        credits=8,
        grok_mode="normal",
        image_file_id="photo_1",
        ref_file_ids=["photo_1"],
        feed_use_gen_type="video",
        feed_use_prompt="hidden source prompt",
        feed_use_gen_id=88,
        source_feed_gen_id=88,
    )
    mock_cost = _make_video_model_cost("kling-3.0/video", 8, "Kling 3.0")
    mock_gen = SimpleNamespace(id=103, task_id=None, model="kling-3.0/video")
    repo_stub = AsyncMock(
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        get_generation_by_id=AsyncMock(return_value=SimpleNamespace(id=88, user_id=99)),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )

    with patch("bot.handlers.video_gen.repo", repo_stub):
        with patch("bot.handlers.video_gen.mirror_telegram_file", AsyncMock(return_value="https://cdn.test/ref.jpg")):
            with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
                generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_feed", provider="kieai", uses_webhook=True)),
                get_poll_fn=MagicMock(),
            )) as mock_video_service:
                await video_gen.cb_vpar_next(call, mock_state, mock_session, mock_db_user, mock_bot)

    assert repo_stub.create_generation.await_args.args[4] == "hidden source prompt"
    assert repo_stub.create_generation.await_args.kwargs["source_feed_gen_id"] == 88
    assert mock_video_service.generate_video.await_args.args[1] == "hidden source prompt"
    assert mock_video_service.generate_video.await_args.kwargs["image_url"] == "https://cdn.test/ref.jpg"
    assert "hidden source prompt" not in call.message.answer.await_args.args[0]
    mock_state.clear.assert_awaited_once()


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


@pytest.mark.asyncio
async def test_handle_image_upload_gemini_omni_collects_multiple_refs() -> None:
    msg = make_message(text="test")
    msg.photo = [SimpleNamespace(file_size=1000, file_id="photo_1")]
    msg.answer = AsyncMock()
    mock_state = _fake_state(
        model_key="gemini-omni-video",
        mode="image",
        duration=4,
        aspect_ratio="16:9",
        resolution="720p",
        ref_file_ids=["photo_0"],
    )
    mock_cost = _make_video_model_cost("gemini-omni-video", credits=90, display_name="Gemini Omni")

    with patch("bot.handlers.video_gen.repo", SimpleNamespace(get_model_cost=AsyncMock(return_value=mock_cost))):
        await video_gen.handle_image_upload(msg, mock_state, AsyncMock())

    updated = await mock_state.get_data()
    assert updated["image_file_id"] == "photo_0"
    assert updated["ref_file_ids"] == ["photo_0", "photo_1"]
    msg.answer.assert_awaited_once()
    assert "Фото 2/7" in msg.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_handle_video_prompt_passes_all_gemini_omni_image_refs() -> None:
    msg = make_message(text="multiref video")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru", username="test", full_name="Test", is_banned=False)
    mock_state = _fake_state(
        model_key="gemini-omni-video",
        duration=4,
        aspect_ratio="16:9",
        resolution="720p",
        mode="image",
        credits=90,
        grok_mode="normal",
        image_file_id="photo_1",
        ref_file_ids=["photo_1", "photo_2", "photo_3"],
    )
    mock_cost = _make_video_model_cost("gemini-omni-video", 90, "Gemini Omni")
    mock_gen = SimpleNamespace(id=103, task_id=None, model="gemini-omni-video")

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )):
        with patch("bot.handlers.video_gen.mirror_telegram_file", AsyncMock(side_effect=[
            "https://cdn.test/1.jpg",
            "https://cdn.test/2.jpg",
            "https://cdn.test/3.jpg",
        ])):
            with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
                generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_omni_refs", provider="kieai")),
                get_poll_fn=MagicMock(),
            )) as mock_video_service:
                await video_gen.handle_video_prompt(msg, mock_state, mock_session, mock_db_user, mock_bot)

    assert mock_video_service.generate_video.await_args.kwargs["image_url"] == [
        "https://cdn.test/1.jpg",
        "https://cdn.test/2.jpg",
        "https://cdn.test/3.jpg",
    ]


@pytest.mark.asyncio
async def test_regen_video_restores_kie_image_refs() -> None:
    call = make_callback(data="regen:video:777")
    status_msg = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
    call.message.answer = AsyncMock(return_value=status_msg)
    mock_state = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    prev = SimpleNamespace(
        id=777,
        user_id=42,
        model="gemini-omni-video",
        prompt="same prompt",
        task_id="task_prev",
        source_feed_gen_id=None,
    )
    mock_cost = _make_video_model_cost("gemini-omni-video", 90, "Gemini Omni")
    new_gen = SimpleNamespace(id=778, task_id=None, model="gemini-omni-video")
    status_payload = {
        "data": {
            "param": {
                "input": {
                    "duration": "8",
                    "aspect_ratio": "9:16",
                    "resolution": "720p",
                    "image_urls": ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"],
                    "audio_ids": ["audio_1"],
                    "prompt": "same prompt",
                }
            }
        }
    }

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        get_generation_by_id=AsyncMock(return_value=prev),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=new_gen),
        update_generation_task=AsyncMock(),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )):
        with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            kieai_client=SimpleNamespace(get_task_status=AsyncMock(return_value=status_payload)),
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_new", provider="kieai", uses_webhook=True)),
            get_poll_fn=MagicMock(),
        )) as mock_video_service:
            await video_gen.cb_regen_video(call, AsyncMock(), mock_state, mock_db_user, AsyncMock())

    kwargs = mock_video_service.generate_video.await_args.kwargs
    assert kwargs["image_url"] == ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"]
    assert kwargs["duration"] == 8
    assert kwargs["aspect_ratio"] == "9:16"
    assert kwargs["audio_ids"] == ["audio_1"]


@pytest.mark.asyncio
async def test_regen_video_restores_reference_image_urls_for_dual_mode_model() -> None:
    call = make_callback(data="regen:video:777")
    status_msg = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
    call.message.answer = AsyncMock(return_value=status_msg)
    mock_state = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    prev = SimpleNamespace(
        id=777,
        user_id=42,
        model="bytedance/seedance-2",
        prompt="same face prompt",
        task_id="task_prev",
        source_feed_gen_id=None,
        input_params=None,
        parent_generation_id=None,
    )
    mock_cost = _make_video_model_cost("bytedance/seedance-2", 8, "Seedance 2")
    new_gen = SimpleNamespace(id=778, task_id=None, model="bytedance/seedance-2")
    status_payload = {
        "data": {
            "param": {
                "input": {
                    "duration": 5,
                    "aspect_ratio": "9:16",
                    "resolution": "720p",
                    "reference_image_urls": [
                        "https://cdn.test/face-a.jpg",
                        "https://cdn.test/face-b.jpg",
                    ],
                }
            }
        }
    }

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        get_generation_by_id=AsyncMock(return_value=prev),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=new_gen),
        update_generation_task=AsyncMock(),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )) as mock_repo:
        with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            kieai_client=SimpleNamespace(get_task_status=AsyncMock(return_value=status_payload)),
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_new", provider="kieai", uses_webhook=True)),
            get_poll_fn=MagicMock(),
        )) as mock_video_service:
            await video_gen.cb_regen_video(call, AsyncMock(), mock_state, mock_db_user, AsyncMock())

    image_url = mock_video_service.generate_video.await_args.kwargs["image_url"]
    assert image_url == ["https://cdn.test/face-a.jpg", "https://cdn.test/face-b.jpg"]
    assert mock_repo.create_generation.await_args.kwargs["input_params"]["image_url"] == image_url


@pytest.mark.asyncio
async def test_regen_video_prefers_saved_input_params_when_provider_omits_refs() -> None:
    call = make_callback(data="regen:video:777")
    status_msg = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
    call.message.answer = AsyncMock(return_value=status_msg)
    mock_state = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    saved_params = {
        "mode": "image",
        "duration": 5,
        "aspect_ratio": "9:16",
        "resolution": "720p",
        "image_url": "https://cdn.test/saved-face.jpg",
    }
    prev = SimpleNamespace(
        id=777,
        user_id=42,
        model="bytedance/seedance-2",
        prompt="same face prompt",
        task_id="task_prev",
        source_feed_gen_id=None,
        input_params=saved_params,
        parent_generation_id=None,
    )
    mock_cost = _make_video_model_cost("bytedance/seedance-2", 8, "Seedance 2")
    new_gen = SimpleNamespace(id=778, task_id=None, model="bytedance/seedance-2")

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        get_generation_by_id=AsyncMock(return_value=prev),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=new_gen),
        update_generation_task=AsyncMock(),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )):
        with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            kieai_client=SimpleNamespace(get_task_status=AsyncMock(return_value={"data": {"param": {"input": {}}}})),
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_new", provider="kieai", uses_webhook=True)),
            get_poll_fn=MagicMock(),
        )) as mock_video_service:
            await video_gen.cb_regen_video(call, AsyncMock(), mock_state, mock_db_user, AsyncMock())

    assert mock_video_service.generate_video.await_args.kwargs["image_url"] == "https://cdn.test/saved-face.jpg"


@pytest.mark.asyncio
async def test_handle_video_prompt_persists_reference_input_params() -> None:
    msg = make_message(text="animate this face")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru", username="test", full_name="Test", is_banned=False)
    mock_state = _fake_state(
        model_key="bytedance/seedance-2",
        duration=5,
        aspect_ratio="9:16",
        resolution="720p",
        mode="image",
        credits=8,
        grok_mode="normal",
        image_file_id="photo_1",
        ref_file_ids=["photo_1"],
    )
    mock_cost = _make_video_model_cost("bytedance/seedance-2", 8, "Seedance 2")
    mock_gen = SimpleNamespace(id=778, task_id=None, model="bytedance/seedance-2")

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )) as mock_repo:
        with patch("bot.handlers.video_gen.mirror_telegram_file", AsyncMock(return_value="https://cdn.test/face.jpg")):
            with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
                generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_new", provider="kieai", uses_webhook=True)),
                get_poll_fn=MagicMock(),
            )):
                await video_gen.handle_video_prompt(msg, mock_state, mock_session, mock_db_user, mock_bot)

    input_params = mock_repo.create_generation.await_args.kwargs["input_params"]
    assert input_params["mode"] == "image"
    assert input_params["image_url"] == "https://cdn.test/face.jpg"


@pytest.mark.asyncio
async def test_reprompt_video_restores_params_and_waits_for_new_prompt() -> None:
    call = make_callback(data="reprompt:video:777")
    mock_state = _fake_state(source_feed_gen_id=999)
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    prev = SimpleNamespace(
        id=777,
        user_id=42,
        model="gemini-omni-video",
        gen_type=GenerationType.video,
        prompt="old hidden prompt",
        task_id="task_prev",
        source_feed_gen_id=88,
    )
    mock_cost = _make_video_model_cost("gemini-omni-video", 90, "Gemini Omni")
    status_payload = {
        "data": {
            "param": {
                "input": {
                    "duration": "8",
                    "aspect_ratio": "9:16",
                    "resolution": "720p",
                    "image_urls": ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"],
                    "audio_ids": ["audio_1"],
                }
            }
        }
    }

    with (
        patch("bot.handlers.video_gen.repo", AsyncMock(
            get_generation_by_id=AsyncMock(return_value=prev),
            resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        )),
        patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            kieai_client=SimpleNamespace(get_task_status=AsyncMock(return_value=status_payload)),
        )),
        patch("bot.handlers.video_gen.safe_edit_message", AsyncMock()) as edit_message,
    ):
        await video_gen.cb_reprompt_video(call, AsyncMock(), mock_state, mock_db_user)

    mock_state.set_state.assert_awaited_with(VideoGenFSM.prompt_input)
    updated = await mock_state.get_data()
    assert updated["parent_generation_id"] == 777
    assert updated["source_feed_gen_id"] is None
    assert updated["video_reuse_prompt"] is None
    assert updated["image_url"] == ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"]
    assert "Новый промпт" in edit_message.await_args.args[1]


@pytest.mark.asyncio
async def test_reparams_video_restores_prompt_and_shows_launch_button() -> None:
    call = make_callback(data="reparams:video:777")
    mock_state = _fake_state()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    prev = SimpleNamespace(
        id=777,
        user_id=42,
        model="gemini-omni-video",
        gen_type=GenerationType.video,
        prompt="same prompt",
        task_id="task_prev",
        source_feed_gen_id=88,
    )
    mock_cost = _make_video_model_cost("gemini-omni-video", 90, "Gemini Omni")
    status_payload = {
        "data": {
            "param": {
                "input": {
                    "duration": "8",
                    "aspect_ratio": "9:16",
                    "resolution": "720p",
                    "image_urls": ["https://cdn.test/a.jpg"],
                }
            }
        }
    }

    with (
        patch("bot.handlers.video_gen.repo", AsyncMock(
            get_generation_by_id=AsyncMock(return_value=prev),
            resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        )),
        patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            kieai_client=SimpleNamespace(get_task_status=AsyncMock(return_value=status_payload)),
        )),
        patch("bot.handlers.video_gen.safe_edit_message", AsyncMock()) as edit_message,
    ):
        await video_gen.cb_reparams_video(call, AsyncMock(), mock_state, mock_db_user, AsyncMock())

    mock_state.set_state.assert_awaited_with(VideoGenFSM.params_select)
    updated = await mock_state.get_data()
    assert updated["video_reuse_prompt"] == "same prompt"
    assert updated["source_feed_gen_id"] == 88
    markup = edit_message.await_args.kwargs["reply_markup"]
    texts = {button.text for row in markup.inline_keyboard for button in row}
    assert "▶️ Запустить" in texts


@pytest.mark.asyncio
async def test_handle_video_prompt_keeps_reprompt_parent_generation() -> None:
    msg = make_message(text="new prompt")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru", username="test", full_name="Test", is_banned=False)
    mock_state = _fake_state(
        model_key="kling-3.0/video",
        duration=5,
        aspect_ratio="16:9",
        resolution="1080p",
        mode="text",
        credits=10,
        grok_mode="normal",
        parent_generation_id=777,
    )
    mock_cost = _make_video_model_cost("kling-3.0/video", 10, "Kling 3.0")
    mock_gen = SimpleNamespace(id=778, task_id=None, model="kling-3.0/video")

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )) as mock_repo:
        with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_abc", provider="kieai", uses_webhook=True)),
            get_poll_fn=MagicMock(),
        )):
            await video_gen.handle_video_prompt(msg, mock_state, mock_session, mock_db_user, mock_bot)

    assert mock_repo.create_generation.await_args.kwargs["parent_generation_id"] == 777


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
        aspect_ratio="16:9", resolution="720p",
        mode="text", credits=45, grok_mode="normal",
    )
    mock_cost = _make_video_model_cost("grok-imagine/text-to-video", 45, "Grok T2V")
    mock_gen = SimpleNamespace(id=101, task_id=None, model="grok-imagine/text-to-video")
    spend_credits = AsyncMock(return_value=True)
    resolve_video_model_cost = AsyncMock(return_value=mock_cost)

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        spend_credits=spend_credits,
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        resolve_video_model_cost=resolve_video_model_cost,
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )):
        with patch("bot.handlers.video_gen.video_service", new=SimpleNamespace(
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_grok", provider="direct")),
            get_poll_fn=MagicMock(return_value=MagicMock()),
        )):
            with patch("bot.handlers.video_gen.polling", new=SimpleNamespace(poll_until_done=AsyncMock())):
                await video_gen.handle_video_prompt(msg, mock_state, mock_session, mock_db_user, mock_bot)

    assert resolve_video_model_cost.await_args.kwargs["resolution"] == "720p"
    assert spend_credits.await_args.args[1:] == (42, 270)


@pytest.mark.asyncio
async def test_handle_video_prompt_preserves_fractional_credit_price() -> None:
    msg = make_message(text="animate portrait")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=100, language="ru", username="test", full_name="Test", is_banned=False)
    mock_state = _fake_state(
        model_key="grok-imagine-video-1-5-preview", duration=6,
        aspect_ratio="auto", resolution="480p",
        mode="image", credits=0.6, grok_mode=None,
        image_url="https://example.test/ref.jpg",
    )
    mock_cost = _make_video_model_cost("grok-imagine-video-1-5-preview", 0.6, "Grok 1.5")
    mock_gen = SimpleNamespace(id=102, task_id=None, model="grok-imagine-video-1-5-preview")
    spend_credits = AsyncMock(return_value=True)

    with patch("bot.handlers.video_gen.repo", AsyncMock(
        spend_credits=spend_credits,
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
        resolve_video_model_cost=AsyncMock(return_value=mock_cost),
        fail_generation=AsyncMock(),
        add_credits=AsyncMock(),
    )), patch("bot.handlers.video_gen._video_reference_image_url", AsyncMock(return_value="https://example.test/ref.jpg")), patch(
        "bot.handlers.video_gen.video_service",
        new=SimpleNamespace(
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id="task_grok_15", provider="direct")),
            get_poll_fn=MagicMock(return_value=MagicMock()),
        ),
    ), patch("bot.handlers.video_gen.polling", new=SimpleNamespace(poll_until_done=AsyncMock())):
        await video_gen.handle_video_prompt(msg, mock_state, mock_session, mock_db_user, mock_bot)

    assert spend_credits.await_args.args[1:] == (42, 3.6)


def test_video_state_resolution_normalizes_kling_motion_aliases() -> None:
    assert video_gen._normalize_resolution_for_state("kling-3.0/video", "2K") == "pro"
    assert video_gen._normalize_resolution_for_state("kling-3.0/video", "720p") == "std"
    assert video_gen._normalize_resolution_for_state("kling-3.0/motion-control", "pro") == "1080p"


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
