"""Настройки — смена языка и другие опции."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.main_menu import back_to_menu_kb
from db import repository as repo
from db.models import User

router = Router(name="settings")


def language_kb(current_lang: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=("✅ " if current_lang == "ru" else "") + "🇷🇺 Русский",
        callback_data="lang:set:ru",
    )
    builder.button(
        text=("✅ " if current_lang == "en" else "") + "🇬🇧 English",
        callback_data="lang:set:en",
    )
    builder.button(text=t("btn_back", current_lang), callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "menu:settings")
async def cb_settings(call: CallbackQuery, db_user: User) -> None:
    lang = db_user.language or "ru"
    text = (
        t("settings_title", lang) + "\n\n"
        + t("settings_language", lang) + f": {('🇷🇺 Русский' if lang == 'ru' else '🇬🇧 English')}"
    )
    await call.message.edit_text(text, reply_markup=language_kb(lang))  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("lang:set:"))
async def cb_set_language(
    call: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    new_lang = call.data.split(":")[-1]  # type: ignore[union-attr]
    if new_lang not in ("ru", "en"):
        await call.answer("Error", show_alert=True)
        return

    await repo.set_user_language(session, db_user.id, new_lang)
    db_user.language = new_lang  # Update in-memory

    text = t("language_changed_en" if new_lang == "en" else "language_changed", new_lang)
    await call.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()
