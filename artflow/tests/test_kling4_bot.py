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
