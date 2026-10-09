"""Protected prompts must not escape through asynchronous Telegram deliveries."""
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import main
from bot.handlers import video_gen
from bot.ui.router import render_screen

SECRET = "private author prompt sentinel"
TASK_ID = "plain-miniapp-repeat-task"
PROTECTIONS = [
    pytest.param({"source_feed_gen_id": 77}, id="feed-lineage"),
    pytest.param({"input_params": {"hidden_prompt": True}}, id="hidden-dict"),
    pytest.param({"input_params": '{"hidden_prompt": true}'}, id="hidden-json"),
]


def _generation(**overrides):
    values = {
        "id": 88,
        "user_id": 42,
        "task_id": TASK_ID,
        "status": SimpleNamespace(value="processing"),
        "gen_type": main.GenerationType.image,
        "image_session_id": None,
        "model": "midjourney-imagine",
        "prompt": SECRET,
        "credits_spent": 3.5,
        "source_feed_gen_id": None,
        "action_type": "initial",
        "input_params": None,
    }
    return SimpleNamespace(**(values | overrides))


@pytest.fixture
def delivery(monkeypatch):
    bot = AsyncMock()
    session = AsyncMock()

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(main, "bot", bot)
    monkeypatch.setattr(main, "AsyncSessionLocal", session_context)
    monkeypatch.setattr(main, "_get_midjourney_context", AsyncMock(return_value=None))
    monkeypatch.setattr(main, "mirror_url", AsyncMock(side_effect=lambda url: url))
    monkeypatch.setattr(main.settings, "MIDJOURNEY_WEBHOOK_SECRET", "delivery-secret")
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", "delivery-secret")
    monkeypatch.setattr(main.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=42, tg_id=555111)))
    monkeypatch.setattr(main.repo, "finish_generation", AsyncMock(return_value=True))
    monkeypatch.setattr(main.repo, "fail_generation_and_refund", AsyncMock(return_value=(True, 3.5)))
    monkeypatch.setattr(main.repo, "get_generation_by_id", AsyncMock(return_value=None))

    def install(gen):
        monkeypatch.setattr(main.repo, "get_generation_by_task_id", AsyncMock(return_value=gen))
        return bot

    return install


async def _post(path, payload):
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(f"{path}?secret=delivery-secret", json=payload)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("protection", PROTECTIONS)
async def test_midjourney_plain_task_delivery_does_not_disclose_protected_prompt(delivery, protection):
    bot = delivery(_generation(**protection))

    await _post(main.settings.MIDJOURNEY_WEBHOOK_PATH, {
        "id": TASK_ID,
        "status": "SUCCESS",
        "imageUrl": "https://example.test/result.jpg",
    })

    assert len(bot.send_photo.await_args_list) == 1
    assert len(bot.send_document.await_args_list) == 1
    caption = bot.send_photo.await_args.kwargs["caption"]
    assert SECRET not in caption
    assert TASK_ID in caption
    assert SECRET not in str(bot.mock_calls)


@pytest.mark.asyncio
async def test_midjourney_ordinary_delivery_preserves_own_prompt_caption(delivery):
    bot = delivery(_generation(prompt="my ordinary portrait"))

    await _post(main.settings.MIDJOURNEY_WEBHOOK_PATH, {
        "id": TASK_ID,
        "status": "SUCCESS",
        "imageUrl": "https://example.test/result.jpg",
    })

    assert "my ordinary portrait" in bot.send_photo.await_args.kwargs["caption"]


@pytest.mark.asyncio
@pytest.mark.parametrize("protection", PROTECTIONS)
@pytest.mark.parametrize("provider", ["midjourney", "kie"])
async def test_protected_failure_delivery_never_echoes_provider_prompt(delivery, protection, provider):
    bot = delivery(_generation(**protection))
    error = f"Input rejected: {SECRET}"
    if provider == "midjourney":
        path = main.settings.MIDJOURNEY_WEBHOOK_PATH
        payload = {"id": TASK_ID, "status": "FAILURE", "failReason": error}
    else:
        path = main.settings.KIE_WEBHOOK_PATH
        payload = {"data": {"taskId": TASK_ID, "state": "failed", "failMsg": error}}

    await _post(path, payload)

    assert len(bot.send_message.await_args_list) == 1
    text = bot.send_message.await_args.args[1]
    assert SECRET not in text
    assert TASK_ID in text
    assert "возвращены" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["midjourney", "kie"])
async def test_ordinary_failure_delivery_keeps_provider_diagnostic(delivery, provider):
    bot = delivery(_generation())
    error = "Temporary provider capacity limit"
    if provider == "midjourney":
        path = main.settings.MIDJOURNEY_WEBHOOK_PATH
        payload = {"id": TASK_ID, "status": "FAILURE", "failReason": error}
    else:
        path = main.settings.KIE_WEBHOOK_PATH
        payload = {"data": {"taskId": TASK_ID, "state": "failed", "failMsg": error}}

    await _post(path, payload)

    assert error in bot.send_message.await_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("source_protection", PROTECTIONS)
async def test_owned_protected_source_cannot_reenable_prompt_actions(monkeypatch, source_protection):
    monkeypatch.setattr(main.repo, "get_generation_by_id", AsyncMock(return_value=_generation(**source_protection)))

    allowed = await main._prompt_actions_allowed_for_generation(
        AsyncMock(), _generation(source_feed_gen_id=88)
    )

    assert allowed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("input_params", [{"hidden_prompt": True}, '{"hidden_prompt": true}'])
@pytest.mark.parametrize("source_id", [None, 77])
async def test_hidden_metadata_cannot_reenable_prompt_actions(monkeypatch, input_params, source_id):
    monkeypatch.setattr(main.repo, "get_generation_by_id", AsyncMock(return_value=_generation()))

    allowed = await main._prompt_actions_allowed_for_generation(
        AsyncMock(), _generation(source_feed_gen_id=source_id, input_params=input_params)
    )

    assert allowed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("source_id", [None, 77])
async def test_ordinary_owned_generation_keeps_prompt_actions(monkeypatch, source_id):
    monkeypatch.setattr(main.repo, "get_generation_by_id", AsyncMock(return_value=_generation()))

    allowed = await main._prompt_actions_allowed_for_generation(
        AsyncMock(), _generation(source_feed_gen_id=source_id)
    )

    assert allowed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("source_protection", PROTECTIONS)
async def test_kie_delivery_keyboard_does_not_copy_nested_owned_source(delivery, monkeypatch, source_protection):
    bot = delivery(_generation(source_feed_gen_id=77, model="kling", gen_type=main.GenerationType.video))
    monkeypatch.setattr(main.repo, "get_generation_by_id", AsyncMock(return_value=_generation(**source_protection)))

    await _post(main.settings.KIE_WEBHOOK_PATH, {
        "data": {"taskId": TASK_ID, "state": "success", "resultUrls": ["https://example.test/result.mp4"]},
    })

    assert len(bot.send_video.await_args_list) == 1
    keyboard = bot.send_video.await_args.kwargs["reply_markup"].model_dump()
    assert SECRET not in str(keyboard)
    assert all(button.get("copy_text") is None for row in keyboard["inline_keyboard"] for button in row)


def _image_session():
    return SimpleNamespace(
        last_generation_id=88, aspect_ratio="1:1", count=1,
        reference_file_ids=None, reference_url=None, reference_file_id=None,
        model="nano-banana-pro", quality="1K",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source_protection", PROTECTIONS)
@pytest.mark.parametrize("allow_hint", [None, True])
async def test_active_session_keyboard_hides_nested_owned_source(monkeypatch, source_protection, allow_hint):
    active = _generation(source_feed_gen_id=77)
    source = _generation(**source_protection)
    monkeypatch.setattr(main.repo, "get_generation_by_id", AsyncMock(side_effect=[active, source]))

    screen = await render_screen(
        screen="image_active", session=AsyncMock(), db_user=SimpleNamespace(id=42, language="ru"),
        extra={"image_session": _image_session(), "prompt_actions_allowed": allow_hint},
    )

    assert SECRET not in str(screen.reply_markup.model_dump())
    assert all(button.copy_text is None for row in screen.reply_markup.inline_keyboard for button in row)


@pytest.mark.asyncio
@pytest.mark.parametrize("input_params", [{"hidden_prompt": True}, '{"hidden_prompt": true}'])
@pytest.mark.parametrize("source_id", [None, 77])
@pytest.mark.parametrize("allow_hint", [None, True])
async def test_active_session_keyboard_hides_metadata_protected_prompt(monkeypatch, input_params, source_id, allow_hint):
    active = _generation(source_feed_gen_id=source_id, input_params=input_params)
    monkeypatch.setattr(main.repo, "get_generation_by_id", AsyncMock(return_value=_generation()))

    screen = await render_screen(
        screen="image_active", session=AsyncMock(), db_user=SimpleNamespace(id=42, language="ru"),
        extra={"image_session": _image_session(), "active_generation": active, "prompt_actions_allowed": allow_hint},
    )

    assert SECRET not in str(screen.reply_markup.model_dump())


@pytest.mark.asyncio
@pytest.mark.parametrize("source_id", [None, 77])
async def test_active_session_keyboard_preserves_ordinary_owned_prompt(monkeypatch, source_id):
    active = _generation(source_feed_gen_id=source_id, prompt="my ordinary portrait")
    monkeypatch.setattr(main.repo, "get_generation_by_id", AsyncMock(return_value=_generation()))

    screen = await render_screen(
        screen="image_active", session=AsyncMock(), db_user=SimpleNamespace(id=42, language="ru"),
        extra={"image_session": _image_session(), "active_generation": active},
    )

    copied = [button.copy_text.text for row in screen.reply_markup.inline_keyboard for button in row if button.copy_text]
    assert copied == ["my ordinary portrait"]


@pytest.fixture
def video_failure_callback(monkeypatch):
    async def launch(flow, *, source_feed_gen_id=None, protection=None):
        current = _generation(id=99, model="kling-3.0/video", **(protection or {}))
        previous = _generation(model="kling-3.0/video", source_feed_gen_id=source_feed_gen_id)
        source = _generation(id=77, user_id=7, result_url="https://example.test/source.mp4", result_urls=None)
        generations = {77: source, 88: previous, 99: current}
        repo = SimpleNamespace(
            get_generation_by_id=AsyncMock(side_effect=lambda _session, gen_id: generations.get(gen_id)),
            get_public_feed_generation=AsyncMock(return_value=source),
            resolve_video_model_cost=AsyncMock(return_value=SimpleNamespace(credits=4, display_name="Video")),
            spend_credits=AsyncMock(return_value=True),
            create_generation=AsyncMock(return_value=current),
            update_generation_task=AsyncMock(),
            fail_generation_and_refund=AsyncMock(return_value=(True, 4)),
        )
        state = AsyncMock()
        data = {"model_key": "kling-3.0/video", "mode": "text", "duration": 5, "aspect_ratio": "16:9", "resolution": "1080p"}
        state.get_data.return_value = data
        message = AsyncMock()
        status = AsyncMock()
        message.answer.return_value = status
        polling = MagicMock()

        @asynccontextmanager
        async def session_context():
            yield AsyncMock()

        monkeypatch.setattr(video_gen, "repo", repo)
        monkeypatch.setattr(video_gen, "AsyncSessionLocal", session_context)
        monkeypatch.setattr(video_gen, "_video_reference_image_url", AsyncMock(return_value=None))
        monkeypatch.setattr(video_gen, "_video_repeat_params_for_generation", AsyncMock(return_value=data))
        monkeypatch.setattr("bot.handlers.genjutsu_replace.restore_result", AsyncMock(return_value=False))
        monkeypatch.setattr(video_gen, "_start_video_polling", polling)
        monkeypatch.setattr(video_gen, "video_service", SimpleNamespace(
            generate_video=AsyncMock(return_value=SimpleNamespace(task_id=TASK_ID, provider="direct", uses_webhook=False)),
            get_poll_fn=MagicMock(),
        ))
        if flow == "launch":
            assert await video_gen._launch_video_generation_from_state(
                source_message=message, state=state, session=AsyncMock(), db_user=SimpleNamespace(id=42),
                bot=AsyncMock(), prompt=SECRET, source_feed_gen_id=source_feed_gen_id,
                hidden_feed_prompt=bool(source_feed_gen_id),
            ) is True
        else:
            await video_gen.cb_regen_video(
                SimpleNamespace(data="regen:video:88", message=message, answer=AsyncMock()),
                AsyncMock(), state, SimpleNamespace(id=42), AsyncMock(),
            )
        assert polling.call_count == 1
        status.edit_text.reset_mock()
        return SimpleNamespace(callback=polling.call_args.args[3], current=current, status=status, repo=repo)

    return launch


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["launch", "regen"])
@pytest.mark.parametrize("source_id,protection", [
    pytest.param(77, {}, id="closure-feed-lineage"),
    pytest.param(None, {"source_feed_gen_id": 77}, id="current-feed-lineage"),
    pytest.param(None, {"input_params": {"hidden_prompt": True}}, id="current-hidden-dict"),
    pytest.param(None, {"input_params": '{"hidden_prompt": true}'}, id="current-hidden-json"),
])
async def test_video_poll_failure_masks_protected_prompt(video_failure_callback, flow, source_id, protection):
    pending = await video_failure_callback(flow, source_feed_gen_id=source_id, protection=protection)
    error = f"Input rejected: {SECRET}"

    await pending.callback(error)

    text = pending.status.edit_text.await_args.args[0]
    assert SECRET not in text
    assert TASK_ID in text
    assert "возвращены" in text
    assert pending.repo.fail_generation_and_refund.await_args.args[1:] == (99, error)


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["launch", "regen"])
async def test_video_poll_failure_preserves_escaped_ordinary_diagnostic(video_failure_callback, flow):
    pending = await video_failure_callback(flow)

    await pending.callback("unsupported <codec> & format")

    text = pending.status.edit_text.await_args.args[0]
    assert "unsupported &lt;codec&gt; &amp; format" in text
    assert TASK_ID in text


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["launch", "regen"])
@pytest.mark.parametrize("status", ["done", "failed"])
async def test_video_poll_failure_keeps_terminal_generation_guard(video_failure_callback, flow, status):
    pending = await video_failure_callback(flow, protection={"input_params": {"hidden_prompt": True}})
    pending.current.status = SimpleNamespace(value=status)

    await pending.callback(SECRET)

    pending.repo.fail_generation_and_refund.assert_not_awaited()
    pending.status.edit_text.assert_not_awaited()
