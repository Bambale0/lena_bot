# bot/handlers/admin.py
"""
Админ-панель.
Команды: /admin, /admin_stats, /admin_price, /admin_models, /admin_ban, /admin_credits
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import IsAdmin
from bot.services.broadcasts import SEGMENT_LABELS, deliver_broadcast, get_recipient_ids
from core.broadcast_scheduler import schedule_broadcast_job
from db import repository as repo
from db.repository import InsufficientReferralBalanceError
from db.models import PricePlan, User, WithdrawalStatus

logger = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _fmt_price(price: float) -> str:
    """'199' для целых, '99.5' для дробных — без лишних нулей."""
    return f"{price:g}"


class AdminFSM(StatesGroup):
    # Price plan editing
    edit_price_label = State()
    edit_price_key = State()
    edit_price_credits = State()
    edit_price_rub = State()
    new_price_credits = State()
    new_price_rub = State()
    # Model cost editing
    edit_model_display_name = State()
    edit_model_key = State()
    edit_model_credits = State()
    # Credits management
    await_credits_tg_id = State()
    await_credits_amount = State()
    # Ban
    await_ban_tg_id = State()
    # Broadcast
    await_broadcast_text = State()
    await_broadcast_segment = State()
    await_broadcast_schedule = State()
    await_broadcast_datetime = State()
    confirm_broadcast = State()


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


BROADCAST_TZ = ZoneInfo("Europe/Moscow")


def _broadcast_preview_kb(*, scheduled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Запланировать" if scheduled else "✅ Запустить", callback_data="adm:broadcast:send")
    builder.button(text="❌ Отмена", callback_data="adm:broadcast:cancel")
    builder.adjust(1)
    return builder.as_markup()


def _broadcast_entry_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="adm:broadcast:cancel")
    return builder.as_markup()


def _broadcast_segment_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Все", callback_data="adm:broadcast:segment:all")
    builder.button(text="💳 Платившие", callback_data="adm:broadcast:segment:paid")
    builder.button(text="🆕 Новые 7д", callback_data="adm:broadcast:segment:new")
    builder.button(text="⚡ Активные 14д", callback_data="adm:broadcast:segment:active")
    builder.button(text="❌ Отмена", callback_data="adm:broadcast:cancel")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def _broadcast_schedule_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Сейчас", callback_data="adm:broadcast:when:now")
    builder.button(text="⏰ Через 10 мин", callback_data="adm:broadcast:when:delay:10")
    builder.button(text="⏰ Через 1 час", callback_data="adm:broadcast:when:delay:60")
    builder.button(text="🗓 Указать время", callback_data="adm:broadcast:when:custom")
    builder.button(text="❌ Отмена", callback_data="adm:broadcast:cancel")
    builder.adjust(1)
    return builder.as_markup()


def _format_broadcast_datetime(dt: datetime) -> str:
    return dt.astimezone(BROADCAST_TZ).strftime("%d.%m.%Y %H:%M MSK")


def _parse_broadcast_datetime(raw: str) -> datetime | None:
    raw = raw.strip()
    now = datetime.now(BROADCAST_TZ)
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m %H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if fmt == "%d.%m %H:%M":
            parsed = parsed.replace(year=now.year)
        parsed = parsed.replace(tzinfo=BROADCAST_TZ)
        if parsed <= now and fmt == "%d.%m %H:%M":
            parsed = parsed.replace(year=now.year + 1)
        if parsed <= now:
            return None
        return parsed
    return None


async def _show_broadcast_preview(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    segment = str(data.get("broadcast_segment", "all"))
    recipients = int(data.get("broadcast_recipient_count", 0))
    scheduled_for_iso = data.get("broadcast_scheduled_for")
    scheduled = bool(scheduled_for_iso)

    text = (
        "👀 Предпросмотр рассылки\n"
        f"Сегмент: <b>{SEGMENT_LABELS.get(segment, segment)}</b>\n"
        f"Получателей: <b>{recipients}</b>\n"
    )
    if scheduled_for_iso:
        text += f"Время: <b>{_format_broadcast_datetime(datetime.fromisoformat(str(scheduled_for_iso)))}</b>\n"
    text += "\nНиже — сообщение как его увидят пользователи."

    await target.answer(text)
    await target.bot.copy_message(
        chat_id=target.chat.id,
        from_chat_id=int(data["broadcast_source_chat_id"]),
        message_id=int(data["broadcast_source_message_id"]),
    )
    await target.answer(
        "Если всё ок — подтверждай.",
        reply_markup=_broadcast_preview_kb(scheduled=scheduled),
    )


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
    try:
        view = await repo.set_withdrawal_status(
            session,
            request_id,
            status=status,
            admin_tg_id=call.from_user.id,
        )
    except InsufficientReferralBalanceError as exc:
        await call.answer(
            f"Недостаточно реферального баланса у пользователя: доступно {exc.available_amount:.2f}₽",
            show_alert=True,
        )
        return
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
    result = await session.execute(select(PricePlan).order_by(PricePlan.sort_order))
    all_plans = list(result.scalars().all())

    builder = InlineKeyboardBuilder()
    for plan in all_plans:
        status = "✅" if plan.is_active else "❌"
        builder.button(
            text=f"{status} {plan.label} — {_fmt_price(plan.price_rub)}₽ / {plan.credits} cr",
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
    builder.button(text="✏️ Изменить название", callback_data=f"adm:price_set_label:{plan.key}")
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
        f"Цена: {_fmt_price(plan.price_rub)}₽\n"
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


@router.callback_query(F.data == "adm:price_new")
async def cb_price_new_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminFSM.new_price_credits)
    await call.message.answer(  # type: ignore[union-attr]
        "➕ <b>Новый тариф</b>\n\n"
        "Введи количество кредитов.\n"
        "Например: <code>500</code>"
    )
    await call.answer()


@router.message(AdminFSM.new_price_credits)
async def handle_new_price_credits(message: Message, state: FSMContext) -> None:
    try:
        credits = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Введи целое число кредитов, например: <code>500</code>")
        return
    if credits <= 0:
        await message.answer("Количество кредитов должно быть больше нуля.")
        return

    await state.update_data(new_price_credits=credits)
    await state.set_state(AdminFSM.new_price_rub)
    await message.answer(
        f"Кредиты: <b>{credits}</b>\n\n"
        "Теперь введи цену в рублях.\n"
        "Например: <code>799</code>"
    )


@router.message(AdminFSM.new_price_rub)
async def handle_new_price_rub(message: Message, session: AsyncSession, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        price_rub = float(raw)
    except ValueError:
        await message.answer("Введи цену числом, например: <code>799</code>")
        return
    if price_rub <= 0:
        await message.answer("Цена должна быть больше нуля.")
        return

    data = await state.get_data()
    credits = float(data["new_price_credits"])
    base_key = f"credits_{credits}"
    plan_key = base_key
    candidate = await repo.get_price_plan_by_key(session, plan_key)
    if candidate:
        suffix = int(price_rub)
        plan_key = f"{base_key}_{suffix}"
        # ensure uniqueness if same price also exists
        while await repo.get_price_plan_by_key(session, plan_key):
            plan_key = f"{base_key}_{suffix}_{id(plan_key) % 10000}"

    max_result = await session.execute(select(func.max(PricePlan.sort_order)))
    sort_order = (max_result.scalar_one_or_none() or 0) + 1

    plan = await repo.upsert_price_plan(
        session,
        key=plan_key,
        label=f"{credits} cr",
        credits=credits,
        price_rub=price_rub,
        sort_order=sort_order,
    )
    await state.clear()
    await message.answer(
        f"✅ Новый тариф создан\n\n"
        f"Ключ: <code>{plan.key}</code>\n"
        f"Название: <b>{plan.label}</b>\n"
        f"Кредиты: <b>{plan.credits}</b>\n"
        f"Цена: <b>{_fmt_price(plan.price_rub)}₽</b>",
    )


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
        new_price = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Введи число (например: 299)")
        return
    if new_price <= 0:
        await message.answer("Цена должна быть больше нуля.")
        return

    data = await state.get_data()
    plan_key = data["edit_plan_key"]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if plan:
        plan.price_rub = new_price
        await session.commit()
    await state.clear()
    await message.answer(f"✅ Цена тарифа <code>{plan_key}</code> обновлена: {_fmt_price(new_price)}₽")


@router.callback_query(F.data.startswith("adm:price_set_cr:"))
async def cb_price_set_credits_start(call: CallbackQuery, state: FSMContext) -> None:
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    await state.set_state(AdminFSM.edit_price_credits)
    await state.update_data(edit_plan_key=plan_key)
    await call.message.answer(f"Введи новое количество кредитов для <code>{plan_key}</code>:")
    await call.answer()


@router.callback_query(F.data.startswith("adm:price_set_label:"))
async def cb_price_set_label_start(call: CallbackQuery, state: FSMContext) -> None:
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    await state.set_state(AdminFSM.edit_price_label)
    await state.update_data(edit_plan_key=plan_key)
    await call.message.answer(
        "Введи новое название тарифа.\n"
        "Например: <code>10 сек · Pro</code> или <code>500 cr</code>"
    )
    await call.answer()


@router.message(AdminFSM.edit_price_credits)
async def handle_price_credits(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        new_credits = float(message.text.strip().replace(",", "."))  # type: ignore[union-attr]
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


@router.message(AdminFSM.edit_price_label)
async def handle_price_label(message: Message, session: AsyncSession, state: FSMContext) -> None:
    new_label = (message.text or "").strip()
    if not new_label:
        await message.answer("Название не должно быть пустым.")
        return

    data = await state.get_data()
    plan_key = data["edit_plan_key"]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if plan:
        plan.label = new_label
        await session.commit()
    await state.clear()
    await message.answer(f"✅ Название тарифа <code>{plan_key}</code> обновлено: <b>{new_label}</b>")


# ─── Стоимость моделей ────────────────────────────────────────────────────────

_MODELS_PAGE_SIZE = 12


def _models_kb(costs: list, page: int) -> "InlineKeyboardMarkup":
    """Build paginated model costs keyboard."""
    total = len(costs)
    total_pages = max(1, (total + _MODELS_PAGE_SIZE - 1) // _MODELS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _MODELS_PAGE_SIZE
    chunk = costs[start : start + _MODELS_PAGE_SIZE]

    builder = InlineKeyboardBuilder()
    for mc in chunk:
        # Use gen_type emoji prefix
        gen_type_value = getattr(mc.gen_type, "value", str(mc.gen_type))
        if gen_type_value in ("image", "GenerationType.image"):
            prefix = "🖼"
        elif gen_type_value in ("music", "GenerationType.music"):
            prefix = "🎵"
        else:
            prefix = "🎬"
        label = mc.display_name[:30]
        
        # Для видео-моделей всегда показываем кр/сек
        # Если в model_key есть resolution, добавляем пометку в скобках
        if gen_type_value in ("video", "GenerationType.video"):
            # Парсим resolution из ключа если есть
            res_match = re.search(r'__resolution=(\w+)', mc.model_key)
            if res_match:
                resolution = res_match.group(1)
                # Убираем " · за сек" из названия, если есть
                label = label.replace(" · за сек", "").replace(f" · {resolution}", "")
                cred_label = f"{mc.credits} кр/сек ({resolution})"
            else:
                cred_label = f"{mc.credits} кр/сек"
        else:
            cred_label = f"{mc.credits} кр"
            
        builder.button(
            text=f"{prefix} {label} — {cred_label}",
            callback_data=f"adm:model_edit:{mc.model_key}",
        )
    builder.adjust(1)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Пред", callback_data=f"adm:models_pg:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="adm:noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="След ▶️", callback_data=f"adm:models_pg:{page + 1}"))
    builder.row(*nav_row)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="adm:back"))
    return builder.as_markup()


@router.callback_query(F.data == "adm:models")
async def cb_models(call: CallbackQuery, session: AsyncSession) -> None:
    # Filter: only show clean model keys (no "::" legacy separator)
    all_costs = await repo.get_all_model_costs(session)
    costs = [mc for mc in all_costs if "::" not in mc.model_key]
    await call.message.edit_text(
        f"⚙️ <b>Стоимость моделей</b> ({len(costs)} активных)\n\nНажми для изменения:",
        reply_markup=_models_kb(costs, 0),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:models_pg:"))
async def cb_models_page(call: CallbackQuery, session: AsyncSession) -> None:
    page = int(call.data.split(":")[2])
    all_costs = await repo.get_all_model_costs(session)
    costs = [mc for mc in all_costs if "::" not in mc.model_key]
    await call.message.edit_reply_markup(reply_markup=_models_kb(costs, page))
    await call.answer()


@router.callback_query(F.data == "adm:noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data.startswith("adm:model_edit:"))
async def cb_model_edit(call: CallbackQuery, session: AsyncSession) -> None:
    model_key = call.data.split(":")[2]  # type: ignore[union-attr]
    model_cost = await repo.get_model_cost(session, model_key)
    if not model_cost:
        await call.answer("Модель не найдена", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить стоимость", callback_data=f"adm:model_set_cr:{model_key}")
    builder.button(text="✏️ Изменить название", callback_data=f"adm:model_set_name:{model_key}")
    builder.button(text="← Назад", callback_data="adm:models")
    builder.adjust(1)

    await call.message.edit_text(  # type: ignore[union-attr]
        f"⚙️ <b>Редактирование стоимости модели</b>\n\n"
        f"Ключ: <code>{model_cost.model_key}</code>\n"
        f"Название: <b>{model_cost.display_name}</b>\n"
        f"Стоимость: <b>{model_cost.credits}</b> кр",
        reply_markup=builder.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:model_set_cr:"))
async def cb_model_set_credits_start(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":")[2]  # type: ignore[union-attr]
    await state.set_state(AdminFSM.edit_model_credits)
    await state.update_data(edit_model_key=model_key)
    await call.message.answer(f"Введи новую стоимость в кредитах для <code>{model_key}</code>:")
    await call.answer()


@router.callback_query(F.data.startswith("adm:model_set_name:"))
async def cb_model_set_name_start(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":")[2]  # type: ignore[union-attr]
    await state.set_state(AdminFSM.edit_model_display_name)
    await state.update_data(edit_model_key=model_key)
    await call.message.answer(
        "Введи новое название позиции.\n"
        "Например: <code>⚡ Kling 3.0 · 10 сек · Pro</code>"
    )
    await call.answer()


@router.message(AdminFSM.edit_model_credits)
async def handle_model_credits(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        new_credits = float(message.text.strip().replace(",", "."))  # type: ignore[union-attr]
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


@router.message(AdminFSM.edit_model_display_name)
async def handle_model_display_name(message: Message, session: AsyncSession, state: FSMContext) -> None:
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("Название не должно быть пустым.")
        return

    data = await state.get_data()
    model_key = data["edit_model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    if not model_cost:
        await state.clear()
        await message.answer("❌ Модель не найдена")
        return

    model_cost.display_name = new_name
    await session.commit()
    await state.clear()
    await message.answer(f"✅ Название <code>{model_key}</code> обновлено: <b>{new_name}</b>")


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
        amount = float(message.text.strip().replace(",", "."))  # type: ignore[union-attr]
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
    await call.message.answer(  # type: ignore[union-attr]
        "📢 Отправь сообщение для рассылки.\n\n"
        "Можно текст, фото, видео, документ и подпись. Потом выберешь сегмент и время отправки.",
        reply_markup=_broadcast_entry_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "adm:broadcast:cancel")
async def cb_broadcast_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer("❌ Рассылка отменена.", reply_markup=admin_menu_kb())  # type: ignore[union-attr]
    await call.answer()


@router.message(Command("cancel"))
async def cmd_cancel_admin_flow(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if not current_state:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=admin_menu_kb())


@router.message(AdminFSM.await_broadcast_text)
async def handle_broadcast(message: Message, state: FSMContext) -> None:
    await state.update_data(
        broadcast_source_chat_id=message.chat.id,
        broadcast_source_message_id=message.message_id,
    )
    await state.set_state(AdminFSM.await_broadcast_segment)
    await message.answer(
        "Выбери аудиторию для рассылки:",
        reply_markup=_broadcast_segment_kb(),
    )


@router.callback_query(AdminFSM.await_broadcast_segment, F.data.startswith("adm:broadcast:segment:"))
async def cb_broadcast_segment(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    segment = str(call.data).split(":")[-1]
    tg_ids = await get_recipient_ids(session, segment)
    await state.update_data(
        broadcast_segment=segment,
        broadcast_recipient_count=len(tg_ids),
    )
    await state.set_state(AdminFSM.await_broadcast_schedule)
    await call.message.answer(  # type: ignore[union-attr]
        f"Аудитория: <b>{SEGMENT_LABELS.get(segment, segment)}</b>\n"
        f"Получателей сейчас: <b>{len(tg_ids)}</b>\n\n"
        "Когда отправить?",
        reply_markup=_broadcast_schedule_kb(),
    )
    await call.answer()


@router.callback_query(AdminFSM.await_broadcast_schedule, F.data == "adm:broadcast:when:now")
async def cb_broadcast_when_now(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(broadcast_scheduled_for=None)
    await state.set_state(AdminFSM.confirm_broadcast)
    await _show_broadcast_preview(call.message, state)  # type: ignore[arg-type]
    await call.answer()


@router.callback_query(AdminFSM.await_broadcast_schedule, F.data.startswith("adm:broadcast:when:delay:"))
async def cb_broadcast_when_delay(call: CallbackQuery, state: FSMContext) -> None:
    minutes = int(str(call.data).split(":")[-1])
    scheduled_for = datetime.now(BROADCAST_TZ) + timedelta(minutes=minutes)
    await state.update_data(broadcast_scheduled_for=scheduled_for.isoformat())
    await state.set_state(AdminFSM.confirm_broadcast)
    await _show_broadcast_preview(call.message, state)  # type: ignore[arg-type]
    await call.answer()


@router.callback_query(AdminFSM.await_broadcast_schedule, F.data == "adm:broadcast:when:custom")
async def cb_broadcast_when_custom(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminFSM.await_broadcast_datetime)
    await call.message.answer(  # type: ignore[union-attr]
        "Введи дату и время по Москве.\n"
        "Формат: <code>12.05.2026 21:30</code> или <code>12.05 21:30</code>",
        reply_markup=_broadcast_entry_kb(),
    )
    await call.answer()


@router.message(AdminFSM.await_broadcast_datetime, F.text)
async def handle_broadcast_datetime(message: Message, state: FSMContext) -> None:
    parsed = _parse_broadcast_datetime(message.text or "")
    if not parsed:
        await message.answer(
            "Не смог понять дату. Используй формат <code>12.05.2026 21:30</code> или <code>12.05 21:30</code>.",
            reply_markup=_broadcast_entry_kb(),
        )
        return
    await state.update_data(broadcast_scheduled_for=parsed.isoformat())
    await state.set_state(AdminFSM.confirm_broadcast)
    await _show_broadcast_preview(message, state)


@router.callback_query(AdminFSM.confirm_broadcast, F.data == "adm:broadcast:send")
async def cb_broadcast_send(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    source_chat_id = data.get("broadcast_source_chat_id")
    source_message_id = data.get("broadcast_source_message_id")
    segment = str(data.get("broadcast_segment", "all"))
    scheduled_for_iso = data.get("broadcast_scheduled_for")

    if not source_chat_id or not source_message_id:
        await state.clear()
        await call.message.answer("❌ Не удалось запустить рассылку. Попробуй заново.", reply_markup=admin_menu_kb())  # type: ignore[union-attr]
        await call.answer()
        return

    if scheduled_for_iso:
        job_id = await schedule_broadcast_job(
            source_chat_id=int(source_chat_id),
            source_message_id=int(source_message_id),
            segment=segment,
            scheduled_for=datetime.fromisoformat(str(scheduled_for_iso)),
            created_by_chat_id=call.from_user.id,
        )
        await state.clear()
        await call.message.answer(  # type: ignore[union-attr]
            "✅ Рассылка запланирована.\n"
            f"ID: <code>{job_id}</code>\n"
            f"Сегмент: <b>{SEGMENT_LABELS.get(segment, segment)}</b>\n"
            f"Время: <b>{_format_broadcast_datetime(datetime.fromisoformat(str(scheduled_for_iso)))}</b>",
            reply_markup=admin_menu_kb(),
        )
        await call.answer()
        return

    tg_ids = await get_recipient_ids(session, segment)
    await state.clear()
    status_msg = await call.message.answer(  # type: ignore[union-attr]
        f"📢 Отправляю {len(tg_ids)} пользователям..."
    )

    sent, failed, errors = await deliver_broadcast(
        bot=call.bot,
        tg_ids=tg_ids,
        source_chat_id=int(source_chat_id),
        source_message_id=int(source_message_id),
        status_msg=status_msg,
    )

    report = (
        "✅ Рассылка завершена\n"
        f"Сегмент: <b>{SEGMENT_LABELS.get(segment, segment)}</b>\n"
        f"Доставлено: {sent} · Ошибок: {failed}"
    )
    if errors:
        report += "\n\nПервые ошибки:\n" + "\n".join(f"• {item}" for item in errors)

    await status_msg.edit_text(report, reply_markup=admin_menu_kb())
    await call.answer()
