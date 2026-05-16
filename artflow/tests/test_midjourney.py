"""Тесты хендлеров midjourney."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.midjourney_service import MJBotType, MJSpeed
from bot.handlers import midjourney
from bot.states import MidjourneyFSM
from tests.factories import make_callback, make_message


def _fake_state(**initial: object):
    real_data = dict(initial)

    async def _do_update(**kwargs: object) -> None:
        real_data.update(kwargs)

    state = AsyncMock()
    state.get_data = AsyncMock(return_value=real_data)
    state.update_data = AsyncMock(side_effect=_do_update)
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


@pytest.fixture(autouse=True)
def _close_background_tasks(monkeypatch):
    created = []

    def fake_create_task(coro):
        created.append(coro)
        coro.close()
        return SimpleNamespace(cancel=MagicMock())

    monkeypatch.setattr(midjourney.asyncio, "create_task", fake_create_task)
    return created


# ── menu:mj ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_mj_menu_shows_submenu() -> None:
    call = make_callback(data="menu:mj")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    repo_mock = AsyncMock(get_model_cost=AsyncMock(return_value=SimpleNamespace(credits=10)))
    with (
        patch("bot.handlers.midjourney.repo", repo_mock),
        patch("bot.handlers.midjourney._ensure_admin_access", return_value=True),
    ):
        await midjourney.cb_mj_menu(call, AsyncMock(), AsyncMock())
    call.message.edit_text.assert_awaited_once()
    args = call.message.edit_text.call_args
    assert "Midjourney" in args[0][0]


# ── mj:imagine ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_imagine_start() -> None:
    call = make_callback(data="mj:imagine")
    mock_state = _fake_state()
    await midjourney.cb_imagine_start(call, mock_state)
    mock_state.set_state.assert_awaited_once_with(MidjourneyFSM.bot_type_select)


# ── mj_bt ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_bot_type() -> None:
    call = make_callback(data="mj_bt:niji")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_state = _fake_state()
    await midjourney.cb_bot_type(call, mock_state)
    mock_state.update_data.assert_awaited_once()
    mock_state.set_state.assert_awaited_once_with(MidjourneyFSM.speed_select)


# ── mj_sp: speed select ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_speed_insufficient_credits() -> None:
    call = make_callback(data="mj_sp:fast")
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=5, language="ru")
    mock_cost = SimpleNamespace(credits=10, display_name="MJ Standard")
    with patch("bot.handlers.midjourney.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        await midjourney.cb_speed(call, AsyncMock(), AsyncMock(), mock_db_user)
    call.answer.assert_awaited_once()
    # answer("text", show_alert=True) → keyword arg
    assert call.answer.call_args[1].get("show_alert") is True


@pytest.mark.asyncio
async def test_cb_speed_sufficient_credits() -> None:
    call = make_callback(data="mj_sp:fast")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    mock_cost = SimpleNamespace(credits=10, display_name="MJ Standard")
    mock_state = _fake_state()
    with patch("bot.handlers.midjourney.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        await midjourney.cb_speed(call, mock_state, AsyncMock(), mock_db_user)
    mock_state.set_state.assert_awaited_once_with(MidjourneyFSM.reference_upload)


# ── mj_ref:skip ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_mj_ref_skip() -> None:
    call = make_callback(data="mj_ref:skip")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_state = _fake_state()
    await midjourney.cb_mj_ref_skip(call, mock_state)
    mock_state.update_data.assert_awaited_once_with(reference_b64=None, reference_url=None)
    mock_state.set_state.assert_awaited_once_with(MidjourneyFSM.prompt_input)


# ── handle_mj_reference_photo ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_mj_reference_photo() -> None:
    msg = make_message(text="test")
    msg.photo = [MagicMock()]
    msg.photo[-1] = msg.photo[0]
    msg.photo[0].file_id = "photo_123"
    msg.answer = AsyncMock()

    mock_bot = AsyncMock()
    mock_file = SimpleNamespace(file_path="test.jpg")
    mock_bot.get_file = AsyncMock(return_value=mock_file)

    import io
    buf = io.BytesIO(b"\xff\xd8\xff\xe0test")
    mock_bot.download_file = AsyncMock(return_value=buf)
    mock_bot.get_file = AsyncMock(return_value=mock_file)

    mock_state = _fake_state(credits=10)
    with patch("bot.handlers.midjourney.mirror_telegram_file", AsyncMock(return_value="https://example.test/ref.jpg")):
        await midjourney.handle_mj_reference_photo(msg, mock_state, mock_bot)

    mock_state.update_data.assert_awaited_once()
    call_data = mock_state.update_data.call_args[1]
    assert "reference_b64" in call_data
    assert call_data["reference_url"] == "https://example.test/ref.jpg"
    assert call_data["reference_b64"].startswith("data:image/jpeg;base64,")


# ── handle_imagine_prompt ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_imagine_prompt_success(_close_background_tasks) -> None:
    msg = make_message(text="/imagine a beautiful cat")
    msg.answer = AsyncMock()
    status_msg = SimpleNamespace(message_id=777)
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru", username="test", full_name="Test")
    mock_state = _fake_state(
        bot_type=MJBotType.MIDJOURNEY,
        speed=MJSpeed.FAST,
        credits=10,
        reference_b64=None,
    )
    msg.answer = AsyncMock(return_value=status_msg)

    mock_gen = SimpleNamespace(id=100, task_id=None)

    with patch("bot.handlers.midjourney.repo", AsyncMock(
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
    )):
        with patch("bot.handlers.midjourney.mj", AsyncMock(imagine=AsyncMock(return_value="task_abc_123"))):
            await midjourney.handle_imagine_prompt(msg, mock_state, AsyncMock(), mock_db_user, AsyncMock())

    mock_state.set_state.assert_awaited_once_with(MidjourneyFSM.generating)
    assert mock_state.update_data.await_args.kwargs["mj_status_message_id"] == 777
    assert len(_close_background_tasks) == 1


@pytest.mark.asyncio
async def test_initial_mj_image_polling_sends_clickable_action_buttons(monkeypatch) -> None:
    created = []

    def fake_create_task(coro):
        created.append(coro)
        return SimpleNamespace(cancel=MagicMock())

    class FakeSessionFactory:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_poll_until_done(task_id, check_fn, on_success, on_failure):
        await on_success("https://example.test/result.jpg")

    button = midjourney.MJButton(custom_id="MJ::JOB::upsample::1", label="U1")
    task_result = midjourney.MJTaskResult(
        task_id="task_buttons",
        status=midjourney.MJTaskStatus.SUCCESS,
        image_url="https://example.test/result.jpg",
        buttons=[button],
    )
    bot = AsyncMock()
    state = _fake_state()
    status_msg = AsyncMock()

    monkeypatch.setattr(midjourney.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(midjourney.polling, "poll_until_done", fake_poll_until_done)
    monkeypatch.setattr(midjourney.mj, "fetch_task", AsyncMock(return_value=task_result))
    monkeypatch.setattr(midjourney, "AsyncSessionLocal", lambda: FakeSessionFactory())
    monkeypatch.setattr(midjourney.repo, "finish_generation", AsyncMock(return_value=SimpleNamespace(id=100)))

    await midjourney._finish_initial_mj_image(
        task_id="task_buttons",
        gen_id=100,
        user_id=42,
        credits=10,
        chat_id=123456,
        caption="done",
        state=state,
        status_msg=status_msg,
        bot=bot,
    )
    await created[0]

    state.set_state.assert_awaited_with(MidjourneyFSM.viewing_result)
    assert state.update_data.await_args.kwargs["buttons"] == [
        {"custom_id": "MJ::JOB::upsample::1", "label": "U1", "emoji": ""}
    ]
    bot.send_photo.assert_awaited_once()
    assert bot.send_photo.await_args.kwargs["reply_markup"] is not None
    bot.send_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_imagine_prompt_prepends_reference_url() -> None:
    msg = make_message(text="a beautiful cat")
    msg.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru", username="test", full_name="Test")
    mock_state = _fake_state(
        bot_type=MJBotType.MIDJOURNEY,
        speed=MJSpeed.FAST,
        credits=10,
        reference_b64="data:image/jpeg;base64,abc",
        reference_url="https://example.test/ref.jpg",
    )

    mock_gen = SimpleNamespace(id=100, task_id=None)
    imagine_mock = AsyncMock(return_value="task_abc_123")

    with patch("bot.handlers.midjourney.repo", AsyncMock(
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=mock_gen),
        update_generation_task=AsyncMock(),
    )):
        with patch("bot.handlers.midjourney.mj", AsyncMock(imagine=imagine_mock)):
            with patch("bot.handlers.midjourney.polling", AsyncMock()):
                await midjourney.handle_imagine_prompt(msg, mock_state, AsyncMock(), mock_db_user, AsyncMock())

    assert imagine_mock.await_args.args[0] == "https://example.test/ref.jpg a beautiful cat"
    assert imagine_mock.await_args.kwargs["base64_array"] == ["data:image/jpeg;base64,abc"]
    assert imagine_mock.await_args.kwargs["reference_url"] == "https://example.test/ref.jpg"


@pytest.mark.asyncio
async def test_handle_imagine_prompt_insufficient_credits() -> None:
    msg = make_message(text="/imagine a cat")
    msg.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=5, language="ru")
    mock_state = _fake_state(credits=10)
    with patch("bot.handlers.midjourney.repo", AsyncMock(spend_credits=AsyncMock(return_value=False))):
        await midjourney.handle_imagine_prompt(msg, mock_state, AsyncMock(), mock_db_user, AsyncMock())
    msg.answer.assert_awaited_once()
    assert "недостаточно" in msg.answer.call_args[0][0].lower()


# ── mj_btn: action buttons ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_mj_action_invalid_index() -> None:
    call = make_callback(data="mj_btn:999")
    call.answer = AsyncMock()
    mock_state = _fake_state(task_id="task_abc", buttons=[{"custom_id": "1", "label": "U1", "emoji": "1️⃣", "clicked": False}])
    await midjourney.cb_mj_action(call, mock_state, AsyncMock(), SimpleNamespace(id=42), AsyncMock())
    call.answer.assert_awaited_once()


# ── mj:blend start ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_blend_start_insufficient_credits() -> None:
    call = make_callback(data="mj:blend")
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=5, language="ru")
    mock_cost = SimpleNamespace(credits=15, display_name="MJ Blend")
    with patch("bot.handlers.midjourney.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        await midjourney.cb_blend_start(call, AsyncMock(), AsyncMock(), mock_db_user)
    call.answer.assert_awaited_once()
    # answer("text", show_alert=True) → keyword arg
    assert call.answer.call_args[1].get("show_alert") is True


@pytest.mark.asyncio
async def test_cb_blend_start_sufficient() -> None:
    call = make_callback(data="mj:blend")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    mock_cost = SimpleNamespace(credits=12, display_name="MJ Blend")
    with patch("bot.handlers.midjourney.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        await midjourney.cb_blend_start(call, AsyncMock(), AsyncMock(), mock_db_user)
    call.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_blend_submit_stores_status_message_for_webhook_completion() -> None:
    call = make_callback(data="mj_blend:submit")
    call.answer = AsyncMock()
    status_msg = SimpleNamespace(message_id=888, edit_text=AsyncMock(), delete=AsyncMock())
    call.message.answer = AsyncMock(return_value=status_msg)
    mock_state = _fake_state(blend_images=["https://example.test/1.jpg", "https://example.test/2.jpg"], blend_credits=12)
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    mock_gen = SimpleNamespace(id=99)

    with (
        patch("bot.handlers.midjourney.repo", AsyncMock(
            spend_credits=AsyncMock(return_value=True),
            create_generation=AsyncMock(return_value=mock_gen),
            update_generation_task=AsyncMock(),
        )),
        patch("bot.handlers.midjourney.mj", AsyncMock(blend=AsyncMock(return_value="task_blend_1"), poll_mj_image=AsyncMock())),
    ):
        await midjourney.cb_blend_submit(call, mock_state, AsyncMock(), mock_db_user, AsyncMock())

    mock_state.set_state.assert_awaited_once_with(MidjourneyFSM.blend_generating)
    mock_state.clear.assert_not_awaited()
    assert mock_state.update_data.await_args.kwargs["mj_status_message_id"] == 888


# ── handle_blend_photo ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_blend_photo() -> None:
    import io
    msg = make_message(text="test")
    msg.photo = [MagicMock()]
    msg.photo[-1] = msg.photo[0]
    msg.photo[0].file_id = "photo_123"
    msg.answer = AsyncMock()

    mock_bot = AsyncMock()
    mock_file = SimpleNamespace(file_path="test.jpg")
    mock_bot.get_file = AsyncMock(return_value=mock_file)
    mock_bot.download_file = AsyncMock(return_value=io.BytesIO(b"\xff\xd8\xff\xe0test"))

    mock_state = _fake_state()
    mock_state.get_data = AsyncMock(return_value={"blend_images": [], "blend_credits": 12})
    mock_state.update_data = AsyncMock()

    await midjourney.handle_blend_photo(msg, mock_state, AsyncMock(), SimpleNamespace(id=42), mock_bot)
    mock_state.update_data.assert_awaited_once()


# ── mj:describe start ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_describe_start_success() -> None:
    call = make_callback(data="mj:describe")
    assert call.message is not None
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    mock_cost = SimpleNamespace(credits=5, display_name="MJ Describe")
    with patch("bot.handlers.midjourney.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        await midjourney.cb_describe_start(call, AsyncMock(), AsyncMock(), mock_db_user)
    assert "Describe" in call.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_describe_start_insufficient_credits() -> None:
    call = make_callback(data="mj:describe")
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=2)
    mock_cost = SimpleNamespace(credits=5, display_name="MJ Describe")
    with patch("bot.handlers.midjourney.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        await midjourney.cb_describe_start(call, AsyncMock(), AsyncMock(), mock_db_user)
    call.answer.assert_awaited_once()


# ── mj:video start ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_mj_video_start_success() -> None:
    call = make_callback(data="mj:video")
    assert call.message is not None
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=500, language="ru")
    mock_cost = SimpleNamespace(credits=15, display_name="MJ Video")
    with patch("bot.handlers.midjourney.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        await midjourney.cb_mj_video_start(call, AsyncMock(), AsyncMock(), mock_db_user)
    text = call.message.edit_text.call_args[0][0]
    assert "🎞️" in text


@pytest.mark.asyncio
async def test_cb_mj_video_start_insufficient_credits() -> None:
    call = make_callback(data="mj:video")
    call.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, credits=5, language="ru")
    mock_cost = SimpleNamespace(credits=15, display_name="MJ Video")
    with patch("bot.handlers.midjourney.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        await midjourney.cb_mj_video_start(call, AsyncMock(), AsyncMock(), mock_db_user)
    call.answer.assert_awaited_once()


# ── mj_vmot: video motion ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_video_motion() -> None:
    call = make_callback(data="mj_vmot:high")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_state = _fake_state()
    await midjourney.cb_video_motion(call, mock_state)
    mock_state.update_data.assert_awaited_once()
    mock_state.set_state.assert_called_with(MidjourneyFSM.video_prompt)


# ── mj_skip_prompt (video) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_video_skip_prompt() -> None:
    call = make_callback(data="mj_skip_prompt")
    call.answer = AsyncMock()
    mock_state = _fake_state()
    mock_state.get_data = AsyncMock(return_value={"video_credits": 15, "video_image_url": "https://img.test/1.png"})
    with patch("bot.handlers.midjourney._submit_mj_video", new_callable=AsyncMock) as mock_submit:
        await midjourney.cb_video_skip_prompt(call, mock_state, AsyncMock(), SimpleNamespace(id=42, credits=500, language="ru"), AsyncMock())
        mock_submit.assert_awaited_once()


# ── modal skip (smoke test) ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_modal_skip_smoke() -> None:
    """Smoke test: cb_modal_skip calls _submit_modal and answers the callback."""
    call = make_callback(data="mj_skip_prompt")
    call.answer = AsyncMock()
    mock_state = _fake_state()
    mock_state.get_data = AsyncMock(return_value={"modal_task_id": "task_modal_123", "task_id": "task_abc"})
    mock_bot = AsyncMock()

    with patch("bot.handlers.midjourney._submit_modal", new_callable=AsyncMock) as mock_submit:
        await midjourney.cb_modal_skip(call, mock_state, mock_bot)
        mock_submit.assert_awaited_once()

    call.answer.assert_awaited_once()


# ── handle_video_prompt (midjourney video) ────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_video_prompt_text() -> None:
    """Test that text message in video_prompt state triggers _submit_mj_video."""
    msg = make_message(text="gentle wind")
    msg.answer = AsyncMock()
    mock_state = _fake_state()
    mock_state.get_data = AsyncMock(return_value={"video_credits": 15, "video_image_url": "https://img.test/1.png"})
    mock_bot = AsyncMock()
    mock_session = AsyncMock()

    with patch("bot.handlers.midjourney._submit_mj_video", new_callable=AsyncMock) as mock_submit:
        await midjourney.handle_video_prompt(msg, mock_state, mock_session, SimpleNamespace(id=42, credits=500, language="ru"), mock_bot)
        mock_submit.assert_awaited_once()
