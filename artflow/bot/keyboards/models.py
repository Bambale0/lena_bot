# bot/keyboards/models.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api.image_service import ImageModel
from api.video_service import MotionDirection, VideoModel
from db.models import ModelCost


def image_models_kb(model_costs: list[ModelCost]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for mc in model_costs:
        if mc.gen_type.value == "image":
            builder.row(
                InlineKeyboardButton(
                    text=f"{mc.display_name} — {mc.credits} кр",
                    callback_data=f"img_model:{mc.model_key}",
                )
            )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:main"))
    return builder.as_markup()


def video_models_kb(model_costs: list[ModelCost]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for mc in model_costs:
        if mc.gen_type.value == "video":
            builder.row(
                InlineKeyboardButton(
                    text=f"{mc.display_name} — {mc.credits} кр",
                    callback_data=f"vid_model:{mc.model_key}",
                )
            )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:main"))
    return builder.as_markup()


def video_mode_kb(model_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✍️ Текстовый промпт", callback_data=f"vid_mode:text:{model_key}"),
    )
    builder.row(
        InlineKeyboardButton(text="🖼️ Из изображения", callback_data=f"vid_mode:image:{model_key}"),
    )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:video"))
    return builder.as_markup()


def motion_control_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for direction in MotionDirection:
        builder.button(
            text=direction.label(),
            callback_data=f"motion:{direction.value}",
        )
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:video"))
    return builder.as_markup()


def after_generation_kb(gen_id: int, gen_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"regen:{gen_type}:{gen_id}"),
        InlineKeyboardButton(text="✏️ Изменить промпт", callback_data=f"reprompt:{gen_type}:{gen_id}"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()
