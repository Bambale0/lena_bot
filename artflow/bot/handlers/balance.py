# bot/handlers/balance.py
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_to_menu_kb, balance_screen_kb
from core.config import settings
from db import repository as repo
from db.models import GenerationType, User

logger = logging.getLogger(__name__)
router = Router(name="balance")


class WithdrawalFSM(StatesGroup):
    amount = State()
    details = State()


def referral_screen_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="💸 Запросить вывод", callback_data="referral:withdraw")
    builder.button(text="🏠 Главное меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def withdrawal_request_admin_kb(request_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить выплату", callback_data=f"adm:wd:approve:{request_id}")
    builder.button(text="❌ Отклонить", callback_data=f"adm:wd:reject:{request_id}")
    builder.adjust(1)
    return builder.as_markup()


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
        f"💳 Пополнить баланс можно прямо здесь."
    )
    await call.message.edit_text(text, reply_markup=balance_screen_kb())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data == "menu:referral")
async def cb_referral(call: CallbackQuery, db_user: User, bot: Bot, session: AsyncSession) -> None:
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={db_user.referral_code}"
    l1, l2, l3 = await repo.count_user_referrals(session, db_user.id)
    withdrawals = await repo.get_user_withdrawal_requests(session, db_user.id, limit=3)
    withdrawal_lines = []
    for request in withdrawals:
        withdrawal_lines.append(
            f"• #{request.id}: {request.amount_rub:.0f}₽ · {request.status.value}"
        )

    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"Твоя ссылка:\n"
        f"<code>{ref_link}</code>\n\n"
        f"<b>Твои рефералы:</b>\n"
        f"• L1 прямые: <b>{l1}</b>\n"
        f"• L2: <b>{l2}</b>\n"
        f"• L3: <b>{l3}</b>\n\n"
        f"💰 <b>Бонусы:</b>\n"
        f"• Уровень 1 (прямой): +{settings.REFERRAL_L1_CREDITS} кредитов\n"
        f"• Уровень 2 (реферал реферала): +{settings.REFERRAL_L2_CREDITS} кредитов\n\n"
        f"<i>Бонусы начисляются при первом запуске бота приглашённым.</i>"
    )
    if withdrawal_lines:
        text += "\n\n💸 <b>Последние заявки на вывод:</b>\n" + "\n".join(withdrawal_lines)
    await call.message.edit_text(text, reply_markup=referral_screen_kb())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data == "referral:withdraw")
async def cb_referral_withdraw(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(WithdrawalFSM.amount)
    await call.message.answer(  # type: ignore[union-attr]
        "💸 <b>Заявка на ручной вывод</b>\n\n"
        "Введи сумму в рублях, которую нужно вывести.\n"
        "Например: <code>1500</code>"
    )
    await call.answer()


@router.message(WithdrawalFSM.amount, F.text)
async def handle_withdraw_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        await message.answer("Введи сумму числом, например: <code>1500</code>")
        return
    if amount <= 0:
        await message.answer("Сумма должна быть больше нуля.")
        return
    await state.update_data(withdraw_amount=amount)
    await state.set_state(WithdrawalFSM.details)
    await message.answer(
        "Теперь отправь реквизиты для выплаты одним сообщением.\n\n"
        "Например: банк + номер телефона / карта / USDT-кошелёк."
    )


@router.message(WithdrawalFSM.details, F.text)
async def handle_withdraw_details(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    details = (message.text or "").strip()
    if len(details) < 5:
        await message.answer("Реквизиты слишком короткие. Отправь банк/номер/кошелёк подробнее.")
        return
    data = await state.get_data()
    amount = float(data["withdraw_amount"])
    request = await repo.create_withdrawal_request(
        session,
        user_id=db_user.id,
        amount_rub=amount,
        payout_details=details,
    )
    await state.clear()
    await message.answer(
        f"✅ Заявка на вывод #{request.id} создана.\n"
        f"Сумма: <b>{amount:.2f}₽</b>\n\n"
        "Админ получит запрос на подтверждение в чат.",
        reply_markup=back_to_menu_kb(),
    )

    admin_text = (
        f"💸 <b>Новая заявка на вывод #{request.id}</b>\n\n"
        f"Пользователь: @{db_user.username or '—'} · <code>{db_user.tg_id}</code>\n"
        f"Имя: <b>{db_user.full_name or '—'}</b>\n"
        f"Сумма: <b>{amount:.2f}₽</b>\n\n"
        f"<b>Реквизиты:</b>\n<code>{details}</code>"
    )
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=withdrawal_request_admin_kb(request.id),
            )
        except Exception as e:
            logger.warning("Failed to notify admin %s about withdrawal %s: %s", admin_id, request.id, e)


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
