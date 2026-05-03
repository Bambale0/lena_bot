# bot/keyboards/prompts.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import PromptCategory, PromptStatus, UserPrompt

PAGE_SIZE = 8


def category_filter_kb(selected: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"{'✅ ' if selected is None else ''}Все категории",
            callback_data="prompts:cat:all",
        )
    )
    for cat in PromptCategory:
        check = "✅ " if selected == cat.value else ""
        builder.button(text=f"{check}{cat.label()}", callback_data=f"prompts:cat:{cat.value}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="➕ Добавить промпт", callback_data="prompts:add"),
        InlineKeyboardButton(text="📊 Мои промпты", callback_data="prompts:my"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def prompts_list_kb(
    prompts: list[UserPrompt],
    page: int,
    total: int,
    category: str | None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in prompts:
        builder.row(
            InlineKeyboardButton(
                text=f"{p.title[:40]} · {p.uses_count}×",
                callback_data=f"prompts:view:{p.id}",
            )
        )

    # Пагинация
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"prompts:page:{page-1}:{category or 'all'}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"prompts:page:{page+1}:{category or 'all'}"))
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(text="🔍 Категории", callback_data="prompts:open"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def prompt_detail_kb(prompt_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✨ Использовать", callback_data=f"prompts:use:{prompt_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="◀ К списку", callback_data="prompts:open"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def category_select_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in PromptCategory:
        builder.button(text=cat.label(), callback_data=f"prompt_cat:{cat.value}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="menu:main"))
    return builder.as_markup()


def prompt_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Отправить на модерацию", callback_data="prompt_confirm:yes"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data="prompt_confirm:edit"),
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="menu:main"))
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
                text=f"{icon} {p.title[:35]} · {p.uses_count}×",
                callback_data=f"prompts:my_view:{p.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data="prompts:open"))
    return builder.as_markup()


def my_prompt_detail_kb(prompt_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == "approved":
        builder.row(
            InlineKeyboardButton(text="🔴 Деактивировать", callback_data=f"prompts:deactivate:{prompt_id}")
        )
    builder.row(InlineKeyboardButton(text="◀ Мои промпты", callback_data="prompts:my"))
    return builder.as_markup()


# ── Модерация (для /admin) ────────────────────────────────────────────────────

def moderation_kb(prompt_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"mod:approve:{prompt_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mod:reject:{prompt_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🚫 Деактивировать", callback_data=f"mod:deactivate:{prompt_id}"),
    )
    return builder.as_markup()


def use_prompt_model_kb(prompt_id: int) -> InlineKeyboardMarkup:
    """Выбор модели после нажатия 'Использовать' из каталога."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎨 Генерировать изображение", callback_data=f"prompts:gen_img:{prompt_id}"))
    builder.row(InlineKeyboardButton(text="🎬 Генерировать видео", callback_data=f"prompts:gen_vid:{prompt_id}"))
    builder.row(InlineKeyboardButton(text="◀ Назад", callback_data=f"prompts:view:{prompt_id}"))
    return builder.as_markup()
