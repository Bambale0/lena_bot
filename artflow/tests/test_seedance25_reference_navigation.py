"""Reproduce old Seedance 2.5 Back buttons against installed aiogram routers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from api.seedance25_adapter import MODEL_KEY
from bot.handlers import video_gen
from bot.states import VideoGenFSM
from db.models import GenerationType
from tests.factories import make_callback


@pytest.fixture
def state():
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=2))


@pytest.fixture
def provider(monkeypatch):
    costs = [
        SimpleNamespace(
            model_key=key, credits=2, display_name=key,
            gen_type=GenerationType.video, is_active=True,
        )
        for key in video_gen.VIDEO_CAPS
    ]
    lookup = {cost.model_key: cost for cost in costs}
    monkeypatch.setattr(video_gen.repo, "get_all_model_costs", AsyncMock(return_value=costs))
    monkeypatch.setattr(
        video_gen.repo, "resolve_video_model_cost",
        AsyncMock(side_effect=lambda session, key, **kwargs: lookup.get(key)),
    )
    monkeypatch.setattr(
        video_gen.repo, "get_model_cost",
        AsyncMock(side_effect=lambda session, key, **kwargs: lookup.get(key)),
    )
    charge = AsyncMock()
    post = AsyncMock()
    monkeypatch.setattr(video_gen.repo, "spend_credits", charge)
    monkeypatch.setattr(video_gen.video_service, "generate_video", post)
    return charge, post


async def dispatch(data, state):
    call = make_callback(data=data)
    def copy_call(*, update):
        copied = make_callback(data=update["data"])
        copied.message = call.message
        copied.answer = call.answer
        return copied
    call.model_copy.side_effect = copy_call
    await video_gen.router.propagate_event(
        "callback_query", call,
        state=state, raw_state=await state.get_state(),
        session=AsyncMock(),
        db_user=SimpleNamespace(id=2, tg_id=2, credits=10000),
        bot=AsyncMock(),
    )
    return call


def callbacks(call):
    return {
        button.callback_data
        for row in call.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["vid_wizard:advanced", "vid_wizard:scenario:video"])
async def test_back_from_auto_seedance_refs_returns_to_model_picker_not_legacy_modes(
    state, provider, entry,
):
    await dispatch(entry, state)
    collection = await dispatch(f"vid_model:{MODEL_KEY}", state)
    assert await state.get_state() == VideoGenFSM.seedance25_reference_upload.state
    assert "s25ref:done" in callbacks(collection)
    assert "vid_nav:models" in callbacks(collection), "Back must target model list directly"

    returned = await dispatch("vid_nav:models", state)
    assert await state.get_state() == VideoGenFSM.model_select.state
    text = returned.message.edit_text.await_args.args[0]
    assert "Выбери режим видео" not in text
    if entry == "vid_wizard:advanced":
        assert "Все видео-модели" in text
    else:
        assert "Что выбрать" in text
    assert not any(value.startswith("vid_mode:") for value in callbacks(returned))
    charge, post = provider
    charge.assert_not_awaited()
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_seedance_back_button_in_old_telegram_messages_is_safe(state, provider):
    await dispatch("vid_wizard:advanced", state)
    await dispatch(f"vid_model:{MODEL_KEY}", state)
    returned = await dispatch("vid_nav:back", state)
    assert await state.get_state() == VideoGenFSM.model_select.state
    assert "Все видео-модели" in returned.message.edit_text.await_args.args[0]
    assert not any(value.startswith("vid_mode:") for value in callbacks(returned))
    charge, post = provider
    charge.assert_not_awaited()
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_params_back_keeps_user_refs_and_next_back_exits_to_models(state, provider):
    await dispatch("vid_wizard:advanced", state)
    await dispatch(f"vid_model:{MODEL_KEY}", state)
    await state.update_data(ref_file_ids=["own-front", "own-profile"], image_file_id="own-front")
    await dispatch("s25ref:done", state)
    assert await state.get_state() == VideoGenFSM.params_select.state

    returned = await dispatch("vpar_back", state)
    assert await state.get_state() == VideoGenFSM.seedance25_reference_upload.state
    assert "2/30" in returned.message.edit_text.await_args.args[0]
    assert (await state.get_data())["ref_file_ids"] == ["own-front", "own-profile"]

    returned = await dispatch("vid_nav:back", state)
    assert await state.get_state() == VideoGenFSM.model_select.state
    assert "Все видео-модели" in returned.message.edit_text.await_args.args[0]
    charge, post = provider
    charge.assert_not_awaited()
    post.assert_not_awaited()


def test_inline_checkout_back_also_targets_model_picker():
    from bot.handlers import seedance25_references as refs
    plan = SimpleNamespace(key="100", price_rub=100)
    markup = refs._checkout_kb(plan)
    assert any(
        button.text.startswith("←") and button.callback_data == "vid_nav:models"
        for row in markup.inline_keyboard for button in row
    )

@pytest.mark.asyncio
async def test_old_checkout_back_with_stale_model_does_not_open_mode_picker(state, provider):
    await dispatch("vid_wizard:advanced", state)
    await state.update_data(model_key=MODEL_KEY, mode="text")
    returned = await dispatch("vid_nav:back", state)
    assert await state.get_state() == VideoGenFSM.model_select.state
    assert "Все видео-модели" in returned.message.edit_text.await_args.args[0]
    charge, post = provider
    charge.assert_not_awaited()
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_back_from_feed_ref_collector_preserves_feed_context(state, provider):
    # The automatic multimodal reference collector is also used for author repeats.
    await state.set_state(VideoGenFSM.seedance25_reference_upload)
    await state.set_data({
        "model_key": MODEL_KEY,
        "feed_force_reference": True,
        "feed_use_source_video_url": "https://example.test/author.mp4",
        "feed_use_model": MODEL_KEY,
        "source_feed_gen_id": 1234,
        "parent_generation_id": 1235,
        "video_model_menu": "vid_wizard:advanced",
        "ref_file_ids": ["my-face.jpg"],
    })
    returned = await dispatch("vid_nav:back", state)
    assert await state.get_state() == VideoGenFSM.model_select.state
    data = await state.get_data()
    assert data["feed_force_reference"] is True
    assert data["feed_use_source_video_url"] == "https://example.test/author.mp4"
    assert data["source_feed_gen_id"] == 1234
    assert data["parent_generation_id"] == 1235
    assert "Повторить видео" in returned.message.edit_text.await_args.args[0]
    assert not any(value.startswith("vid_mode:") for value in callbacks(returned))
    charge, post = provider
    charge.assert_not_awaited()
    post.assert_not_awaited()
