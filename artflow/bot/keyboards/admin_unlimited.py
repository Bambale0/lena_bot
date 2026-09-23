from __future__ import annotations

from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import GenerationType


def _generation_type_value(value) -> str:
    return str(getattr(value, "value", value) or "")


def eligible_image_models(costs: Iterable) -> list:
    result = [
        item
        for item in costs
        if bool(getattr(item, "is_active", True))
        and _generation_type_value(getattr(item, "gen_type", None)) == GenerationType.image.value
        and "__" not in str(getattr(item, "model_key", ""))
    ]
    return sorted(
        result,
        key=lambda item: (
            str(getattr(item, "display_name", "")).casefold(),
            str(getattr(item, "model_key", "")).casefold(),
        ),
    )


def _mode_suffix(model_key: str) -> str:
    key = str(model_key or "")
    if "image-to-image" in key or "image-edit" in key or key.endswith("-edit"):
        return " · edit"
    if "text-to-image" in key:
        return " · text"
    return ""


def image_unlimited_models_kb(
    costs: Iterable,
    *,
    enabled_model_ids: set[int] | frozenset[int],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in eligible_image_models(costs):
        model_id = int(item.id)
        marker = "✅" if model_id in enabled_model_ids else "▫️"
        label = str(getattr(item, "display_name", None) or getattr(item, "model_key", model_id))
        suffix = _mode_suffix(str(getattr(item, "model_key", "")))
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {label[:40]}{suffix}",
                callback_data=f"adm:iu:toggle:{model_id}",
            )
        )

    builder.row(
        InlineKeyboardButton(text="🧹 Снять весь безлимит", callback_data="adm:iu:clear")
    )
    builder.row(
        InlineKeyboardButton(text="👤 Другой пользователь", callback_data="adm:iu:other"),
        InlineKeyboardButton(text="← Админ-панель", callback_data="adm:back"),
    )
    return builder.as_markup()
