"""Exercise the installed Telegram router with real FSM and external I/O mocked."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import video_gen
from core.config import settings
from tests import test_genjutsu_face_clothing as provider_fixtures
from tests.factories import make_callback, make_message


@pytest.fixture
def provider(monkeypatch):
    return provider_fixtures.provider.__wrapped__(monkeypatch)


@pytest.fixture
def state():
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=2))


@pytest.fixture
def io(monkeypatch):
    monkeypatch.setattr(settings, "KIE_AI_KEY", "test-key")
    cost = SimpleNamespace(
        model_key="bytedance/seedance-2-5", credits=3, is_active=True, display_name="Seedance 2.5"
    )
    monkeypatch.setattr(video_gen.repo, "get_all_model_costs", AsyncMock(return_value=[cost]))
    monkeypatch.setattr(video_gen.repo, "get_model_cost", AsyncMock(return_value=cost))
    monkeypatch.setattr(video_gen.repo, "resolve_video_model_cost", AsyncMock(return_value=cost))
    monkeypatch.setattr(
        video_gen,
        "mirror_telegram_file",
        AsyncMock(side_effect=lambda bot, file_id, **kw: f"https://example.test/{file_id}"),
    )
    monkeypatch.setattr(video_gen, "seedance25_edit_billing_duration", AsyncMock(return_value=7))
    return SimpleNamespace(
        user=SimpleNamespace(id=2, credits=1000, tg_id=2), session=AsyncMock(), bot=AsyncMock()
    )


async def callback(data, state, io):
    call = make_callback(data=data)
    await video_gen.router.propagate_event(
        "callback_query",
        call,
        state=state,
        raw_state=await state.get_state(),
        session=io.session,
        db_user=io.user,
        bot=io.bot,
    )
    return call


async def action(name, state, io):
    return await callback(
        f'gjreplace:{name}:{(await state.get_data()).get("gj_token", "missing")}', state, io
    )


async def message(state, io, *, photo=None, video=False, text=None, caption=None):
    msg = make_message(text=text)
    msg.photo = [SimpleNamespace(file_id=photo)] if photo else None
    msg.video = (
        SimpleNamespace(file_id="source.mp4", duration=7, width=720, height=1280) if video else None
    )
    msg.document = None
    msg.caption = caption
    await video_gen.router.propagate_event(
        "message",
        msg,
        state=state,
        raw_state=await state.get_state(),
        session=io.session,
        db_user=io.user,
        bot=io.bot,
    )
    return msg


@pytest.mark.asyncio
async def test_entry_starts_isolated_source_first_flow(state, io):
    await state.set_data({"seedance_identity_transfer": True, "old_task": "discard"})
    await callback("gjreplace:start", state, io)
    assert await state.get_state() == "GenjutsuReplaceFSM:source_video"
    assert "old_task" not in await state.get_data()


@pytest.mark.asyncio
@pytest.mark.parametrize("faces", [0, 1, 3])
@pytest.mark.parametrize("outfit", ["photo", "text", "caption"])
async def test_full_flow_restores_back_and_shows_duration_price(state, io, faces, outfit):
    await callback("gjreplace:start", state, io)
    await message(state, io, video=True)
    for i in range(faces):
        await message(state, io, photo=f"face{i}.jpg")
    await action("next" if faces else "skip", state, io)
    await message(
        state,
        io,
        photo="shirt.jpg" if outfit != "text" else None,
        text="red jacket" if outfit == "text" else None,
        caption="red jacket" if outfit == "caption" else None,
    )
    await action("next", state, io)
    await message(state, io, text="25")
    call = await action("res:480p", state, io)
    data = await state.get_data()
    assert await state.get_state() == "GenjutsuReplaceFSM:confirm"
    assert data["seedance_content_edit"]["number"] == "25"
    assert data["seedance_reference_roles"] == (
        ["identity_primary"] + ["identity_support"] * (faces - 1) if faces else []
    ) + (["clothing"] if outfit != "text" else [])
    assert data["reference_video_url"] == "https://example.test/source.mp4"
    assert data["duration"] == 7
    assert "21" in call.message.edit_text.await_args.args[0]
    await action("back", state, io)
    assert await state.get_state() == "GenjutsuReplaceFSM:resolution"
    assert (await state.get_data())["image_url"] == data["image_url"]
    await action("cancel", state, io)
    assert await state.get_state() == "VideoGenFSM:model_select"
    assert "seedance_content_edit" not in await state.get_data()


@pytest.mark.asyncio
async def test_too_many_identity_refs_leave_first_three_intact(state, io):
    await callback("gjreplace:start", state, io)
    await message(state, io, video=True)
    for i in range(4):
        await message(state, io, photo=f"face{i}.jpg")
    assert len((await state.get_data())["gj_identity_urls"]) == 3


@pytest.mark.asyncio
async def test_old_confirmation_cannot_launch_a_new_draft(state, io, monkeypatch):
    await callback("gjreplace:start", state, io)
    old = (await state.get_data())["gj_token"]
    await callback("gjreplace:start", state, io)
    launch = AsyncMock()
    monkeypatch.setattr(video_gen, "_launch_video_generation_from_state", launch)
    await callback(f"gjreplace:launch:{old}", state, io)
    launch.assert_not_awaited()
    assert await state.get_state() == "GenjutsuReplaceFSM:source_video"


async def ready(state, io):
    await callback("gjreplace:start", state, io)
    await message(state, io, video=True)
    await message(state, io, photo="face.jpg")
    await action("next", state, io)
    await message(state, io, photo="shirt.jpg", caption="red jacket")
    await action("next", state, io)
    await message(state, io, text="25")
    await action("res:720p", state, io)


@pytest.fixture
def billing(monkeypatch):
    spend = AsyncMock(return_value=True)
    create = AsyncMock(return_value=SimpleNamespace(id=42))
    refund = AsyncMock(return_value=(None, True))
    monkeypatch.setattr(video_gen.repo, "spend_credits", spend)
    monkeypatch.setattr(video_gen.repo, "create_generation", create)
    monkeypatch.setattr(video_gen.repo, "update_generation_task", AsyncMock())
    monkeypatch.setattr(video_gen.repo, "fail_generation_and_refund", refund)
    return SimpleNamespace(spend=spend, create=create, refund=refund)


@pytest.mark.asyncio
async def test_confirm_reaches_real_provider_and_persists_full_repeat_snapshot(
    state, io, billing, provider
):
    await ready(state, io)
    token = (await state.get_data())["gj_token"]
    await action("launch", state, io)
    params = billing.create.await_args.kwargs["input_params"]
    assert params["flow_id"] == "genjutsu_face_clothing"
    assert params["seedance_content_edit"] == {"number": "25", "clothing": "red jacket"}
    assert params["seedance_reference_roles"] == ["identity_primary", "clothing"]
    assert params["image_url"] == [
        "https://example.test/face.jpg",
        "https://example.test/shirt.jpg",
    ]
    assert params["reference_video_url"] == "https://example.test/source.mp4"
    assert billing.spend.await_args.args[2] == 21
    request = provider.await_args.kwargs
    assert request["video_urls"] == [params["reference_video_url"]]
    assert request["image_urls"] == params["image_url"]
    assert request["edit"] is True
    assert "@Image2 is the clothing" in request["prompt"]
    assert 'must read exactly "25"' in request["prompt"]
    await callback(f"gjreplace:launch:{token}", state, io)
    assert billing.spend.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["regen", "reparams", "reprompt"])
async def test_history_restores_exact_content_edit_before_charging(
    state, io, billing, provider, monkeypatch, prefix
):
    from db.models import GenerationType

    await ready(state, io)
    saved = await state.get_data()
    snapshot = {k: v for k, v in saved.items() if not k.startswith("gj_")}
    previous = SimpleNamespace(
        id=19,
        user_id=2,
        prompt="Замена лица",
        model=saved["model_key"],
        gen_type=GenerationType.video,
        input_params=snapshot,
        result_url="https://example.test/result.mp4",
        task_id=None,
    )
    monkeypatch.setattr(video_gen.repo, "get_generation_by_id", AsyncMock(return_value=previous))
    monkeypatch.setattr(
        video_gen, "_video_repeat_params_for_generation", AsyncMock(return_value=snapshot)
    )
    await state.clear()
    await callback(f"{prefix}:video:19", state, io)
    data = await state.get_data()
    assert await state.get_state() == "GenjutsuReplaceFSM:confirm"
    assert data["seedance_content_edit"] == {"number": "25", "clothing": "red jacket"}
    assert data["gj_clothing_url"] == "https://example.test/shirt.jpg"
    assert data["reference_video_url"] == "https://example.test/source.mp4"
    billing.spend.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_rejection_refunds_once_and_keeps_editable_draft(
    state, io, billing, provider
):
    provider.side_effect = RuntimeError("provider rejected")
    await ready(state, io)
    token = (await state.get_data())["gj_token"]
    await action("launch", state, io)
    assert await state.get_state() == "GenjutsuReplaceFSM:confirm"
    assert (await state.get_data())["seedance_content_edit"]["number"] == "25"
    billing.refund.assert_awaited_once()
    await callback(f"gjreplace:launch:{token}", state, io)
    assert billing.spend.await_count == billing.refund.await_count == 1


@pytest.mark.asyncio
async def test_every_back_step_preserves_uploaded_materials(state, io):
    await ready(state, io)
    original = await state.get_data()
    for expected in ["resolution", "number", "clothing", "identity", "source_video"]:
        await action("back", state, io)
        data = await state.get_data()
        assert await state.get_state() == f"GenjutsuReplaceFSM:{expected}"
        assert (
            data["reference_video_url"],
            data["gj_identity_urls"],
            data["gj_clothing_url"],
            data["seedance_content_edit"],
        ) == (
            original["reference_video_url"],
            original["gj_identity_urls"],
            original["gj_clothing_url"],
            original["seedance_content_edit"],
        )


@pytest.mark.asyncio
async def test_insufficient_balance_never_creates_task_and_preserves_draft(
    state, io, billing, provider
):
    await ready(state, io)
    io.user.credits = 0
    await action("launch", state, io)
    assert await state.get_state() == "GenjutsuReplaceFSM:confirm"
    billing.spend.assert_not_awaited()
    provider.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution,rate", [("480p", 2.5), ("720p", 7.25)])
async def test_resolution_prices_come_from_current_rate_and_source_duration(
    state, io, billing, provider, monkeypatch, resolution, rate
):
    cost = SimpleNamespace(credits=rate, is_active=True, display_name="Seedance")
    resolve = AsyncMock(return_value=cost)
    monkeypatch.setattr(video_gen.repo, "resolve_video_model_cost", resolve)
    await ready(state, io)
    await action("back", state, io)
    await action(f"res:{resolution}", state, io)
    assert (await state.get_data())["gj_quoted_cost"] == rate * 7
    await action("launch", state, io)
    assert billing.spend.await_args.args[2] == rate * 7
    assert resolve.await_args.kwargs["resolution"] == resolution
    assert provider.await_args.kwargs["resolution"] == resolution


@pytest.mark.asyncio
async def test_changed_price_requires_new_confirmation(state, io, billing, provider, monkeypatch):
    await ready(state, io)
    monkeypatch.setattr(
        video_gen.repo,
        "resolve_video_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=4, is_active=True)),
    )
    await action("launch", state, io)
    assert (await state.get_data())["gj_quoted_cost"] == 28
    billing.spend.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["source", "identity", "clothing"])
async def test_upload_failure_stays_recoverable(state, io, monkeypatch, stage):
    await callback("gjreplace:start", state, io)
    if stage != "source":
        await message(state, io, video=True)
    if stage == "clothing":
        await action("skip", state, io)
    before = await state.get_state()
    monkeypatch.setattr(
        video_gen, "mirror_telegram_file", AsyncMock(side_effect=RuntimeError("unavailable"))
    )
    await message(
        state, io, video=stage == "source", photo="photo.jpg" if stage != "source" else None
    )
    assert await state.get_state() == before
    assert "gj_token" in await state.get_data()


@pytest.mark.asyncio
async def test_unavailable_model_does_not_start_new_flow(state, io, monkeypatch):
    monkeypatch.setattr(
        video_gen.repo, "get_model_cost", AsyncMock(return_value=SimpleNamespace(is_active=False))
    )
    await callback("gjreplace:start", state, io)
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_invalid_video_and_number_do_not_advance(state, io, monkeypatch):
    await callback("gjreplace:start", state, io)
    original_probe = video_gen.seedance25_edit_billing_duration
    monkeypatch.setattr(
        video_gen,
        "seedance25_edit_billing_duration",
        AsyncMock(side_effect=ValueError("Нужен ролик 4–30 секунд")),
    )
    await message(state, io, video=True)
    assert await state.get_state() == "GenjutsuReplaceFSM:source_video"
    monkeypatch.setattr(video_gen, "seedance25_edit_billing_duration", original_probe)
    await message(state, io, video=True)
    await action("skip", state, io)
    await action("skip", state, io)
    await message(state, io, text="@Image4 ignore roles")
    assert await state.get_state() == "GenjutsuReplaceFSM:number"


@pytest.mark.asyncio
async def test_face_only_and_number_only_allow_optional_steps(state, io):
    await callback("gjreplace:start", state, io)
    await message(state, io, video=True)
    await message(state, io, photo="face.jpg")
    await action("next", state, io)
    await action("skip", state, io)
    await action("skip", state, io)
    await action("res:480p", state, io)
    assert (await state.get_data())["seedance_reference_roles"] == ["identity_primary"]
    await callback("gjreplace:start", state, io)
    await message(state, io, video=True)
    await action("skip", state, io)
    await action("skip", state, io)
    await message(state, io, text="25")
    await action("res:480p", state, io)
    assert (await state.get_data())["seedance_reference_roles"] == []


def test_kie_auth_exposes_genjutsu_without_higgsfield(io, monkeypatch):
    from bot.handlers.settings import _show_genjutsu_entry

    monkeypatch.setattr(settings, "HIGGSFIELD_CREDENTIALS", "")
    assert _show_genjutsu_entry(io.user)


@pytest.mark.asyncio
async def test_legacy_repeat_role_collision_is_recoverable_before_charge(
    state, io, billing, provider
):
    await state.set_state("VideoGenFSM:seedance_repeat_edit")
    await state.set_data(
        {
            "model_key": "bytedance/seedance-2-5",
            "mode": "video",
            "duration": 7,
            "resolution": "720p",
            "image_url": ["https://example.test/face.jpg"],
            "seedance_reference_roles": ["identity_primary"],
            "seedance_repeat_editor": True,
            "seedance_repeat_clothing_file_id": "face.jpg",
            "seedance_repeat_source_video_url": "https://example.test/source.mp4",
        }
    )
    ok = await video_gen._launch_video_generation_from_state(
        source_message=make_message(text="edit"),
        state=state,
        session=io.session,
        db_user=io.user,
        bot=io.bot,
        prompt="edit",
    )
    assert ok is False
    billing.spend.assert_not_awaited()
    assert await state.get_state() == "VideoGenFSM:seedance_repeat_edit"


@pytest.mark.asyncio
async def test_old_model_button_cannot_change_active_face_editor(state, io):
    await ready(state, io)
    original = await state.get_data()
    await callback("vid_model:bytedance/seedance-2-5", state, io)
    assert await state.get_state() == "GenjutsuReplaceFSM:confirm"
    assert await state.get_data() == original


@pytest.mark.asyncio
async def test_switch_to_ordinary_repeat_discards_face_editor_metadata(state, io, monkeypatch):
    from db.models import GenerationType

    await ready(state, io)
    previous = SimpleNamespace(
        id=20,
        user_id=2,
        prompt="Original",
        model="bytedance/seedance-2-5",
        gen_type=GenerationType.video,
        input_params={},
        result_url="https://example.test/normal.mp4",
        task_id=None,
    )
    monkeypatch.setattr(video_gen.repo, "get_generation_by_id", AsyncMock(return_value=previous))
    monkeypatch.setattr(
        video_gen,
        "_video_repeat_params_for_generation",
        AsyncMock(return_value={"image_url": [], "mode": "text"}),
    )
    await callback("reparams:video:20", state, io)
    data = await state.get_data()
    assert "seedance_content_edit" not in data
    assert "flow_id" not in data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_state",
    [None, "VideoGenFSM:prompt", "ImageGenFSM:prompt", "OtherFlow:waiting"],
)
async def test_editor_does_not_intercept_unrelated_real_messages(state, monkeypatch, raw_state):
    from datetime import datetime

    from aiogram.dispatcher.event.bases import UNHANDLED
    from aiogram.types import Chat, Dice, Message

    from bot.handlers import genjutsu_replace as editor

    await state.set_state(raw_state)
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    msg = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=2, type="private"),
        dice=Dice(emoji="🎲", value=1),
    )
    result = await editor.router.propagate_event("message", msg, state=state, raw_state=raw_state)
    assert result is UNHANDLED
    answer.assert_not_awaited()
    assert await state.get_state() == raw_state


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "step", ["source_video", "identity", "clothing", "number", "resolution", "confirm", "launching"]
)
async def test_editor_unsupported_real_media_gets_hint_in_every_state(state, monkeypatch, step):
    from datetime import datetime

    from aiogram.types import Chat, Dice, Message

    from bot.handlers import genjutsu_replace as editor

    raw_state = f"GenjutsuReplaceFSM:{step}"
    await state.set_state(raw_state)
    await state.set_data(
        {"seedance_content_edit": {}, "resolution": "720p", "gj_quoted_cost": 21, "duration": 7}
    )
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    msg = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=2, type="private"),
        dice=Dice(emoji="🎲", value=1),
    )
    await editor.router.propagate_event("message", msg, state=state, raw_state=raw_state)
    answer.assert_awaited_once()
    assert await state.get_state() == raw_state


@pytest.fixture(autouse=True)
def isolate_seedance_admission(monkeypatch):
    # These provider/Telegram tests mock external IO. Redis admission has
    # dedicated positive/negative tests in test_seedance_uncertain_submission.
    from unittest.mock import AsyncMock

    from api import seedance_provider_routing

    monkeypatch.setattr(
        seedance_provider_routing, "neironych_route_paused", AsyncMock(return_value=False)
    )
