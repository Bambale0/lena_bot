from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from api.web import sessions as web_sessions
from bot.handlers import image_gen
from db import repository as repo
from db.models import Generation, GenerationStatus, GenerationType
from tests.test_image_session_prompt_provenance import (
    OWN_PROMPT,
    SECRET,
)
from tests.test_image_session_prompt_provenance import (
    local_session as _local_session,
)
from tests.test_seedance_feed_bot import seedance_bot as _seedance_bot
from tests.test_seedance_feed_bot import video_launch as video_launch

local_session = _local_session
seedance_bot = _seedance_bot


@pytest.fixture
def state():
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=4200, user_id=4200))


@pytest.mark.parametrize("entry", ["text", "caption", "active"])
async def test_direct_telegram_prompt_restores_in_web_session(local_session, state, monkeypatch, entry):
    user = local_session.sync.get(image_gen.User, 42)
    image_session = await repo.create_image_session(
        local_session, 42, "nano-banana-2", "text", "1:1", "2K", 1, None,
    )
    await state.update_data(model_key=image_session.model, image_session_id=image_session.id, mode="text")
    monkeypatch.setattr(repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    monkeypatch.setattr(image_gen, "_launch_session_generation", AsyncMock(return_value=True))
    message = SimpleNamespace(text=None if entry == "caption" else OWN_PROMPT,
                              caption=OWN_PROMPT if entry == "caption" else None, answer=AsyncMock())
    if entry == "active":
        await image_gen.handle_session_prompt(message, state, local_session, user, AsyncMock())
    else:
        await image_gen.handle_prompt(message, state, local_session, user, AsyncMock())

    response = await web_sessions.active_image_session(local_session, user)
    assert image_session.prompt_provenance == "user_supplied"
    assert response["data"]["last_prompt"] == OWN_PROMPT
    assert response["data"]["prompt_hidden"] is False


@pytest.mark.parametrize("protection", ["feed", "hidden", "foreign", "template"])
async def test_direct_text_does_not_promote_protected_session(local_session, state, monkeypatch, protection):
    user = local_session.sync.get(image_gen.User, 42)
    image_session = await repo.create_image_session(
        local_session, 42, "nano-banana-2", "text", "1:1", "2K", 1, SECRET,
    )
    if protection != "template":
        local_session.add(Generation(
            user_id=99 if protection == "foreign" else 42, model=image_session.model,
            image_session_id=image_session.id, gen_type=GenerationType.image, prompt=SECRET,
            source_feed_gen_id=77 if protection == "feed" else None,
            input_params=json.dumps({"hidden_prompt": True}) if protection == "hidden" else None,
            status=GenerationStatus.done,
        ))
        await local_session.commit()
    await state.update_data(model_key=image_session.model, image_session_id=image_session.id, mode="text",
                            remix_mode=protection == "template", style_edit_kind="hair_color" if protection == "template" else None)
    monkeypatch.setattr(image_gen, "_launch_session_generation", AsyncMock(return_value=True))
    message = SimpleNamespace(text=OWN_PROMPT, answer=AsyncMock())
    await image_gen.handle_session_prompt(message, state, local_session, user, AsyncMock())
    assert image_session.prompt_provenance is None
    response = await web_sessions.active_image_session(local_session, user)
    assert SECRET not in json.dumps(response)


async def test_direct_text_never_promotes_old_untrusted_prompt_fields(local_session, state, monkeypatch):
    user = local_session.sync.get(image_gen.User, 42)
    image_session = await repo.create_image_session(
        local_session, 42, "nano-banana-2", "text", "1:1", "2K", 1, SECRET,
    )
    await state.update_data(model_key=image_session.model, image_session_id=image_session.id, mode="text")
    monkeypatch.setattr(repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    await image_gen.handle_prompt(SimpleNamespace(text=OWN_PROMPT, answer=AsyncMock()), state, local_session, user, AsyncMock())
    response = await web_sessions.active_image_session(local_session, user)
    assert response["data"]["last_prompt"] == OWN_PROMPT
    assert SECRET not in json.dumps(response)


@pytest.fixture
def quoted_regen(seedance_bot, state):
    fixture = seedance_bot
    fixture.kwargs["state"] = state
    return fixture


def _confirm_callback(fixture):
    markup = fixture.call.message.answer.await_args.kwargs["reply_markup"]
    return markup.inline_keyboard[0][0].callback_data


async def test_measured_duration_is_quoted_before_any_charge_or_submit(quoted_regen):
    fixture = quoted_regen
    await fixture.run("regen")
    fixture.repo.spend_credits.assert_not_awaited()
    fixture.service.generate_video.assert_not_awaited()
    assert "7 сек" in fixture.call.message.answer.await_args.args[0]
    assert "28 💋" in fixture.call.message.answer.await_args.args[0]
    callback = _confirm_callback(fixture)
    assert len(callback.encode()) <= 64
    fixture.call.data = callback
    await fixture.run("regen")
    fixture.repo.spend_credits.assert_awaited_once()
    assert fixture.repo.spend_credits.await_args.args[2] == 28
    assert fixture.service.generate_video.await_args.kwargs["duration"] == 7
    await fixture.run("regen")
    fixture.repo.spend_credits.assert_awaited_once()
    fixture.service.generate_video.assert_awaited_once()


@pytest.mark.parametrize("change", ["price", "duration", "reference", "clear", "new_quote", "foreign_owner"])
async def test_stale_quote_cannot_charge(quoted_regen, change):
    fixture = quoted_regen
    await fixture.run("regen")
    callback = _confirm_callback(fixture)
    if change == "price":
        fixture.repo.resolve_video_model_cost.side_effect = None
        fixture.repo.resolve_video_model_cost.return_value = SimpleNamespace(credits=5, display_name="Seedance", is_active=True)
    elif change == "duration":
        fixture.metadata.duration_seconds = 9.1
    elif change == "reference":
        fixture.data["image_url"] = "https://example.test/new-reference.jpg"
    elif change == "clear":
        await fixture.kwargs["state"].clear()
    elif change == "new_quote":
        await fixture.run("regen")
    elif change == "foreign_owner":
        fixture.kwargs["db_user"] = SimpleNamespace(id=99)
    fixture.call.data = callback
    await fixture.run("regen")
    fixture.repo.spend_credits.assert_not_awaited()
    fixture.service.generate_video.assert_not_awaited()


async def test_interruption_after_consuming_quote_cannot_spend_again(quoted_regen):
    fixture = quoted_regen
    await fixture.run("regen")
    fixture.call.data = _confirm_callback(fixture)
    fixture.repo.spend_credits.side_effect = RuntimeError("synthetic interruption")
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        await fixture.run("regen")
    await fixture.run("regen")
    fixture.repo.spend_credits.assert_awaited_once()
    fixture.service.generate_video.assert_not_awaited()


async def test_confirmation_survives_serialized_state_restore(quoted_regen):
    fixture = quoted_regen
    await fixture.run("regen")
    fixture.call.data = _confirm_callback(fixture)
    old_state = fixture.kwargs["state"]
    saved = json.loads(json.dumps(await old_state.get_data()))
    restored = FSMContext(MemoryStorage(), old_state.key)
    await restored.set_data(saved)
    fixture.kwargs["state"] = restored
    await fixture.run("regen")
    fixture.repo.spend_credits.assert_awaited_once()
    fixture.service.generate_video.assert_awaited_once()


@pytest.mark.parametrize("callback", ["regen:video:nope", "regen:video:²", "regen:video:88:é", "regen:video:88:"])
async def test_malformed_confirmation_cannot_charge(quoted_regen, callback):
    quoted_regen.call.data = callback
    await quoted_regen.run("regen")
    quoted_regen.repo.spend_credits.assert_not_awaited()
    quoted_regen.service.generate_video.assert_not_awaited()


async def test_changed_price_requires_quote_even_when_duration_is_unchanged(quoted_regen):
    fixture = quoted_regen
    fixture.data["duration"] = 7
    fixture.previous.credits_spent = 21
    await fixture.run("regen")
    fixture.repo.spend_credits.assert_not_awaited()
    assert "28 💋" in fixture.call.message.answer.await_args.args[0]


async def test_quote_shows_all_six_billed_decimal_places(quoted_regen):
    fixture = quoted_regen
    fixture.repo.resolve_video_model_cost.side_effect = None
    fixture.repo.resolve_video_model_cost.return_value = SimpleNamespace(credits=1234.56789, display_name="Seedance", is_active=True)
    await fixture.run("regen")
    assert "8641.97523 💋" in fixture.call.message.answer.await_args.args[0]
    fixture.call.data = _confirm_callback(fixture)
    await fixture.run("regen")
    assert fixture.repo.spend_credits.await_args.args[2] == 8641.97523


async def test_cancel_button_through_navigation_invalidates_confirmation(quoted_regen):
    from bot.middlewares.navigation import NavigationMiddleware
    from tests.factories import make_callback

    fixture = quoted_regen
    await fixture.run("regen")
    confirm = _confirm_callback(fixture)
    cancel = fixture.call.message.answer.await_args.kwargs["reply_markup"].inline_keyboard[1][0].callback_data
    handler = AsyncMock()
    await NavigationMiddleware()(handler, make_callback(data=cancel, user_id=4200), {"state": fixture.kwargs["state"]})
    handler.assert_awaited_once()
    fixture.call.data = confirm
    await fixture.run("regen")
    fixture.repo.spend_credits.assert_not_awaited()
    fixture.service.generate_video.assert_not_awaited()


async def test_text_before_required_photo_keeps_only_authenticated_prompt(local_session, state, monkeypatch):
    user = local_session.sync.get(image_gen.User, 42)
    image_session = await repo.create_image_session(
        local_session, 42, "qwen/image-edit", "image", "1:1", "basic", 1, None,
    )
    await state.update_data(model_key=image_session.model, image_session_id=image_session.id, mode="image")
    monkeypatch.setattr(repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value="https://example.test/user.jpg"))
    launch = AsyncMock(return_value=True)
    monkeypatch.setattr(image_gen, "_launch_session_generation", launch)
    await image_gen.handle_prompt(SimpleNamespace(text=OWN_PROMPT, answer=AsyncMock()), state, local_session, user, AsyncMock())
    assert await state.get_state() == image_gen.ImageGenFSM.image_upload.state
    response = await web_sessions.active_image_session(local_session, user)
    assert response["data"]["last_prompt"] == OWN_PROMPT
    launch.assert_not_awaited()

    # The existing upload flow accepts a direct caption before its review button.
    # It does not turn a stored copied prompt into newly authenticated text.
    message = SimpleNamespace(text=None, caption=OWN_PROMPT, photo=[SimpleNamespace(file_id="own-photo", file_size=10)], answer=AsyncMock())
    await image_gen.handle_reference_upload(message, state, local_session, user, AsyncMock())
    await image_gen.cb_image_review_launch(SimpleNamespace(message=AsyncMock(), answer=AsyncMock()), state, local_session, user)
    launch.assert_awaited_once()
    assert launch.await_args.kwargs["prompt"] == OWN_PROMPT
    assert image_session.prompt_provenance == "user_supplied"


@pytest.fixture
async def initial_feed_launch(seedance_bot, state, monkeypatch):
    from bot.handlers import feed, seedance25_references, video_gen
    from tests.factories import make_callback

    fixture = seedance_bot
    fixture.kwargs["state"] = state
    fixture.kwargs["db_user"].credits = 1000
    fixture.source.model = fixture.previous.model
    cost = SimpleNamespace(model_key=fixture.previous.model, credits=4, display_name="Seedance", is_active=True, gen_type=GenerationType.video)
    monkeypatch.setattr(feed.repo, "get_public_feed_generation", AsyncMock(return_value=fixture.source))
    monkeypatch.setattr(feed.repo, "get_all_model_costs", AsyncMock(return_value=[cost]))
    fixture.repo.get_model_cost = AsyncMock(return_value=cost)
    monkeypatch.setattr(seedance25_references, "repo", fixture.repo)
    call = make_callback(data="feed:use:77", user_id=42)
    await feed.cb_feed_use(call, fixture.kwargs["session"], fixture.kwargs["db_user"], state)
    call.data = f"vid_model:{fixture.previous.model}"
    await video_gen.router.propagate_event("callback_query", call, state=state, raw_state=await state.get_state(),
                                          session=fixture.kwargs["session"], db_user=fixture.kwargs["db_user"])
    await seedance25_references.add_seedance25_photo(SimpleNamespace(photo=[SimpleNamespace(file_id="user-photo", file_size=10)], answer=AsyncMock()), state)
    await seedance25_references.finish_seedance25_refs(call, state)
    fixture.initial_call = call
    fixture.events.clear()
    return fixture


async def _initial_next(fixture):
    from bot.handlers import video_gen
    fixture.initial_call.data = "vpar_next"
    await video_gen.cb_vpar_next(fixture.initial_call, fixture.kwargs["state"], fixture.kwargs["session"],
                                fixture.kwargs["db_user"], fixture.kwargs["bot"])


async def _initial_confirm(fixture, callback):
    from bot.handlers import video_gen
    fixture.initial_call.data = callback
    await video_gen.router.propagate_event("callback_query", fixture.initial_call,
                                          state=fixture.kwargs["state"], raw_state=await fixture.kwargs["state"].get_state(),
                                          session=fixture.kwargs["session"], db_user=fixture.kwargs["db_user"], bot=fixture.kwargs["bot"])


async def test_initial_feed_picker_to_photo_to_params_requires_measured_quote(initial_feed_launch):
    fixture = initial_feed_launch
    await _initial_next(fixture)
    fixture.repo.spend_credits.assert_not_awaited()
    fixture.service.generate_video.assert_not_awaited()
    sent = fixture.initial_call.message.answer.await_args
    assert "7 сек" in sent.args[0] and "28 💋" in sent.args[0]
    assert SECRET not in sent.args[0]
    callback = sent.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
    await _initial_confirm(fixture, callback)
    fixture.repo.spend_credits.assert_awaited_once()
    assert fixture.repo.spend_credits.await_args.args[2] == 28
    assert fixture.service.generate_video.await_args.kwargs["duration"] == 7
    assert SECRET not in fixture.service.generate_video.await_args.args[1]
    await _initial_confirm(fixture, callback)
    fixture.repo.spend_credits.assert_awaited_once()


@pytest.mark.parametrize("change", ["price", "duration", "source", "cancel", "next_again"])
async def test_initial_feed_quote_revalidates_before_spending(initial_feed_launch, change):
    from bot.middlewares.navigation import NavigationMiddleware
    from tests.factories import make_callback

    fixture = initial_feed_launch
    await _initial_next(fixture)
    markup = fixture.initial_call.message.answer.await_args.kwargs["reply_markup"]
    callback = markup.inline_keyboard[0][0].callback_data
    if change == "price":
        fixture.repo.resolve_video_model_cost.side_effect = None
        fixture.repo.resolve_video_model_cost.return_value = SimpleNamespace(credits=5, display_name="Seedance", is_active=True)
    elif change == "duration":
        fixture.metadata.duration_seconds = 9.1
    elif change == "source":
        fixture.source.result_url = "https://example.test/replaced-source.mp4"
    elif change == "cancel":
        await NavigationMiddleware()(AsyncMock(), make_callback(data=markup.inline_keyboard[1][0].callback_data), {"state": fixture.kwargs["state"]})
    elif change == "next_again":
        await _initial_next(fixture)
    await _initial_confirm(fixture, callback)
    fixture.repo.spend_credits.assert_not_awaited()
    fixture.service.generate_video.assert_not_awaited()
