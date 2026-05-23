from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import image_gen
from bot.keyboards.models import image_nana_banano_kb, image_scenarios_kb
from bot.ui.image_menu import render_image_scenarios


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_image_fast_start_is_renamed_to_nana_banano() -> None:
    buttons = _buttons(image_scenarios_kb())
    assert buttons[0].text == "🍌 nana banano"
    assert buttons[0].callback_data == "img_scn:fast"


def test_nana_banano_keyboard_has_four_buttons_with_pro_default() -> None:
    buttons = _buttons(image_nana_banano_kb())
    assert len(buttons) == 4
    assert buttons[0].text == "✅ Pro"
    assert buttons[0].callback_data == "img_nb:model:nano-banana-pro"
    assert buttons[1].text == "Banana 2"
    assert buttons[1].callback_data == "img_nb:model:nano-banana-2"
    assert buttons[3].callback_data == "menu:image"


def test_image_entry_keeps_full_scenario_menu() -> None:
    render = render_image_scenarios()
    buttons = _buttons(render.reply_markup)
    assert "Выбери сценарий" in render.text
    assert buttons[0].text == "🍌 nana banano"
    assert buttons[1].text == "🖼️ Из фото в новую версию"
    assert buttons[2].text == "🧠 Все нейросети"


@pytest.mark.asyncio
async def test_prompt_input_photo_adds_reference_inside_nana_banano_menu() -> None:
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_size=10, file_id="ref_1")],
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "nana_banano_flow": True,
            "model_key": "nano-banana-pro",
            "ref_file_ids": [],
        }
    )

    await image_gen.handle_prompt_reference_upload(message, state)

    state.update_data.assert_awaited_once_with(
        image_file_id="ref_1",
        ref_file_ids=["ref_1"],
        mode="image",
        image_mode="image",
    )
    markup = message.answer.await_args.kwargs["reply_markup"]
    buttons = _buttons(markup)
    assert len(buttons) == 4
    assert buttons[2].text == "📎 Референсы: 1"


@pytest.mark.asyncio
async def test_nana_banano_text_asks_photo_before_prompt() -> None:
    call = SimpleNamespace(message=SimpleNamespace(), answer=AsyncMock())
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    db_user = SimpleNamespace(credits=100)
    repo_stub = SimpleNamespace(
        resolve_image_model_cost=AsyncMock(return_value=SimpleNamespace(credits=1)),
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        edit_message = AsyncMock()
        monkeypatch.setattr(image_gen, "repo", repo_stub)
        monkeypatch.setattr(image_gen, "safe_edit_message", edit_message)
        await image_gen._show_nana_banano_flow(
            call=call,
            state=state,
            session=AsyncMock(),
            db_user=db_user,
        )

    text = edit_message.await_args.args[1]
    assert text.index("Отправь фото") < text.index("отправь промпт")
