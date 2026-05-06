# bot/handlers/admin.py
"""
Админ-панель.
Команды: /admin, /admin_stats, /admin_price, /admin_models, /admin_ban, /admin_credits
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Bot
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import IsAdmin
from db import repository as repo
from db.models import User, WithdrawalStatus

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
    builder.button(text="👥 Рефералы", callback_data="adm:referrals")
    builder.button(text="💸 Заявки на вывод", callback_data="adm:withdrawals")
    builder.button(text="💳 Прайс-лист", callback_data="adm:price")
    builder.button(text="⚙️ Стоимость моделей", callback_data="adm:models")
    builder.button(text="💰 Начислить кредиты", callback_data="adm:add_credits")
    builder.button(text="🚫 Бан / Разбан", callback_data="adm:ban")
    builder.button(text="🗂 Промпты (модерация)", callback_data="adm:prompts")
    builder.button(text="📢 Рассылка", callback_data="adm:broadcast")
    builder.adjust(2)
    return builder.as_markup()


async def _show_admin_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = "🔧 <b>Панель администратора</b>"
    try:
        await call.message.edit_text(text, reply_markup=admin_menu_kb())  # type: ignore[union-attr]
    except TelegramBadRequest as e:
        if "there is no text in the message to edit" not in str(e).lower():
            raise
        await call.message.answer(text, reply_markup=admin_menu_kb())  # type: ignore[union-attr]
    await call.answer()


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer("🔧 <b>Панель администратора</b>", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "menu:admin")
async def cb_admin_menu(call: CallbackQuery, state: FSMContext) -> None:
    await _show_admin_menu(call, state)


@router.callback_query(F.data == "adm:back")
async def cb_admin_back(call: CallbackQuery, state: FSMContext) -> None:
    await _show_admin_menu(call, state)


def _user_label(user: User) -> str:
    username = f"@{user.username}" if user.username else "без username"
    return f"{username} · <code>{user.tg_id}</code>"


def _admin_back_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="← Админ-панель", callback_data="adm:back")
    return builder.as_markup()


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


# ─── Рефералы ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:referrals")
async def cb_referrals(call: CallbackQuery, session: AsyncSession) -> None:
    leaders = await repo.get_referral_leaders(session, limit=15)
    builder = InlineKeyboardBuilder()

    if not leaders:
        builder.button(text="← Назад", callback_data="adm:back")
        await call.message.edit_text(  # type: ignore[union-attr]
            "👥 <b>Рефералы</b>\n\nПока нет пользователей с рефералами.",
            reply_markup=builder.as_markup(),
        )
        await call.answer()
        return

    lines = ["👥 <b>Реферальная статистика</b>\n"]
    for i, leader in enumerate(leaders, 1):
        user = leader.user
        lines.append(
            f"{i}. {_user_label(user)}\n"
            f"   L1: <b>{leader.l1_count}</b> · L2: <b>{leader.l2_count}</b> · "
            f"L3: <b>{leader.l3_count}</b> · всего: <b>{leader.total_count}</b>"
        )
        builder.button(
            text=f"{i}. {user.username or user.tg_id} · {leader.total_count}",
            callback_data=f"adm:ref_user:{user.id}",
        )

    builder.button(text="← Назад", callback_data="adm:back")
    builder.adjust(1)
    await call.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("adm:ref_user:"))
async def cb_referral_user(call: CallbackQuery, session: AsyncSession) -> None:
    user_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    user = await repo.get_user_by_id(session, user_id)
    if not user:
        await call.answer("Пользователь не найден", show_alert=True)
        return
    l1, l2, l3 = await repo.count_user_referrals(session, user.id)

    builder = InlineKeyboardBuilder()
    if l1:
        builder.button(text=f"L1 прямые: {l1}", callback_data=f"adm:ref_level:{user.id}:1")
    if l2:
        builder.button(text=f"L2: {l2}", callback_data=f"adm:ref_level:{user.id}:2")
    if l3:
        builder.button(text=f"L3: {l3}", callback_data=f"adm:ref_level:{user.id}:3")
    builder.button(text="← К рефералам", callback_data="adm:referrals")
    builder.adjust(1)

    await call.message.edit_text(  # type: ignore[union-attr]
        f"👤 <b>Реферер</b>\n\n"
        f"{_user_label(user)}\n"
        f"Имя: <b>{user.full_name or '—'}</b>\n"
        f"Баланс: <b>{user.credits}</b> кр\n"
        f"Код: <code>{user.referral_code}</code>\n\n"
        f"Прямые L1: <b>{l1}</b>\n"
        f"Уровень L2: <b>{l2}</b>\n"
        f"Уровень L3: <b>{l3}</b>",
        reply_markup=builder.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:ref_level:"))
async def cb_referral_level(call: CallbackQuery, session: AsyncSession) -> None:
    _, _, user_id_raw, level_raw = call.data.split(":", 3)  # type: ignore[union-attr]
    user_id = int(user_id_raw)
    level = int(level_raw)
    parent = await repo.get_user_by_id(session, user_id)
    children = await repo.get_referral_children(session, user_id, level=level, limit=25)
    if not parent:
        await call.answer("Пользователь не найден", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="← К карточке", callback_data=f"adm:ref_user:{user_id}")
    builder.button(text="← Админ-панель", callback_data="adm:back")
    builder.adjust(1)

    if not children:
        await call.message.edit_text(  # type: ignore[union-attr]
            f"👥 <b>L{level} рефералы</b>\n\nУ {_user_label(parent)} нет пользователей на этом уровне.",
            reply_markup=builder.as_markup(),
        )
        await call.answer()
        return

    lines = [f"👥 <b>L{level} рефералы</b>\nРеферер: {_user_label(parent)}\n"]
    for i, item in enumerate(children, 1):
        user = item.user
        lines.append(
            f"{i}. {_user_label(user)}\n"
            f"   Имя: {user.full_name or '—'}\n"
            f"   Генераций: <b>{item.generations_count}</b> · оплат: <b>{item.paid_rub:.0f}₽</b> · "
            f"баланс: <b>{user.credits}</b> кр"
        )

    await call.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())  # type: ignore[union-attr]
    await call.answer()


# ─── Вывод средств ────────────────────────────────────────────────────────────

def withdrawal_admin_kb(request_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить выплату", callback_data=f"adm:wd:approve:{request_id}")
    builder.button(text="❌ Отклонить", callback_data=f"adm:wd:reject:{request_id}")
    builder.button(text="← Заявки", callback_data="adm:withdrawals")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "adm:withdrawals")
async def cb_withdrawals(call: CallbackQuery, session: AsyncSession) -> None:
    requests = await repo.get_pending_withdrawal_requests(session, limit=20)
    builder = InlineKeyboardBuilder()
    if not requests:
        builder.button(text="← Назад", callback_data="adm:back")
        await call.message.edit_text(  # type: ignore[union-attr]
            "💸 <b>Заявки на вывод</b>\n\nНет ожидающих заявок.",
            reply_markup=builder.as_markup(),
        )
        await call.answer()
        return

    lines = ["💸 <b>Заявки на вывод</b>\n"]
    for view in requests:
        req = view.request
        user = view.user
        lines.append(
            f"#{req.id} · <b>{req.amount_rub:.0f}₽</b> · {_user_label(user)}\n"
            f"   {req.payout_details[:80]}"
        )
        builder.button(text=f"#{req.id} · {req.amount_rub:.0f}₽ · {user.username or user.tg_id}", callback_data=f"adm:wd:view:{req.id}")
    builder.button(text="← Назад", callback_data="adm:back")
    builder.adjust(1)
    await call.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("adm:wd:view:"))
async def cb_withdrawal_view(call: CallbackQuery, session: AsyncSession) -> None:
    request_id = int(call.data.split(":")[3])  # type: ignore[union-attr]
    view = await repo.get_withdrawal_request(session, request_id)
    if not view:
        await call.answer("Заявка не найдена", show_alert=True)
        return
    req = view.request
    user = view.user
    await call.message.edit_text(  # type: ignore[union-attr]
        f"💸 <b>Заявка на вывод #{req.id}</b>\n\n"
        f"Пользователь: {_user_label(user)}\n"
        f"Имя: <b>{user.full_name or '—'}</b>\n"
        f"Сумма: <b>{req.amount_rub:.2f}₽</b>\n"
        f"Статус: <b>{req.status.value}</b>\n\n"
        f"<b>Реквизиты:</b>\n<code>{req.payout_details}</code>",
        reply_markup=withdrawal_admin_kb(req.id) if req.status == WithdrawalStatus.pending else _admin_back_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:wd:approve:"))
@router.callback_query(F.data.startswith("adm:wd:reject:"))
async def cb_withdrawal_decide(call: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    parts = call.data.split(":")  # type: ignore[union-attr]
    action = parts[2]
    request_id = int(parts[3])
    status = WithdrawalStatus.approved if action == "approve" else WithdrawalStatus.rejected
    view = await repo.set_withdrawal_status(
        session,
        request_id,
        status=status,
        admin_tg_id=call.from_user.id,
    )
    if not view:
        await call.answer("Заявка уже обработана или не найдена", show_alert=True)
        return

    req = view.request
    user = view.user
    status_text = "подтверждена" if status == WithdrawalStatus.approved else "отклонена"
    await call.message.edit_text(  # type: ignore[union-attr]
        f"✅ Заявка #{req.id} {status_text}.\n\n"
        f"Пользователь: {_user_label(user)}\n"
        f"Сумма: <b>{req.amount_rub:.2f}₽</b>",
        reply_markup=_admin_back_kb(),
    )
    try:
        await bot.send_message(
            user.tg_id,
            f"💸 Заявка на вывод #{req.id} {status_text}.\n"
            f"Сумма: <b>{req.amount_rub:.2f}₽</b>",
        )
    except Exception as e:
        logger.warning("Failed to notify withdrawal user %s: %s", user.tg_id, e)
    await call.answer("Готово")


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
