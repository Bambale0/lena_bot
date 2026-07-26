"""Настройки и вторичная навигация UX v2."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.main_menu import back_to_menu_kb
from bot.ui.navigation_v2 import render_create_hub, render_more_hub
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
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
    builder.button(text=t("btn_back", current_lang), callback_data="menu:more")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "menu:create")
async def cb_create_hub(call: CallbackQuery, db_user: User) -> None:
    lang = db_user.language or "ru"
    screen = render_create_hub(lang=lang, is_admin=bool(getattr(db_user, "is_admin", False)))
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "menu:more")
async def cb_more_hub(call: CallbackQuery, db_user: User) -> None:
    lang = db_user.language or "ru"
    screen = render_more_hub(lang=lang, is_admin=bool(getattr(db_user, "is_admin", False)))
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "menu:settings")
async def cb_settings(call: CallbackQuery, db_user: User) -> None:
    lang = db_user.language or "ru"
    if lang == "ru":
        text = (
            "⚙️ <b>Настройки</b>\n\n"
            "Здесь можно изменить язык интерфейса.\n\n"
            f"🌍 Язык: {('🇷🇺 Русский' if lang == 'ru' else '🇬🇧 English')}"
        )
    else:
        text = (
            "⚙️ <b>Settings</b>\n\n"
            "Here you can change the interface language.\n\n"
            f"🌍 Language: {('🇷🇺 Russian' if lang == 'ru' else '🇬🇧 English')}"
        )
    await safe_edit_message(call.message, text, reply_markup=language_kb(lang))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("lang:set:"))
async def cb_set_language(
    call: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    new_lang = call.data.split(":")[-1]  # type: ignore[union-attr]
    if new_lang not in ("ru", "en"):
        await call.answer("Error", show_alert=True)
        return

    await repo.set_user_language(session, db_user.id, new_lang)
    db_user.language = new_lang

    text = t("language_changed_en" if new_lang == "en" else "language_changed", new_lang)
    await call.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()
