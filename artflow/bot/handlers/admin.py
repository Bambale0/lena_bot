# bot/handlers/admin.py
"""
Админ-панель.
Команды: /admin, /admin_stats, /admin_price, /admin_models, /admin_ban, /admin_credits
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import IsAdmin
from db import repository as repo

logger = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class AdminFSM(StatesGroup):
    # Price plan editing
    edit_price_key = State()
    edit_price_credits = State()
    edit_price_rub = State()
    # Model cost editing
    edit_model_key = State()
    edit_model_credits = State()
    # Credits management
    await_credits_tg_id = State()
    await_credits_amount = State()
    # Ban
    await_ban_tg_id = State()
    # Broadcast
    await_broadcast_text = State()


def admin_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="adm:stats")
    builder.button(text="💳 Прайс-лист", callback_data="adm:price")
    builder.button(text="⚙️ Стоимость моделей", callback_data="adm:models")
    builder.button(text="💰 Начислить кредиты", callback_data="adm:add_credits")
    builder.button(text="🚫 Бан / Разбан", callback_data="adm:ban")
    builder.button(text="📢 Рассылка", callback_data="adm:broadcast")
    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer("🔧 <b>Панель администратора</b>", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm:back")
async def cb_admin_back(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("🔧 <b>Панель администратора</b>", reply_markup=admin_menu_kb())
    await call.answer()


# ─── Статистика ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession) -> None:
    total_users = await repo.count_users(session)
    gens_today = await repo.count_generations_today(session)
    revenue_today = await repo.get_revenue_today(session)

    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="adm:back")

    await call.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👤 Пользователей: <b>{total_users}</b>\n"
        f"🎨 Генераций сегодня: <b>{gens_today}</b>\n"
        f"💰 Выручка сегодня: <b>{revenue_today:.2f}₽</b>",
        reply_markup=builder.as_markup(),
    )
    await call.answer()


# ─── Прайс-лист ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:price")
async def cb_price_list(call: CallbackQuery, session: AsyncSession) -> None:
    plans = await repo.get_active_price_plans(session)
    all_plans = await session.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(
            __import__("db.models", fromlist=["PricePlan"]).PricePlan
        ).order_by(__import__("db.models", fromlist=["PricePlan"]).PricePlan.sort_order)
    )
    all_plans = list(all_plans.scalars().all())

    builder = InlineKeyboardBuilder()
    for plan in all_plans:
        status = "✅" if plan.is_active else "❌"
        builder.button(
            text=f"{status} {plan.label} — {plan.price_rub:.0f}₽ / {plan.credits}кр",
            callback_data=f"adm:price_edit:{plan.key}",
        )
    builder.button(text="➕ Новый тариф", callback_data="adm:price_new")
    builder.button(text="← Назад", callback_data="adm:back")
    builder.adjust(1)

    await call.message.edit_text(
        "💳 <b>Прайс-лист</b>\n\nНажми на тариф для редактирования:",
        reply_markup=builder.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:price_edit:"))
async def cb_price_edit(
    call: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить цену", callback_data=f"adm:price_set_rub:{plan.key}")
    builder.button(text="✏️ Изменить кредиты", callback_data=f"adm:price_set_cr:{plan.key}")
    builder.button(
        text="🔴 Выключить" if plan.is_active else "🟢 Включить",
        callback_data=f"adm:price_toggle:{plan.key}",
    )
    builder.button(text="← Назад", callback_data="adm:price")
    builder.adjust(2)

    await call.message.edit_text(
        f"✏️ <b>Редактирование тарифа</b>\n\n"
        f"Ключ: <code>{plan.key}</code>\n"
        f"Название: {plan.label}\n"
        f"Кредиты: {plan.credits}\n"
        f"Цена: {plan.price_rub:.0f}₽\n"
        f"Статус: {'✅ Активен' if plan.is_active else '❌ Выключен'}",
        reply_markup=builder.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:price_toggle:"))
async def cb_price_toggle(call: CallbackQuery, session: AsyncSession) -> None:
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    new_state = await repo.toggle_price_plan(session, plan_key)
    await call.answer(f"Тариф {'включён' if new_state else 'выключен'}", show_alert=True)
    await cb_price_list(call, session)


@router.callback_query(F.data.startswith("adm:price_set_rub:"))
async def cb_price_set_rub_start(call: CallbackQuery, state: FSMContext) -> None:
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    await state.set_state(AdminFSM.edit_price_rub)
    await state.update_data(edit_plan_key=plan_key)
    await call.message.answer(f"Введи новую цену в рублях для <code>{plan_key}</code>:")
    await call.answer()


@router.message(AdminFSM.edit_price_rub)
async def handle_price_rub(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        new_price = float(message.text.strip())  # type: ignore[union-attr]
    except ValueError:
        await message.answer("Введи число (например: 299)")
        return

    data = await state.get_data()
    plan_key = data["edit_plan_key"]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if plan:
        plan.price_rub = new_price
        await session.commit()
    await state.clear()
    await message.answer(f"✅ Цена тарифа <code>{plan_key}</code> обновлена: {new_price:.0f}₽")


@router.callback_query(F.data.startswith("adm:price_set_cr:"))
async def cb_price_set_credits_start(call: CallbackQuery, state: FSMContext) -> None:
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    await state.set_state(AdminFSM.edit_price_credits)
    await state.update_data(edit_plan_key=plan_key)
    await call.message.answer(f"Введи новое количество кредитов для <code>{plan_key}</code>:")
    await call.answer()


@router.message(AdminFSM.edit_price_credits)
async def handle_price_credits(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        new_credits = int(message.text.strip())  # type: ignore[union-attr]
    except ValueError:
        await message.answer("Введи целое число")
        return

    data = await state.get_data()
    plan_key = data["edit_plan_key"]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if plan:
        plan.credits = new_credits
        await session.commit()
    await state.clear()
    await message.answer(f"✅ Кредиты тарифа <code>{plan_key}</code> обновлены: {new_credits}")


# ─── Стоимость моделей ────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:models")
async def cb_models(call: CallbackQuery, session: AsyncSession) -> None:
    costs = await repo.get_all_model_costs(session)
    builder = InlineKeyboardBuilder()
    for mc in costs:
        builder.button(
            text=f"{mc.display_name} — {mc.credits} кр",
            callback_data=f"adm:model_edit:{mc.model_key}",
        )
    builder.button(text="← Назад", callback_data="adm:back")
    builder.adjust(1)
    await call.message.edit_text(
        "⚙️ <b>Стоимость моделей</b>\n\nНажми для изменения:",
        reply_markup=builder.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:model_edit:"))
async def cb_model_edit(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":")[2]  # type: ignore[union-attr]
    await state.set_state(AdminFSM.edit_model_credits)
    await state.update_data(edit_model_key=model_key)
    await call.message.answer(
        f"Введи новую стоимость в кредитах для <code>{model_key}</code>:"
    )
    await call.answer()


@router.message(AdminFSM.edit_model_credits)
async def handle_model_credits(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        new_credits = int(message.text.strip())  # type: ignore[union-attr]
    except ValueError:
        await message.answer("Введи целое число")
        return

    data = await state.get_data()
    model_key = data["edit_model_key"]
    ok = await repo.set_model_cost(session, model_key, new_credits)
    await state.clear()
    if ok:
        await message.answer(f"✅ Стоимость <code>{model_key}</code> обновлена: {new_credits} кр")
    else:
        await message.answer("❌ Модель не найдена")


# ─── Кредиты ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:add_credits")
async def cb_add_credits(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminFSM.await_credits_tg_id)
    await call.message.answer("Введи Telegram ID пользователя:")
    await call.answer()


@router.message(AdminFSM.await_credits_tg_id)
async def handle_credits_tg_id(message: Message, state: FSMContext, session: AsyncSession) -> None:
    try:
        tg_id = int(message.text.strip())  # type: ignore[union-attr]
    except ValueError:
        await message.answer("Введи числовой Telegram ID")
        return
    user = await repo.get_user_by_tg_id(session, tg_id)
    if not user:
        await message.answer("Пользователь не найден")
        await state.clear()
        return
    await state.update_data(target_user_id=user.id, target_tg_id=tg_id)
    await state.set_state(AdminFSM.await_credits_amount)
    await message.answer(
        f"Пользователь: <b>{user.full_name}</b> (@{user.username})\n"
        f"Баланс: {user.credits} кр\n\nВведи количество кредитов (может быть отрицательным):"
    )


@router.message(AdminFSM.await_credits_amount)
async def handle_credits_amount(message: Message, state: FSMContext, session: AsyncSession) -> None:
    try:
        amount = int(message.text.strip())  # type: ignore[union-attr]
    except ValueError:
        await message.answer("Введи целое число")
        return

    data = await state.get_data()
    new_balance = await repo.add_credits(session, data["target_user_id"], amount)
    await state.clear()
    await message.answer(
        f"✅ Начислено <b>{amount}</b> кр пользователю {data['target_tg_id']}\n"
        f"Новый баланс: <b>{new_balance}</b> кр"
    )


# ─── Бан ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:ban")
async def cb_ban(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminFSM.await_ban_tg_id)
    await call.message.answer(
        "Введи Telegram ID для бана/разбана\n"
        "<i>Формат: tg_id или tg_id unban</i>"
    )
    await call.answer()


@router.message(AdminFSM.await_ban_tg_id)
async def handle_ban(message: Message, state: FSMContext, session: AsyncSession) -> None:
    parts = message.text.strip().split()  # type: ignore[union-attr]
    try:
        tg_id = int(parts[0])
    except ValueError:
        await message.answer("Неверный формат")
        await state.clear()
        return

    unban = len(parts) > 1 and parts[1].lower() == "unban"
    if unban:
        ok = await repo.unban_user(session, tg_id)
        await message.answer(f"✅ Разбан {tg_id}" if ok else "❌ Пользователь не найден")
    else:
        ok = await repo.ban_user(session, tg_id)
        await message.answer(f"🚫 Забанен {tg_id}" if ok else "❌ Пользователь не найден")
    await state.clear()


# ─── Рассылка ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:broadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminFSM.await_broadcast_text)
    await call.message.answer(
        "📢 Введи текст рассылки (поддерживается HTML):\n"
        "<i>Для отмены: /cancel</i>"
    )
    await call.answer()


@router.message(AdminFSM.await_broadcast_text, F.text)
async def handle_broadcast(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = message.text  # type: ignore[union-attr]
    tg_ids = await repo.get_all_user_ids(session)
    await state.clear()

    status_msg = await message.answer(f"📢 Отправляю {len(tg_ids)} пользователям...")

    sent, failed = 0, 0
    from aiogram import Bot
    bot: Bot = message.bot  # type: ignore[assignment]
    for tg_id in tg_ids:
        try:
            await bot.send_message(tg_id, text)
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ Рассылка завершена\n"
        f"Доставлено: {sent} · Ошибок: {failed}"
    )
