from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from api.kling4_contract import REFERENCE_MODEL, Kling4Input
from bot.handlers import kling4


@pytest.fixture
async def state():
    storage = MemoryStorage()
    yield FSMContext(storage, StorageKey(bot_id=1, chat_id=1, user_id=1))
    await storage.close()


def test_bot_renaming_preserves_tags_and_does_not_rewrite_longer_names():
    options = Kling4Input(
        elements=[
            {"name": "Hero", "image_urls": ["https://cdn.example/a.png"] * 2},
            {"name": "Hero_2", "image_urls": ["https://cdn.example/b.png"] * 2},
        ]
    ).model_dump()
    updated, prompt = kling4.rename_material(
        options, "@Hero meets @Hero_2.", "elements", 0, "Actor"
    )
    assert prompt == "@Actor meets @Hero_2."
    assert updated["elements"][0]["name"] == "Actor"
    with pytest.raises(ValueError):
        kling4.rename_material(options, "@Hero", "elements", 0, "hero_2")


@pytest.mark.asyncio
async def test_non_admin_cannot_open_direct_model_callback(monkeypatch, state):
    monkeypatch.setattr(kling4, "kling4_visible", AsyncMock(return_value=False))
    call = AsyncMock()
    # Passing a concrete CallbackQuery is unnecessary: assert no draft was created.
    await kling4.start_kling4(call, state, None, SimpleNamespace(id=1), REFERENCE_MODEL)
    assert await state.get_data() == {}


@pytest.mark.asyncio
async def test_photo_element_commit_rotates_intent_and_invalidates_quote(monkeypatch, state):
    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(kling4, "render", AsyncMock())
    original = str(uuid4())
    await state.set_data(
        {
            "model_key": REFERENCE_MODEL,
            "kling4": Kling4Input().model_dump(),
            "intent_id": original,
            "quoted_credits": 85.5,
            "k4_field": "element_image",
            "k4_revision": "abc",
            "k4_new_name": "Hero_1",
            "k4_pending_images": ["https://cdn.example/a.png", "https://cdn.example/b.png"],
        }
    )
    call = SimpleNamespace(data="k4:done:vabc", answer=AsyncMock(), message=AsyncMock())
    await kling4.action(call, state, None, SimpleNamespace(id=1))
    result = await state.get_data()
    assert result["intent_id"] != original
    assert result["quoted_credits"] is None
    assert len(result["kling4"]["elements"]) == 1


@pytest.mark.asyncio
async def test_old_material_controls_cannot_edit_reindexed_material(monkeypatch, state):
    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    await state.set_data(
        {
            "model_key": REFERENCE_MODEL,
            "kling4": Kling4Input().model_dump(),
            "k4_revision": "latest",
        }
    )
    before = await state.get_data()
    call = SimpleNamespace(
        data="k4:text:element_name_0:vold", answer=AsyncMock(), message=AsyncMock()
    )
    await kling4.action(call, state, None, SimpleNamespace(id=1))
    assert await state.get_data() == before
    assert call.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.parametrize("group", [None, "fast"])
def test_catalog_has_one_kling4_reference_entry(group):
    from api.kling4_contract import KEYFRAME_MODEL
    from bot.keyboards.models import video_models_kb
    from db.models import GenerationType

    costs = [
        SimpleNamespace(
            model_key=key, display_name=label, credits=rate, gen_type=GenerationType.video
        )
        for key, label, rate in [
            (REFERENCE_MODEL, "Kling 4 · Референсы", 17),
            (KEYFRAME_MODEL, "Kling 4 · Ключевые кадры", 28.5),
        ]
    ]
    markup = video_models_kb(costs, group)
    buttons = [
        b for row in markup.inline_keyboard for b in row if "kling-4.0" in (b.callback_data or "")
    ]
    assert len(buttons) == 1
    assert buttons[0].callback_data == f"vid_model:{REFERENCE_MODEL}"
    assert buttons[0].text == "🎬 Kling 4 · 17 💋/сек"


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["command", "reference", "old_keyframe"])
async def test_entry_opens_reference_collector_without_mode_picker(monkeypatch, state, entry):
    from api.kling4_contract import KEYFRAME_MODEL

    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    message = AsyncMock()
    if entry == "command":
        await kling4.open_kling4(message, None, SimpleNamespace(id=1), state)
    else:
        call = SimpleNamespace(answer=AsyncMock(), message=message)
        await kling4.start_kling4(
            call,
            state,
            None,
            SimpleNamespace(id=1),
            KEYFRAME_MODEL if entry == "old_keyframe" else REFERENCE_MODEL,
        )
    data = await state.get_data()
    assert data["model_key"] == REFERENCE_MODEL
    assert await state.get_state() == kling4.Kling4FSM.edit.state
    markup = message.answer.await_args.kwargs["reply_markup"]
    actions = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert not any(a.startswith(("k4:start:", "k4:media:")) for a in actions)
    assert "Пришли" in message.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,collection", [("image", "image_urls"), ("video", "video_urls"), ("audio", "voices")]
)
async def test_automatic_attachments_use_measured_kind_and_caption(
    monkeypatch, state, kind, collection
):
    import io

    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        kling4,
        "store_kling4_asset",
        AsyncMock(return_value={"url": "https://cdn.example/ref", "kind": kind}),
    )
    await state.set_data(
        {
            "model_key": REFERENCE_MODEL,
            "kling4": Kling4Input().model_dump(),
            "intent_id": "before",
            "quoted_credits": 85,
            "k4_quote_token": "old",
        }
    )
    await state.set_state(kling4.Kling4FSM.edit)
    media = SimpleNamespace(file_id="file", file_size=100, file_name="ref.bin")
    message = SimpleNamespace(
        photo=[],
        video=None,
        audio=None,
        voice=None,
        document=media,
        caption="Сцена с референсом",
        answer=AsyncMock(),
    )
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="ref.bin")),
        download_file=AsyncMock(return_value=io.BytesIO(b"content")),
    )
    await kling4.media_value(message, state, None, SimpleNamespace(id=1), bot)
    data = await state.get_data()
    assert len(data["kling4"][collection]) == 1
    assert data["prompt"] == "Сцена с референсом"
    assert data["intent_id"] != "before"
    assert data["quoted_credits"] is None
    assert data["k4_quote_token"] is None
    assert await state.get_state() == kling4.Kling4FSM.edit.state
    body = kling4.body_from_state(data)
    from api.kling4_contract import build_kling4_payload

    payload = build_kling4_payload(body.model, body.prompt, body.kling4)
    assert payload["model"] == REFERENCE_MODEL
    assert payload["input"][collection]


@pytest.mark.asyncio
@pytest.mark.parametrize("current", [kling4.Kling4FSM.edit, kling4.Kling4FSM.confirm])
async def test_installed_router_accepts_plain_prompt_without_button(monkeypatch, state, current):
    from bot.handlers import video_gen
    from tests.factories import make_message

    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    await state.set_data(
        {
            "model_key": REFERENCE_MODEL,
            "kling4": Kling4Input().model_dump(),
            "intent_id": "before",
            "quoted_credits": 85,
            "k4_quote_token": "old",
        }
    )
    await state.set_state(current)
    message = make_message(text="Камера приближается к герою")
    await video_gen.router.propagate_event(
        "message",
        message,
        state=state,
        raw_state=await state.get_state(),
        session=None,
        db_user=SimpleNamespace(id=1),
        bot=message.bot,
    )
    data = await state.get_data()
    assert data["prompt"] == message.text
    assert data["quoted_credits"] is None
    assert data["k4_quote_token"] is None
    assert data["intent_id"] != "before"
    assert await state.get_state() == kling4.Kling4FSM.edit.state


@pytest.mark.asyncio
async def test_installed_router_collects_mixed_references_in_order(monkeypatch, state):
    import io

    from bot.handlers import video_gen
    from tests.factories import make_message

    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    store = AsyncMock(
        side_effect=[
            {"url": f"https://cdn.example/{i}", "kind": kind}
            for i, kind in enumerate(["image", "video", "audio", "image"])
        ]
    )
    monkeypatch.setattr(kling4, "store_kling4_asset", store)
    await state.set_data(
        {
            "model_key": REFERENCE_MODEL,
            "kling4": Kling4Input().model_dump(),
            "prompt": "Тест",
            "intent_id": str(uuid4()),
        }
    )
    await state.set_state(kling4.Kling4FSM.edit)
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="ref.bin")),
        download_file=AsyncMock(side_effect=lambda _: io.BytesIO(b"content")),
    )
    for kind in ["photo", "video", "voice", "document"]:
        message = make_message(text=None)
        (
            message.photo,
            message.video,
            message.audio,
            message.voice,
            message.document,
            message.caption,
        ) = [], None, None, None, None, None
        media = SimpleNamespace(file_id="file", file_size=100, file_name="ref.bin")
        setattr(message, kind, [media] if kind == "photo" else media)
        await video_gen.router.propagate_event(
            "message",
            message,
            state=state,
            raw_state=await state.get_state(),
            session=None,
            db_user=SimpleNamespace(id=1),
            bot=bot,
        )
    data = await state.get_data()
    assert data["kling4"]["image_urls"] == ["https://cdn.example/0", "https://cdn.example/3"]
    assert data["kling4"]["video_urls"] == ["https://cdn.example/1"]
    assert data["kling4"]["voices"] == [{"name": "Voice_1", "audio_url": "https://cdn.example/2"}]
    assert data["prompt"] == "Тест"


@pytest.mark.asyncio
async def test_reference_limit_failure_preserves_draft_and_confirmation(monkeypatch, state):
    import io

    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        kling4,
        "store_kling4_asset",
        AsyncMock(return_value={"url": "https://cdn.example/extra", "kind": "image"}),
    )
    await state.set_data(
        {
            "model_key": REFERENCE_MODEL,
            "kling4": Kling4Input(
                image_urls=[f"https://cdn.example/{i}" for i in range(10)]
            ).model_dump(),
            "intent_id": "before",
            "quoted_credits": 85,
            "k4_quote_token": "old",
        }
    )
    await state.set_state(kling4.Kling4FSM.confirm)
    before = await state.get_data()
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="photo", file_size=100)],
        caption="Замена промпта",
        answer=AsyncMock(),
    )
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="a.jpg")),
        download_file=AsyncMock(return_value=io.BytesIO(b"content")),
    )
    await kling4.media_value(message, state, None, SimpleNamespace(id=1), bot)
    assert await state.get_data() == before
    assert await state.get_state() == kling4.Kling4FSM.confirm.state
    assert "10" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_legacy_keyframe_recipe_does_not_accept_reference_upload(monkeypatch, state):
    from api.kling4_contract import KEYFRAME_MODEL

    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    await state.set_data(
        {
            "model_key": KEYFRAME_MODEL,
            "kling4": Kling4Input(first_frame_url="https://cdn.example/first.jpg").model_dump(),
            "intent_id": "legacy",
        }
    )
    await state.set_state(kling4.Kling4FSM.edit)
    before = await state.get_data()
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="photo", file_size=100)], caption=None, answer=AsyncMock()
    )
    import io

    monkeypatch.setattr(
        kling4,
        "store_kling4_asset",
        AsyncMock(return_value={"url": "https://cdn.example/new.jpg", "kind": "image"}),
    )
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="new.jpg")),
        download_file=AsyncMock(return_value=io.BytesIO(b"content")),
    )
    await kling4.media_value(message, state, None, SimpleNamespace(id=1), bot)
    assert await state.get_data() == before
    assert "кадр" in message.answer.await_args.args[0].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/cancel", "/promo", "/prompts", "/admin"])
@pytest.mark.parametrize("current", [kling4.Kling4FSM.edit, kling4.Kling4FSM.confirm])
async def test_direct_prompt_collector_does_not_consume_commands(
    monkeypatch, state, current, command
):
    from aiogram.dispatcher.event.bases import UNHANDLED

    from bot.handlers import video_gen
    from tests.factories import make_message

    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    await state.set_data(
        {
            "model_key": REFERENCE_MODEL,
            "kling4": Kling4Input().model_dump(),
            "prompt": "Сцена",
            "intent_id": "before",
        }
    )
    await state.set_state(current)
    before = await state.get_data()
    message = make_message(text=command)
    result = await video_gen.router.propagate_event(
        "message",
        message,
        state=state,
        raw_state=await state.get_state(),
        session=None,
        db_user=SimpleNamespace(id=1),
        bot=message.bot,
    )
    assert result is UNHANDLED
    assert await state.get_data() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,options,suffix",
    [
        ("image", Kling4Input(image_urls=["https://cdn.example/a"] * 10), "jpg"),
        ("video", Kling4Input(video_urls=["https://cdn.example/a"] * 5), "mp4"),
        (
            "audio",
            Kling4Input(
                voices=[
                    {"name": f"Voice_{i}", "audio_url": "https://cdn.example/a"} for i in range(3)
                ]
            ),
            "wav",
        ),
    ],
)
async def test_automatic_limit_refuses_before_downloading_or_storing(
    monkeypatch, state, kind, options, suffix
):
    import io

    monkeypatch.setattr(kling4, "allowed", AsyncMock(return_value=True))
    store = AsyncMock(return_value={"url": "https://cdn.example/extra", "kind": kind})
    monkeypatch.setattr(kling4, "store_kling4_asset", store)
    await state.set_data(
        {"model_key": REFERENCE_MODEL, "kling4": options.model_dump(), "intent_id": "before"}
    )
    await state.set_state(kling4.Kling4FSM.edit)
    message = SimpleNamespace(
        photo=[],
        video=None,
        audio=None,
        voice=None,
        document=SimpleNamespace(file_id="f", file_size=100, file_name=f"a.{suffix}"),
        caption=None,
        answer=AsyncMock(),
    )
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path=f"a.{suffix}")),
        download_file=AsyncMock(return_value=io.BytesIO(b"content")),
    )
    before = await state.get_data()
    await kling4.media_value(message, state, None, SimpleNamespace(id=1), bot)
    assert await state.get_data() == before
    assert store.await_count == 0
    assert bot.download_file.await_count == 0
