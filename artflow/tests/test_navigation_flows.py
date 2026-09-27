"""Behavior regressions: actual installed routers, real FSM, no external I/O."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import image_wizard_v2, video_gen
from bot.keyboards.models import VIDEO_CAPS
from bot.states import ImageGenFSM, VideoGenFSM
from db.models import GenerationType
from tests.factories import make_callback


@pytest.fixture
def state():
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=2))


@pytest.fixture
def costs(monkeypatch):
    items = [
        SimpleNamespace(
            model_key=key,
            display_name=key,
            credits=1,
            gen_type=GenerationType.video,
            is_active=True,
        )
        for key in VIDEO_CAPS
    ]
    monkeypatch.setattr(video_gen.repo, "get_all_model_costs", AsyncMock(return_value=items))

    async def resolve(_session, key, **kwargs):
        return next((item for item in items if item.model_key == key), None)

    monkeypatch.setattr(video_gen.repo, "resolve_video_model_cost", resolve)
    monkeypatch.setattr(video_gen.repo, "get_model_cost", resolve)
    return items


async def dispatch(data, state, **kwargs):
    call = make_callback(data=data)

    def copy_call(*, update):
        copied = make_callback(data=update["data"])
        copied.message = call.message
        copied.answer = call.answer
        return copied

    call.model_copy.side_effect = copy_call
    await video_gen.router.propagate_event(
        "callback_query",
        call,
        state=state,
        raw_state=await state.get_state(),
        session=AsyncMock(),
        db_user=SimpleNamespace(id=2, tg_id=2, credits=10000),
        **kwargs,
    )
    return call


def buttons(call):
    return call.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard


def back(call):
    return next(b.callback_data for row in buttons(call) for b in row if b.text.startswith("←"))


@pytest.mark.asyncio
async def test_scenario_selection_discards_previous_task(state, costs):
    await state.set_data(
        {
            "reference_video_url": "old.mp4",
            "motion_step": "prompt",
            "feed_force_reference": True,
            "model_key": "old",
        }
    )
    await dispatch("vid_wizard:scenario:text", state)
    assert (
        not {"reference_video_url", "motion_step", "feed_force_reference", "model_key"}
        & (await state.get_data()).keys()
    )


@pytest.mark.asyncio
async def test_advanced_entry_discards_previous_scenario(state, costs):
    await state.set_data({"wizard_mode": "video", "reference_video_url": "old.mp4"})
    call = await dispatch("vid_wizard:advanced", state)
    assert "wizard_mode" not in await state.get_data()
    assert back(call) == "menu:video"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("text", VideoGenFSM.params_select.state),
        ("image", VideoGenFSM.image_upload.state),
        ("video", VideoGenFSM.image_upload.state),
    ],
)
async def test_omni_model_respects_chosen_scenario(state, costs, scenario, expected):
    await dispatch(f"vid_wizard:scenario:{scenario}", state)
    await dispatch("vid_model:gemini-omni-video", state)
    assert (await state.get_state(), (await state.get_data()).get("mode")) == (expected, scenario)


@pytest.mark.asyncio
async def test_manual_mode_back_returns_to_manual_model_list(state, costs):
    await dispatch("vid_wizard:advanced", state)
    call = await dispatch("vid_model:gemini-omni-video", state)
    returned = await dispatch(back(call), state)
    assert "Все видео-модели" in returned.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_other_models_keeps_video_scenario_instead_of_omni_category(state, costs):
    call = await dispatch("vid_wizard:scenario:video", state)
    other = next(b.callback_data for row in buttons(call) for b in row if "другую модель" in b.text)
    call = await dispatch(other, state)
    assert "Переработать видео" in call.message.edit_text.await_args.args[0]
    assert back(call) == "vid_wizard:scenario:video"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,state_name",
    [
        ("gemini-omni-video", VideoGenFSM.image_upload.state),
        ("minimax-hailuo-3", VideoGenFSM.h3_reference_upload.state),
        ("bytedance/seedance-2-5", VideoGenFSM.seedance25_reference_upload.state),
    ],
)
async def test_params_back_restores_reference_collector_without_losing_media(
    state, costs, model, state_name
):
    from api.minimax_h3_adapter import PUBLIC_MODEL

    if model == "minimax-hailuo-3":
        model = PUBLIC_MODEL
    await state.set_state(VideoGenFSM.params_select)
    await state.set_data(
        {
            "model_key": model,
            "mode": "video",
            "wizard_scenario": "video",
            "wizard_review_enabled": True,
            "reference_video_url": "saved.mp4",
            "ref_file_ids": ["photo"],
            "duration": 5,
            "resolution": "720p",
        }
    )
    await dispatch("vpar_back", state)
    assert (await state.get_state(), (await state.get_data())["reference_video_url"]) == (
        state_name,
        "saved.mp4",
    )


@pytest.mark.asyncio
async def test_image_home_returns_to_model_first_entry(state, monkeypatch):
    from bot.handlers import image_models_first

    target = AsyncMock()
    monkeypatch.setattr(image_models_first, "open_image_models_first", target)
    await state.set_state(ImageGenFSM.image_upload)
    await image_wizard_v2.image_home(
        make_callback(), state, AsyncMock(), SimpleNamespace(credits=100)
    )
    target.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_library_repeat_clears_previous_feed_prompt(state, monkeypatch):
    from bot.handlers import marketplace

    await state.set_data({"feed_use_prompt": "wrong prompt", "prompt_multi_ref_file_ids": ["old"]})
    monkeypatch.setattr(
        marketplace, "get_prompt_by_id", AsyncMock(return_value=SimpleNamespace(title="New"))
    )
    monkeypatch.setattr(marketplace.repo, "get_all_model_costs", AsyncMock(return_value=[]))
    await marketplace.cb_prompt_use(
        make_callback(data="prompt_use:22"), AsyncMock(), SimpleNamespace(id=2), state
    )
    assert await state.get_data() == {"use_prompt_id": 22}


@pytest.mark.asyncio
async def test_photo_prompt_model_back_preserves_analysis(state, monkeypatch):
    from bot.handlers import photo_prompt

    await state.set_state(ImageGenFSM.photo_to_prompt)
    await state.set_data({"generated_prompt": "A red fox", "p2p_model_name": "test"})
    monkeypatch.setattr(photo_prompt.repo, "get_all_model_costs", AsyncMock(return_value=[]))
    monkeypatch.setattr(photo_prompt, "_resolve_active_session", AsyncMock(return_value=None))
    call = make_callback(data="p2p:model")
    await photo_prompt.cb_photo_prompt_model(
        call, state, AsyncMock(), SimpleNamespace(language="ru")
    )
    callback = back(call)
    await photo_prompt.router.propagate_event(
        "callback_query",
        make_callback(data=callback),
        state=state,
        raw_state=await state.get_state(),
        session=AsyncMock(),
        db_user=SimpleNamespace(id=2),
    )
    assert (await state.get_state(), (await state.get_data())["generated_prompt"]) == (
        ImageGenFSM.photo_to_prompt.state,
        "A red fox",
    )


@pytest.mark.asyncio
async def test_photo_prompt_cancel_opens_working_model_picker(state, monkeypatch):
    from bot.handlers import image_models_first, photo_prompt

    monkeypatch.setattr(photo_prompt, "_resolve_active_session", AsyncMock(return_value=None))
    target = AsyncMock()
    monkeypatch.setattr(image_models_first, "open_image_models_first", target)
    await photo_prompt.cb_cancel_prompt(make_callback(), state, AsyncMock(), SimpleNamespace(id=2))
    target.assert_awaited_once()


@pytest.mark.parametrize(
    "builder",
    ["_session_ratio_choices_kb", "_session_quality_choices_kb", "_session_count_choices_kb"],
)
def test_image_parameter_back_returns_to_settings(builder):
    from bot.handlers import image_gen

    image_session = SimpleNamespace(
        id=1, model="nano-banana-pro", mode="text", aspect_ratio="1:1", quality="2K", count=1
    )
    markup = getattr(image_gen, builder)(image_session)
    assert markup.inline_keyboard[-1][0].callback_data == "img_session:settings"


from bot.middlewares.navigation import PUBLIC_MENU_ENTRIES


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", sorted(PUBLIC_MENU_ENTRIES))
@pytest.mark.parametrize("previous", [ImageGenFSM.prompt_input, VideoGenFSM.prompt_input])
async def test_public_menu_ends_previous_input_flow(entry, previous):
    from aiogram import F, Router

    from bot.utils.dispatcher import create_dispatcher

    dp = create_dispatcher(MemoryStorage())
    route = Router()
    observed = []

    @route.callback_query(F.data == entry)
    async def screen(call, state):
        observed.append((await state.get_state(), await state.get_data()))

    dp.include_router(route)
    ctx = FSMContext(dp.storage, StorageKey(bot_id=1, chat_id=2, user_id=2))
    await ctx.set_state(previous)
    await ctx.set_data({"model_key": "abandoned", "review_prompt": "old"})
    await dp.propagate_event(
        "callback_query", make_callback(data=entry), state=ctx, raw_state=await ctx.get_state()
    )
    assert observed == [(None, {})]


@pytest.mark.asyncio
async def test_feed_repeat_back_to_models_preserves_source(state, costs):
    await state.set_state(VideoGenFSM.mode_select)
    await state.set_data(
        {
            "feed_force_reference": True,
            "feed_use_prompt": "hidden original",
            "source_feed_gen_id": 22,
            "model_key": "gemini-omni-video",
            "ref_file_ids": ["old"],
        }
    )
    await dispatch("vid_nav:models", state)
    assert await state.get_data() == {
        "feed_force_reference": True,
        "feed_use_prompt": "hidden original",
        "source_feed_gen_id": 22,
    }


@pytest.mark.asyncio
async def test_existing_photo_can_continue_after_params_back(state, costs):
    await state.set_state(VideoGenFSM.params_select)
    await state.set_data(
        {
            "model_key": "gemini-omni-video",
            "mode": "image",
            "ref_file_ids": ["saved"],
            "duration": 5,
        }
    )
    call = await dispatch("vpar_back", state)
    forward = next(b.callback_data for row in buttons(call) for b in row if b.text.startswith("✅"))
    await dispatch(forward, state)
    assert (await state.get_state(), (await state.get_data())["ref_file_ids"]) == (
        VideoGenFSM.params_select.state,
        ["saved"],
    )


@pytest.mark.asyncio
async def test_h3_photo_back_stays_in_photo_scenario(state, costs):
    from api.minimax_h3_adapter import PUBLIC_MODEL

    await state.set_state(VideoGenFSM.params_select)
    await state.set_data(
        {
            "model_key": PUBLIC_MODEL,
            "mode": "image",
            "wizard_scenario": "image",
            "ref_file_ids": ["saved"],
        }
    )
    call = await dispatch("vpar_back", state)
    assert await state.get_state() == VideoGenFSM.image_upload.state
    assert "h3ref:none" not in [b.callback_data for row in buttons(call) for b in row]


@pytest.mark.asyncio
async def test_photo_analysis_cancel_restores_unsaved_composer(state, monkeypatch):
    from bot.handlers import photo_prompt

    snapshot = {
        "model_key": "nano-banana-pro",
        "mode": "image",
        "ref_file_ids": ["my-photo"],
        "aspect_ratio": "9:16",
    }
    await state.set_state(ImageGenFSM.prompt_input)
    await state.set_data(snapshot)
    # An unrelated saved series must not be substituted for the open composer.
    monkeypatch.setattr(
        photo_prompt.repo,
        "get_active_image_session",
        AsyncMock(return_value=SimpleNamespace(id=999)),
    )
    user = SimpleNamespace(id=2)
    await photo_prompt.cb_photo_to_prompt(make_callback(), state, AsyncMock(), user)
    await photo_prompt.cb_cancel_prompt(make_callback(), state, AsyncMock(), user)
    assert (await state.get_state(), await state.get_data()) == (
        ImageGenFSM.prompt_input.state,
        snapshot,
    )


@pytest.mark.asyncio
async def test_late_midjourney_result_does_not_replace_music_state(state, monkeypatch):
    import main
    from api.midjourney_service import MJTaskResult, MJTaskStatus
    from bot.states import MusicFSM

    await state.set_state(MusicFSM.prompt_input)
    await state.set_data({"music_model_key": "suno/v5.5"})
    monkeypatch.setattr(main, "bot", AsyncMock())
    gen = SimpleNamespace(model="midjourney", prompt="art")
    result = MJTaskResult(
        task_id="old-task", status=MJTaskStatus.SUCCESS, image_url="https://example.test/image.jpg"
    )
    await main._finish_midjourney_image_generation(gen, 2, result, state_ctx=state)
    assert (await state.get_state(), await state.get_data()) == (
        MusicFSM.prompt_input.state,
        {"music_model_key": "suno/v5.5"},
    )


@pytest.mark.asyncio
async def test_midjourney_own_task_still_opens_result(state, monkeypatch):
    import main
    from api.midjourney_service import MJTaskResult, MJTaskStatus
    from bot.states import MidjourneyFSM

    await state.set_state(MidjourneyFSM.generating)
    await state.set_data({"pending_mj_task_id": "my-task"})
    monkeypatch.setattr(main, "bot", AsyncMock())
    result = MJTaskResult(
        task_id="my-task", status=MJTaskStatus.SUCCESS, image_url="https://example.test/image.jpg"
    )
    await main._finish_midjourney_image_generation(
        SimpleNamespace(model="midjourney", prompt="art"), 2, result, state_ctx=state
    )
    assert await state.get_state() == MidjourneyFSM.viewing_result.state


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "callback",
    ["vpar_dur:999", "vpar_dur:invalid", "vpar_res:8K", "vpar_ratio:99:1", "vpar_mode:wrong"],
)
async def test_old_parameter_button_cannot_corrupt_current_model(state, costs, callback):
    original = {
        "model_key": "gemini-omni-video",
        "mode": "video",
        "duration": 5,
        "resolution": "720p",
    }
    await state.set_state(VideoGenFSM.params_select)
    await state.set_data(original)
    call = await dispatch(callback, state)
    assert await state.get_data() == original
    assert call.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_editing_review_params_returns_to_review_with_prompt(state, costs):
    await state.set_state(VideoGenFSM.review)
    await state.set_data(
        {
            "model_key": "gemini-omni-video",
            "mode": "text",
            "duration": 5,
            "resolution": "720p",
            "review_prompt": "A red fox",
            "wizard_review_enabled": True,
        }
    )
    await dispatch("vid_review:params", state)
    await dispatch("vpar_next", state, bot=AsyncMock())
    assert (await state.get_state(), (await state.get_data())["review_prompt"]) == (
        VideoGenFSM.review.state,
        "A red fox",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("edit", ["params", "prompt"])
async def test_back_from_review_editor_restores_confirmation(state, costs, edit):
    await state.set_state(VideoGenFSM.review)
    await state.set_data(
        {
            "model_key": "gemini-omni-video",
            "mode": "text",
            "duration": 5,
            "resolution": "720p",
            "review_prompt": "A red fox",
            "wizard_review_enabled": True,
        }
    )
    call = await dispatch(f"vid_review:{edit}", state)
    await dispatch(back(call), state)
    assert await state.get_state() == VideoGenFSM.review.state


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/help", "/starshelp", "/assistant@TestBot"])
async def test_help_commands_end_abandoned_flow(command, state):
    from bot.middlewares.navigation import NavigationMiddleware
    from tests.factories import make_message

    await state.set_state(VideoGenFSM.prompt_input)
    await state.set_data({"model_key": "abandoned"})
    await NavigationMiddleware()(AsyncMock(), make_message(text=command), {"state": state})
    assert (await state.get_state(), await state.get_data()) == (None, {})


@pytest.mark.asyncio
async def test_stale_model_mode_is_rejected_before_handler(state):
    from bot.middlewares.navigation import NavigationMiddleware

    await state.set_state(VideoGenFSM.mode_select)
    await state.set_data({"model_key": "gemini-omni-video"})
    handler = AsyncMock()
    call = make_callback(data="vid_mode:image:another-model")
    await NavigationMiddleware()(handler, call, {"state": state})
    handler.assert_not_awaited()
    call.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_motion_video_step_back_returns_to_photo_step(state, costs):
    await state.set_state(VideoGenFSM.image_upload)
    await state.set_data(
        {
            "model_key": "kling-3.0/motion-control",
            "mode": "motion",
            "motion_step": "video_url",
            "image_file_id": "my-photo",
        }
    )
    call = await dispatch("vid_nav:back", state)
    assert (await state.get_state(), (await state.get_data())["motion_step"]) == (
        VideoGenFSM.image_upload.state,
        "person",
    )
    forward = next(b.callback_data for row in buttons(call) for b in row if b.text.startswith("✅"))
    await dispatch(forward, state)
    assert (await state.get_data())["motion_step"] == "video_url"


def test_topup_has_explicit_home_destination():
    from bot.keyboards.payment import topup_kb

    button = topup_kb([]).inline_keyboard[-1][0]
    assert (button.text, button.callback_data) == ("🏠 Главное меню", "menu:main")


@pytest.mark.asyncio
async def test_result_action_can_rebuild_missing_image_session(state, monkeypatch):
    from bot.handlers import image_gen

    created = SimpleNamespace(id=3)
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(image_gen.repo, "create_image_session", AsyncMock(return_value=created))
    result = await image_gen._image_session_for_result_action(
        make_callback(),
        AsyncMock(),
        state,
        SimpleNamespace(id=2),
        SimpleNamespace(id=1, model="nano-banana-pro", image_session_id=None),
    )
    assert result is created


@pytest.mark.asyncio
async def test_old_midjourney_result_button_does_not_charge_current_task(state, monkeypatch):
    from bot.handlers import midjourney
    from bot.keyboards.midjourney import mj_action_callback

    await state.set_state(
        __import__("bot.states", fromlist=["MidjourneyFSM"]).MidjourneyFSM.viewing_result
    )
    await state.set_data({"task_id": "new-task", "buttons": [{"custom_id": "new-action"}]})
    charge = AsyncMock()
    monkeypatch.setattr(midjourney.repo, "charge_image_generation", charge)
    call = make_callback(data=mj_action_callback(0, "old-task"))
    await midjourney.cb_mj_action(call, state, AsyncMock(), SimpleNamespace(id=2), AsyncMock())
    charge.assert_not_awaited()
    call.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_music_source_back_preserves_uploaded_audio(state):
    from bot.handlers import music_gen
    from bot.states import MusicFSM

    await state.set_state(MusicFSM.source_prompt_input)
    await state.set_data({"suno_source_url": "saved.mp3", "suno_source_operation": "cover"})
    call = make_callback(data="music:source_back")
    await music_gen.router.propagate_event(
        "callback_query", call, state=state, raw_state=await state.get_state()
    )
    assert (await state.get_state(), await state.get_data()) == (
        MusicFSM.prompt_input.state,
        {"suno_source_url": "saved.mp3", "suno_source_operation": None},
    )


def test_automatic_collectors_are_listed_for_image_and_video_scenarios():
    from api.minimax_h3_adapter import PUBLIC_MODEL
    from api.seedance25_adapter import MODEL_KEY
    from bot.handlers.video_wizard import supports_scenario

    assert all(
        supports_scenario(model, mode)
        for model in [PUBLIC_MODEL, MODEL_KEY]
        for mode in ["image", "video"]
    )


@pytest.mark.asyncio
async def test_old_image_settings_callback_does_not_change_video_workflow(state):
    from aiogram.dispatcher.event.bases import UNHANDLED

    await state.set_state(VideoGenFSM.prompt_input)
    original = {"model_key": "gemini-omni-video", "mode": "video"}
    await state.set_data(original)
    result = await image_wizard_v2.router.propagate_event(
        "callback_query",
        make_callback(data="img_v2:ratio"),
        state=state,
        raw_state=await state.get_state(),
    )
    assert result is UNHANDLED
    assert await state.get_data() == original


@pytest.mark.asyncio
async def test_motion_reference_continue_restores_prompt_stage(state, costs):
    await state.set_state(VideoGenFSM.image_upload)
    await state.set_data(
        {
            "model_key": "kling-3.0/motion-control",
            "mode": "motion",
            "motion_step": "video_url",
            "image_file_id": "saved-photo",
            "reference_video_url": "https://example.com/saved.mp4",
        }
    )
    await dispatch("vid_nav:params", state)
    await dispatch("vpar_next", state, bot=AsyncMock())
    data = await state.get_data()
    assert await state.get_state() == VideoGenFSM.prompt_input.state
    assert data["motion_step"] == "prompt"
    assert data["reference_video_url"] == "https://example.com/saved.mp4"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry,credit_key",
    [
        ("imagine", None),
        ("blend", "blend_credits"),
        ("describe", "describe_credits"),
        ("video", "video_credits"),
    ],
)
async def test_new_mj_wizard_rejects_previous_task_result(state, monkeypatch, entry, credit_key):
    from bot.handlers import midjourney
    from bot.states import MidjourneyFSM
    from bot.utils.midjourney_state import owns_midjourney_task

    await state.set_state(MidjourneyFSM.generating)
    await state.set_data({"pending_mj_task_id": "previous-task"})
    monkeypatch.setattr(
        midjourney.repo, "get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=7))
    )
    call = make_callback(data=f"mj:{entry}")
    if entry == "imagine":
        await midjourney.cb_imagine_start(call, state)
    else:
        handler = getattr(midjourney, f"cb_{'mj_video' if entry == 'video' else entry}_start")
        await handler(call, state, AsyncMock(), SimpleNamespace(id=2, credits=100))
    assert not await owns_midjourney_task(state, "previous-task")
    assert "pending_mj_task_id" not in await state.get_data()
    if credit_key:
        assert (await state.get_data())[credit_key] == 7
