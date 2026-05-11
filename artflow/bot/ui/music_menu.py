from __future__ import annotations

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.ui.common import ScreenRender


def render_music_menu(last_style: str | None = None, credits: float | None = None) -> ScreenRender:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎤 С текстом", callback_data="music:mode:lyrics"),
        InlineKeyboardButton(text="🎧 Без текста", callback_data="music:mode:instrumental"),
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    )
    style_text = f"Последний стиль: <b>{last_style}</b>\n\n" if last_style else ""
    price_text = f"Стоимость: <b>{credits:g} 💋</b> за трек.\n" if credits is not None else ""
    return ScreenRender(
        text=(
            "🎵 <b>Генерация музыки</b>\n\n"
            f"{style_text}"
            "Сделаю трек через Suno AI.\n"
            f"{price_text}"
            "Обычно готово за 1–2 минуты.\n\n"
            "Выбери режим, а затем отправь описание трека, настроения и жанра."
        ),
        reply_markup=builder.as_markup(),
    )
