from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup


@dataclass(frozen=True)
class ScreenRender:
    text: str
    reply_markup: InlineKeyboardMarkup
