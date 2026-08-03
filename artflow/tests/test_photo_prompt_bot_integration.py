from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from api import photo_prompt_service
from bot.handlers.photo_prompt import (
    _append_photo_prompt_button,
    _result_keyboard,
    _result_text,
)
from bot.keyboards.models import after_generation_kb, image_active_kb, image_session_kb


def _callbacks(markup: InlineKeyboardMarkup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_photo_prompt_button_is_inserted_before_home_without_duplicates() -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Действие", callback_data="action")],
            [InlineKeyboardButton(text="Главная", callback_data="menu:main")],
        ]
    )

    updated = _append_photo_prompt_button(markup)
    updated_twice = _append_photo_prompt_button(updated)

    assert _callbacks(updated) == ["action", "img:photo2prompt", "menu:main"]
    assert _callbacks(updated_twice).count("img:photo2prompt") == 1


def test_active_and_completed_image_keyboards_expose_photo_prompt() -> None:
    assert "img:photo2prompt" in _callbacks(image_active_kb())
    assert "img:photo2prompt" in _callbacks(image_session_kb(101, prompt="test"))
    assert "img:photo2prompt" in _callbacks(after_generation_kb(101, "image"))
    assert "img:photo2prompt" not in _callbacks(after_generation_kb(101, "video"))


def test_result_text_shows_escaped_prompt_in_code() -> None:
    text = _result_text("cinematic <portrait> & soft light")

    assert "<code>cinematic &lt;portrait&gt; &amp; soft light</code>" in text
    assert "выделить и скопировать" in text


def test_result_keyboard_supports_active_series_and_model_selection() -> None:
    active_callbacks = _callbacks(_result_keyboard(has_active_session=True))
    selected_callbacks = _callbacks(
        _result_keyboard(
            has_active_session=False,
            selected_model_key="gpt-image-2-text-to-image",
            selected_model_name="GPT Image 2",
        )
    )

    assert active_callbacks == ["img:use_prompt", "p2p:model", "img:cancel_prompt"]
    assert selected_callbacks == ["p2p:model", "p2p:generate", "img:cancel_prompt"]


def test_vision_instruction_requires_plain_russian_prompt() -> None:
    chat_messages = photo_prompt_service._photo_prompt_chat_messages("data:image/jpeg;base64,aW1hZ2U=")
    responses_input = photo_prompt_service._photo_prompt_responses_input("data:image/jpeg;base64,aW1hZ2U=")

    chat_text = str(chat_messages)
    responses_text = str(responses_input)
    assert "русском языке" in chat_text
    assert "только финальный промпт" in chat_text
    assert "русском языке" in responses_text
    assert "без комментариев" in responses_text
    assert "English" not in chat_text
    assert "English" not in responses_text
