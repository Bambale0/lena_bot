# bot/keyboards/prompts.py
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import ModelCost, UserPrompt
from db.prompt_repository import COLLECTION_TAGS

PAGE_SIZE = 8


def prompts_home_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔥 Trending", callback_data="prompts:trending"),
        InlineKeyboardButton(text="👑 Top today", callback_data="prompts:top_today"),
    )
    builder.row(InlineKeyboardButton(text="🧠 Best prompts", callback_data="prompts:best"))
    builder.row(InlineKeyboardButton(text="📁 Разделы", callback_data="prompts:collections"))
    builder.row(InlineKeyboardButton(text="➕ Добавить свой", callback_data="prompts:add"))
    builder.row(InlineKeyboardButton(text="📊 Мои промпты", callback_data="prompts:my"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def prompt_collections_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tag, label in COLLECTION_TAGS.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"prompts:collection:{tag}:0"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="prompts:open"))
    return builder.as_markup()


def prompt_card_kb(prompt_id: int, *, source: str, index: int, has_next: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔁 Повторить", callback_data=f"prompt_use:{prompt_id}"),
        InlineKeyboardButton(text="✨ Ремикс", callback_data=f"prompt_remix:{prompt_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="❤️ Лайк", callback_data=f"prompt_like:{prompt_id}:{source}:{index}"),
        InlineKeyboardButton(text="📤 Поделиться", callback_data=f"prompt_share:{prompt_id}"),
    )
    if has_next:
        builder.row(InlineKeyboardButton(text="➡️ Далее", callback_data=f"prompt_next:{source}:{index+1}"))
    builder.row(InlineKeyboardButton(text="◀ К промптам", callback_data="prompts:open"))
    return builder.as_markup()


def prompt_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Отправить на модерацию", callback_data="prompt_confirm:yes"),
        InlineKeyboardButton(text="✏️ Начать заново", callback_data="prompt_confirm:edit"),
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="prompts:open"))
    return builder.as_markup()


def my_prompts_kb(prompts: list[UserPrompt]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status_icons = {
        "pending": "⏳",
        "approved": "✅",
        "rejected": "❌",
        "deactivated": "🔴",
    }
    for p in prompts:
        icon = status_icons.get(p.status.value, "❓")
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} {p.title[:35]} · {p.uses_count}× · ❤️ {p.likes}",
                callback_data=f"prompts:my_view:{p.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="prompts:open"))
    return builder.as_markup()


def my_prompt_detail_kb(prompt_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == "approved":
        builder.row(InlineKeyboardButton(text="🔴 Деактивировать", callback_data=f"prompts:deactivate:{prompt_id}"))
    builder.row(InlineKeyboardButton(text="◀ Мои промпты", callback_data="prompts:my"))
    return builder.as_markup()


def prompt_use_model_kb(
    prompt_id: int,
    model_costs: list[ModelCost],
    *,
    reference_only: bool = False,
) -> InlineKeyboardMarkup:
    from bot.keyboards.models import HIDDEN_IMAGE_MODELS, IMAGE_CAPS

    builder = InlineKeyboardBuilder()
    for mc in model_costs:
        caps = IMAGE_CAPS.get(mc.model_key)
        if (
            mc.gen_type.value == "image"
            and caps is not None
            and mc.model_key not in HIDDEN_IMAGE_MODELS
            and (not reference_only or "image" in caps.get("modes", []))
        ):
            builder.row(
                InlineKeyboardButton(
                    text=f"{mc.display_name} · {mc.credits} 💋",
                    callback_data=f"prompt_pick_model:{prompt_id}:{mc.model_key}",
                )
            )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="prompts:open"))
    return builder.as_markup()


def prompt_use_reference_kb(prompt_id: int, *, allow_skip: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if allow_skip:
        builder.row(
            InlineKeyboardButton(text="▶ Без референса", callback_data=f"prompt_skip_ref:{prompt_id}")
        )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="prompts:open"))
    return builder.as_markup()


def moderation_kb(prompt_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"mod:approve:{prompt_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mod:reject:{prompt_id}"),
    )
    builder.row(InlineKeyboardButton(text="🚫 Деактивировать", callback_data=f"mod:deactivate:{prompt_id}"))
    return builder.as_markup()
