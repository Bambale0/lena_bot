"""Feed entrypoints must offer and collect provider-compatible public-media edits."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import (
    feed,
    gemini_omni_references,
    marketplace,
    seedance25_references,
    video_gen,
    video_navigation,
)
from bot.handlers import (
    repeat_reference_marketplace as refs,
)
from bot.keyboards.models import IMAGE_CAPS, VIDEO_CAPS
from bot.keyboards.prompts import prompt_use_model_kb
from bot.services import video_reference_support
from bot.states import PromptUseFSM, VideoGenFSM
from core.feed_remix_prompt import supports_feed_source_media
from db.models import GenerationType
from tests.factories import make_callback

SOURCE_VIDEO = "https://example.test/public-source.mp4"
SEEDANCE = "bytedance/seedance-2-5"
OMNI = "gemini-omni-video"


@pytest.fixture
def state():
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=2))


def callbacks(markup):
    return {button.callback_data for row in markup.inline_keyboard for button in row}


def costs(keys, gen_type):
    return [SimpleNamespace(model_key=key, gen_type=gen_type, credits=1,
                            display_name=key, is_active=True) for key in keys]


async def enter_feed(monkeypatch, state, gen_type, model_costs):
    source = SimpleNamespace(id=77, user_id=99, prompt="private author prompt", model=SEEDANCE,
                             gen_type=gen_type, result_url=SOURCE_VIDEO, result_urls=None)
    monkeypatch.setattr(feed.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr(feed.repo, "get_all_model_costs", AsyncMock(return_value=model_costs))
    call = make_callback(data="feed:use:77")
    await feed.cb_feed_use(call, AsyncMock(), SimpleNamespace(id=2), state)
    return call


@pytest.mark.asyncio
async def test_video_feed_entry_and_back_only_offer_source_video_capable_models(monkeypatch, state):
    items = costs(VIDEO_CAPS, GenerationType.video)
    call = await enter_feed(monkeypatch, state, GenerationType.video, items)
    offered = callbacks(call.message.answer.await_args.kwargs["reply_markup"])
    expected = {f"vid_model:{key}" for key, caps in VIDEO_CAPS.items()
                if supports_feed_source_media(caps, "video")}
    assert {value for value in offered if value.startswith("vid_model:")} == expected
    assert f"vid_model:{SEEDANCE}" in offered and f"vid_model:{OMNI}" in offered
    await state.update_data(model_key=OMNI, mode="video")
    await video_navigation.back_to_models(call, state, AsyncMock())
    assert callbacks(call.message.edit_text.await_args.kwargs["reply_markup"]) == offered
    assert (await state.get_data())["feed_use_source_video_url"] == SOURCE_VIDEO


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [SEEDANCE, OMNI, "bytedance/seedance-2"])
async def test_video_feed_picker_upload_and_done_keep_supported_mode(monkeypatch, state, model):
    items = costs(VIDEO_CAPS, GenerationType.video)
    await enter_feed(monkeypatch, state, GenerationType.video, items)
    model_cost = next(item for item in items if item.model_key == model)
    monkeypatch.setattr(video_gen.repo, "resolve_video_model_cost", AsyncMock(return_value=model_cost))
    monkeypatch.setattr(video_gen.repo, "get_model_cost", AsyncMock(return_value=model_cost))
    call = make_callback(data=f"vid_model:{model}")
    await video_gen.router.propagate_event(
        "callback_query", call, state=state, raw_state=await state.get_state(),
        session=AsyncMock(), db_user=SimpleNamespace(id=2, credits=1000),
    )
    data = await state.get_data()
    assert data["reference_video_url"] == SOURCE_VIDEO
    assert data["mode"] in VIDEO_CAPS[model]["modes"]
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="user-photo", file_size=100)], answer=AsyncMock())
    if model == SEEDANCE:
        assert await state.get_state() == VideoGenFSM.seedance25_reference_upload.state
        await seedance25_references.add_seedance25_photo(message, state)
        await seedance25_references.finish_seedance25_refs(call, state)
    elif model == OMNI:
        await gemini_omni_references.upload_gemini_omni_photo(message, state)
        await gemini_omni_references.finish_gemini_omni_media(call, state, AsyncMock())
    else:
        await video_gen.handle_image_upload(message, state, AsyncMock())
    assert await state.get_state() == VideoGenFSM.params_select.state
    data = await state.get_data()
    assert data["ref_file_ids"] == ["user-photo"]
    assert data["reference_video_url"] == SOURCE_VIDEO
    assert data["mode"] in VIDEO_CAPS[model]["modes"]
    assert data["mode"] != "image"


@pytest.mark.asyncio
async def test_forged_incompatible_video_model_is_rejected_before_picker_state_changes(monkeypatch, state):
    await enter_feed(monkeypatch, state, GenerationType.video, costs(VIDEO_CAPS, GenerationType.video))
    resolve = AsyncMock(return_value=SimpleNamespace(credits=1, display_name="Veo"))
    monkeypatch.setattr(video_gen, "_resolve_video_model_cost", resolve)
    call = make_callback(data="vid_model:veo3_fast")
    await video_gen.cb_video_model(call, AsyncMock(), state, SimpleNamespace(credits=1000))
    assert await state.get_state() == VideoGenFSM.model_select.state
    assert "model_key" not in await state.get_data()
    resolve.assert_not_awaited()
    assert call.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_image_feed_entry_reserves_source_slot_through_collection_and_submission(monkeypatch, state):
    monkeypatch.setitem(IMAGE_CAPS, "test/single", {"modes": ["image"], "max_refs": 1})
    monkeypatch.setitem(IMAGE_CAPS, "test/two", {"modes": ["image"], "max_refs": 2})
    items = costs(["test/single", "test/two"], GenerationType.image)
    entry = await enter_feed(monkeypatch, state, GenerationType.image, items)
    offered = callbacks(entry.message.answer.await_args.kwargs["reply_markup"])
    assert "prompt_pick_model:77:test/single" not in offered
    assert "prompt_pick_model:77:test/two" in offered
    picker = make_callback(data="prompt_pick_model:77:test/two")
    await marketplace.cb_prompt_pick_model(picker, state)
    assert (await state.get_data())["prompt_multi_ref_max"] == 1
    monkeypatch.setattr(refs.image_gen, "_supports_img2img", lambda key: True)
    legacy = AsyncMock()
    monkeypatch.setattr(marketplace, "fsm_prompt_use_reference", legacy)
    user = SimpleNamespace(id=2, credits=1000)
    for file_id in ["first", "excess"]:
        message = SimpleNamespace(photo=[SimpleNamespace(file_id=file_id, file_size=100)], answer=AsyncMock())
        await refs._collect_prompt_reference(message, AsyncMock(), user, state, AsyncMock())
    assert (await state.get_data())["prompt_multi_ref_file_ids"] == ["first"]
    legacy.assert_not_awaited()
    monkeypatch.setattr(refs, "mirror_telegram_file", AsyncMock(return_value="https://example.test/user.jpg"))
    monkeypatch.setattr(refs.repo, "resolve_image_model_cost", AsyncMock(return_value=items[1]))
    monkeypatch.setattr(refs.repo, "create_image_session", AsyncMock(return_value=SimpleNamespace(id=123)))
    launch = AsyncMock(return_value=True)
    monkeypatch.setattr(refs.image_gen, "_launch_session_generation", launch)
    await refs._run(picker, AsyncMock(), user, state, AsyncMock())
    assert launch.await_args.kwargs["reference_url"] == ["https://example.test/user.jpg"]
    assert launch.await_args.kwargs["source_feed_gen_id"] == 77


@pytest.mark.asyncio
async def test_feed_forged_single_slot_model_rejected_but_ordinary_marketplace_unchanged(monkeypatch, state):
    monkeypatch.setitem(IMAGE_CAPS, "test/single", {"modes": ["image"], "max_refs": 1})
    items = costs(["test/single"], GenerationType.image)
    assert "prompt_pick_model:77:test/single" in callbacks(prompt_use_model_kb(77, items))
    await state.update_data(feed_use_prompt="hidden", feed_use_gen_id=77)
    await state.set_state(PromptUseFSM.model_select)
    call = make_callback(data="prompt_pick_model:77:test/single")
    await marketplace.cb_prompt_pick_model(call, state)
    assert await state.get_state() == PromptUseFSM.model_select.state
    assert "use_model_key" not in await state.get_data()
    await state.clear()
    await marketplace.cb_prompt_pick_model(call, state)
    assert (await state.get_data())["prompt_multi_ref_max"] == 1
    assert await state.get_state() == PromptUseFSM.reference_upload.state


@pytest.mark.asyncio
async def test_seedance_video_reference_adapter_preserves_personalization_images(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(task_id="fake", uses_webhook=True))
    monkeypatch.setattr(video_reference_support, "create_seedance_task", create)
    await video_reference_support._generate_video_with_references(
        video_reference_support.VideoModel.SEEDANCE_2, "safe public-media edit",
        image_url=["https://example.test/user.jpg"], reference_video_url=SOURCE_VIDEO,
    )
    assert create.await_args.kwargs["reference_image_urls"] == ["https://example.test/user.jpg"]


@pytest.mark.asyncio
async def test_feed_image_model_switch_respects_source_and_uploaded_slots(monkeypatch, state):
    for key, limit in [("test/one", 1), ("test/two", 2), ("test/three", 3)]:
        monkeypatch.setitem(IMAGE_CAPS, key, {"modes": ["image"], "max_refs": limit})
    items = costs(["test/one", "test/two", "test/three"], GenerationType.image)
    monkeypatch.setattr(refs.image_gen, "_supports_img2img", lambda key: True)
    monkeypatch.setattr(refs.repo, "get_all_model_costs", AsyncMock(return_value=items))
    monkeypatch.setattr(refs.repo, "get_model_cost", AsyncMock(return_value=items[1]))
    await state.update_data(feed_use_prompt="hidden", feed_use_gen_id=77,
                            use_model_key="test/three", prompt_multi_ref_file_ids=["one", "two"])
    call = make_callback(data="prompt_multi_ref:model_menu")
    await refs._model_menu(call, AsyncMock(), state)
    offered = callbacks(call.message.answer.await_args.kwargs["reply_markup"])
    assert "pmr:m:test/three" in offered
    assert "pmr:m:test/two" not in offered and "pmr:m:test/one" not in offered
    call.data = "pmr:m:test/two"
    await refs._set_model(call, AsyncMock(), state)
    assert (await state.get_data())["use_model_key"] == "test/three"
    assert call.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_feed_overfull_stale_reference_state_never_uploads_or_launches(monkeypatch, state):
    monkeypatch.setitem(IMAGE_CAPS, "test/two", {"modes": ["image"], "max_refs": 2})
    await state.update_data(feed_use_prompt="hidden", feed_use_gen_id=77,
                            use_model_key="test/two", prompt_multi_ref_file_ids=["one", "two"])
    mirror = AsyncMock()
    launch = AsyncMock()
    monkeypatch.setattr(refs, "mirror_telegram_file", mirror)
    monkeypatch.setattr(refs.image_gen, "_launch_session_generation", launch)
    call = make_callback(data="prompt_multi_ref:run")
    await refs._run(call, AsyncMock(), SimpleNamespace(id=2), state, AsyncMock())
    mirror.assert_not_awaited()
    launch.assert_not_awaited()
    assert (await state.get_data())["prompt_multi_ref_file_ids"] == ["one", "two"]
    assert call.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_ordinary_marketplace_still_collects_full_model_capacity(monkeypatch, state):
    monkeypatch.setitem(IMAGE_CAPS, "test/two", {"modes": ["image"], "max_refs": 2})
    monkeypatch.setattr(refs.image_gen, "_supports_img2img", lambda key: True)
    await state.update_data(use_prompt_id=77, use_model_key="test/two")
    for file_id in ["one", "two", "excess"]:
        message = SimpleNamespace(photo=[SimpleNamespace(file_id=file_id, file_size=100)], answer=AsyncMock())
        await refs._collect_prompt_reference(message, AsyncMock(), SimpleNamespace(id=2), state, AsyncMock())
    assert (await state.get_data())["prompt_multi_ref_file_ids"] == ["one", "two"]
    assert (await state.get_data())["prompt_multi_ref_max"] == 2


@pytest.mark.asyncio
async def test_gemini_feed_source_occupies_quota_and_requires_personal_photo(monkeypatch, state):
    await state.update_data(feed_force_reference=True, feed_use_source_video_url=SOURCE_VIDEO,
                            reference_video_url=SOURCE_VIDEO, mode="video", model_key=OMNI)
    call = make_callback(data="omni_media:done")
    await gemini_omni_references.finish_gemini_omni_media(call, state, AsyncMock())
    assert call.answer.await_args.kwargs["show_alert"] is True
    for number in range(6):
        message = SimpleNamespace(photo=[SimpleNamespace(file_id=f"image-{number}", file_size=100)], answer=AsyncMock())
        await gemini_omni_references.upload_gemini_omni_photo(message, state)
    data = await state.get_data()
    assert len(data["ref_file_ids"]) == 5
    assert data["reference_video_url"] == SOURCE_VIDEO
    assert "Квота" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_seedance_feed_clear_preserves_public_video_and_rejects_second_video(state):
    await state.update_data(feed_force_reference=True, feed_use_source_video_url=SOURCE_VIDEO,
                            reference_video_url=SOURCE_VIDEO, ref_file_ids=["one"])
    call = make_callback(data="s25ref:clear")
    await seedance25_references.clear_seedance25_refs(call, state)
    data = await state.get_data()
    assert data["reference_video_url"] == SOURCE_VIDEO
    assert data["ref_file_ids"] == []
    message = SimpleNamespace(answer=AsyncMock())
    await seedance25_references.add_seedance25_video(message, state, AsyncMock())
    assert (await state.get_data())["reference_video_url"] == SOURCE_VIDEO
    assert "уже взято из ленты" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_video_catalog_exposes_shared_source_video_photo_capacity(monkeypatch):
    from api import miniapp_routes
    from core.gemini_omni import validate_gemini_omni_media_slots

    monkeypatch.setattr(miniapp_routes.repo, "get_all_model_costs", AsyncMock(return_value=costs([OMNI, SEEDANCE], GenerationType.video)))
    monkeypatch.setattr(miniapp_routes, "_video_model_rate_info", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(miniapp_routes, "_resolve_video_price_table", AsyncMock(return_value={}))
    models = {item.key: item for item in await miniapp_routes.list_video_models(AsyncMock(), SimpleNamespace(id=2))}
    assert models[OMNI].max_refs == 7
    assert models[OMNI].max_refs_with_video == 5
    assert models[SEEDANCE].max_refs_with_video is None
    validate_gemini_omni_media_slots(image_count=models[OMNI].max_refs_with_video, video_count=1)
    with pytest.raises(ValueError, match="media quota"):
        validate_gemini_omni_media_slots(image_count=models[OMNI].max_refs_with_video + 1, video_count=1)
