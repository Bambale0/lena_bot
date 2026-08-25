from __future__ import annotations

from types import SimpleNamespace

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.safe_repeat_ui import install_safe_repeat_keyboard_support


def _callbacks(markup: InlineKeyboardMarkup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_completed_session_image_uses_safe_repeat_callback() -> None:
    module = SimpleNamespace(
        image_session_kb=lambda gen_id=None, **kwargs: InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔁 Ещё вариант", callback_data=f"img_session:repeat:{gen_id}")]
            ]
        ),
        after_generation_kb=lambda gen_id, gen_type, **kwargs: InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"regen:{gen_type}:{gen_id}")]
            ]
        ),
    )
    install_safe_repeat_keyboard_support(module)

    markup = module.image_session_kb(123)
    assert _callbacks(markup) == ["repeat_image_123"]
    assert markup.inline_keyboard[0][0].text == "🔁 Повторить генерацию"

    generic = module.after_generation_kb(124, "image")
    assert _callbacks(generic) == ["repeat_image_124"]
    assert generic.inline_keyboard[0][0].text == "🔁 Повторить генерацию"


def test_video_repeat_keyboard_is_not_rewritten() -> None:
    module = SimpleNamespace(
        image_session_kb=lambda gen_id=None, **kwargs: InlineKeyboardMarkup(inline_keyboard=[]),
        after_generation_kb=lambda gen_id, gen_type, **kwargs: InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"regen:{gen_type}:{gen_id}")]
            ]
        ),
    )
    install_safe_repeat_keyboard_support(module)
    markup = module.after_generation_kb(5, "video")
    assert _callbacks(markup) == ["regen:video:5"]
