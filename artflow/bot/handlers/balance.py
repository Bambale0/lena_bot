# bot/handlers/balance.py
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_to_menu_kb
from core.config import settings
from db import repository as repo
from db.models import GenerationType, User

logger = logging.getLogger(__name__)
router = Router(name="balance")


@router.callback_query(F.data == "menu:balance")
async def cb_balance(call: CallbackQuery, db_user: User) -> None:
    sub_status = (
        f"✅ До {db_user.subscription_until.strftime('%d.%m.%Y')}"
        if db_user.is_subscribed and db_user.subscription_until
        else "❌ Не активна"
    )
    text = (
        f"💎 <b>Твой баланс</b>\n\n"
        f"Кредиты: <b>{db_user.credits}</b>\n"
        f"Подписка: {sub_status}\n\n"
        f"<b>Стоимость генерации:</b>\n"
        f"• Изображение: 2–10 кр\n"
        f"• Видео: 20–50 кр\n"
        f"• Midjourney: 5–15 кр\n\n"
        f"💳 Нажми «Пополнить» в главном меню, чтобы купить кредиты."
    )
    await call.message.edit_text(text, reply_markup=back_to_menu_kb())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data == "menu:referral")
async def cb_referral(call: CallbackQuery, db_user: User, bot: Bot) -> None:
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={db_user.referral_code}"

    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"Твоя ссылка:\n"
        f"<code>{ref_link}</code>\n\n"
        f"💰 <b>Бонусы:</b>\n"
        f"• Уровень 1 (прямой): +{settings.REFERRAL_L1_CREDITS} кредитов\n"
        f"• Уровень 2 (реферал реферала): +{settings.REFERRAL_L2_CREDITS} кредитов\n\n"
        f"<i>Бонусы начисляются при первом запуске бота приглашённым.</i>"
    )
    await call.message.edit_text(text, reply_markup=back_to_menu_kb())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data == "menu:history")
async def cb_history(
    call: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    history = await repo.get_user_history(session, db_user.id, limit=10)

    if not history:
        await call.message.edit_text(  # type: ignore[union-attr]
            "📋 История пуста. Сделай первую генерацию!",
            reply_markup=back_to_menu_kb(),
        )
        await call.answer()
        return

    lines = ["📋 <b>Последние генерации:</b>\n"]
    for i, gen in enumerate(history, 1):
        icon = "🎨" if gen.gen_type == GenerationType.image else "🎬"
        status_icon = {"done": "✅", "pending": "⏳", "failed": "❌", "processing": "🔄"}.get(
            gen.status.value, "❓"
        )
        lines.append(
            f"{i}. {icon} {status_icon} <code>{gen.model}</code>\n"
            f"   <i>{gen.prompt[:60]}{'...' if len(gen.prompt) > 60 else ''}</i>\n"
            f"   -{gen.credits_spent} кр"
        )

    await call.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines), reply_markup=back_to_menu_kb()
    )
    await call.answer()
