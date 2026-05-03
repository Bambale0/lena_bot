# bot/keyboards/midjourney.py
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api.midjourney_service import MJBotType, MJButton, MJDimensions, MJSpeed, MJVideoMotion


def mj_submenu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎨 Imagine", callback_data="mj:imagine"),
        InlineKeyboardButton(text="🖼️ Blend", callback_data="mj:blend"),
    )
    builder.row(
        InlineKeyboardButton(text="🔍 Describe", callback_data="mj:describe"),
        InlineKeyboardButton(text="🎞️ Video", callback_data="mj:video"),
    )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:main"))
    return builder.as_markup()


def mj_bot_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for bt in MJBotType:
        builder.row(
            InlineKeyboardButton(text=bt.label(), callback_data=f"mj_bt:{bt.value}")
        )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:mj"))
    return builder.as_markup()


def mj_speed_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sp in MJSpeed:
        builder.button(text=sp.label(), callback_data=f"mj_sp:{sp.value}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:mj"))
    return builder.as_markup()


def mj_action_buttons_kb(buttons: list[MJButton]) -> InlineKeyboardMarkup:
    """
    Динамическая клавиатура из кнопок, вернувшихся в task result.
    callback_data = mj_btn:{index}  (index → lookup в FSM state data)
    """
    builder = InlineKeyboardBuilder()
    for i, btn in enumerate(buttons):
        builder.button(text=btn.display or f"#{i}", callback_data=f"mj_btn:{i}")
    builder.adjust(4)
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def mj_blend_submit_kb(count: int) -> InlineKeyboardMarkup:
    """Показывается во время сбора изображений для blend."""
    builder = InlineKeyboardBuilder()
    if count >= 2:
        builder.row(
            InlineKeyboardButton(
                text=f"✅ Блендить ({count} фото)", callback_data="mj_blend:submit"
            )
        )
    if count < 5:
        builder.row(
            InlineKeyboardButton(
                text="➕ Добавить ещё фото", callback_data="mj_blend:add"
            )
        )
    builder.row(InlineKeyboardButton(text="✖️ Отмена", callback_data="menu:mj"))
    return builder.as_markup()


def mj_dimensions_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    labels = {
        MJDimensions.PORTRAIT: "🖼 Портрет",
        MJDimensions.SQUARE: "⬛ Квадрат",
        MJDimensions.LANDSCAPE: "🏞 Пейзаж",
    }
    for dim, label in labels.items():
        builder.button(text=label, callback_data=f"mj_dim:{dim.value}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:mj"))
    return builder.as_markup()


def mj_video_speed_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for motion in MJVideoMotion:
        builder.button(text=motion.label(), callback_data=f"mj_vmot:{motion.value}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:mj"))
    return builder.as_markup()


def mj_skip_prompt_kb() -> InlineKeyboardMarkup:
    """Кнопка 'Без промпта' при вводе текста для видео/modal."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⏭ Без промпта", callback_data="mj_skip_prompt"))
    builder.row(InlineKeyboardButton(text="✖️ Отмена", callback_data="menu:mj"))
    return builder.as_markup()
