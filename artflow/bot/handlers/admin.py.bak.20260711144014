# bot/handlers/admin.py
"""
Админ-панель.
Команды: /admin, /admin_stats, /admin_price, /admin_models, /admin_ban, /admin_credits
"""
from __future__ import annotations

import csv
import html
import io
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import IsAdmin
from bot.keyboards.models import model_cost_display_text
from bot.services import admin_ai_service
from bot.services.broadcasts import SEGMENT_LABELS, deliver_broadcast, get_recipient_ids
from bot.services.maintenance_mode import is_maintenance_mode, set_maintenance_mode
from bot.states import AdminStates
from core.broadcast_scheduler import schedule_broadcast_job
from db import repository as repo
from db.models import (
    CreditLedgerEntry,
    PricePlan,
    PromoCode,
    PromoRewardType,
    User,
    WithdrawalStatus,
)
from db.repository import InsufficientReferralBalanceError

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
    builder.button(text="🤖 ИИ-админ", callback_data="admin_ai")
    builder.button(text="📘 Инструкция ИИ", callback_data="admin_ai_help")
    builder.button(text="👥 Рефералы", callback_data="adm:referrals")
    builder.button(text="💸 Заявки на вывод", callback_data="adm:withdrawals")
    builder.button(text="💳 Прайс-лист", callback_data="adm:price")
    builder.button(text="🎟 Промокоды", callback_data="adm:promos")
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


@router.message(Command("admin_ai"))
async def cmd_admin_ai(message: Message, state: FSMContext) -> None:
    await _open_admin_ai_for_message(message, state)


@router.callback_query(F.data == "admin_ai")
async def cb_admin_ai(call: CallbackQuery, state: FSMContext) -> None:
    await _open_admin_ai_for_callback(call, state)


@router.callback_query(F.data == "admin_ai_help")
async def cb_admin_ai_help(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_ai_request)
    await _edit_or_answer(call.message, _admin_ai_help_text(), reply_markup=_admin_ai_kb())  # type: ignore[arg-type]
    await call.answer()


@router.message(AdminStates.waiting_ai_request, F.text)
async def handle_admin_ai_request(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    request = (message.text or "").strip()
    data = await state.get_data()
    memory = list(data.get("admin_ai_memory") or [])
    plan = await admin_ai_service.plan_action(
        request,
        context={
            "admin_id": message.from_user.id,
            "session_memory": memory[-6:],
            "maintenance_mode": "1" if is_maintenance_mode() else "0",
        },
    )
    error = admin_ai_service.validate_plan(plan)
    if error:
        await message.answer(html.escape(error), reply_markup=_admin_ai_kb())
        return

    if plan.get("action") == "clear_context":
        await state.update_data(admin_ai_memory=[])
        await message.answer("🧹 Контекст ИИ-админа очищен.", reply_markup=_admin_ai_kb())
        return

    if admin_ai_service.plan_requires_confirmation(plan):
        await state.update_data(admin_ai_plan=plan, admin_ai_request=request)
        await state.set_state(AdminStates.confirming_ai_action)
        await message.answer(_plan_preview_text(plan), reply_markup=_admin_ai_confirm_kb())
        return

    wait = await message.answer("🤖 Выполняю...")
    try:
        result = await execute_admin_ai_plan(
            plan,
            session=session,
            admin_id=message.from_user.id,
            message=message,
        )
    except Exception as exc:
        logger.exception("admin_ai execution failed: %s", exc)
        await wait.edit_text(
            "⚠️ Не удалось выполнить действие. Ошибка записана в лог.",
            reply_markup=_admin_ai_kb(),
        )
        return

    memory = _remember_admin_ai_context(memory, request=request, plan=plan, result=result)
    await state.update_data(admin_ai_memory=memory)
    await state.set_state(AdminStates.waiting_ai_request)
    await wait.delete()
    await _send_admin_ai_text(message, "✅ Выполнено", result, reply_markup=_admin_ai_kb())


@router.message(AdminStates.waiting_ai_request)
async def handle_admin_ai_non_text(message: Message) -> None:
    await message.answer("ИИ-админ принимает только текстовые задачи.", reply_markup=_admin_ai_kb())


@router.callback_query(AdminStates.confirming_ai_action, F.data == "admin_ai_cancel")
async def cb_admin_ai_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(admin_ai_plan=None, admin_ai_request=None)
    await state.set_state(AdminStates.waiting_ai_request)
    await call.message.answer("❌ План отменён. Можно написать новую задачу.", reply_markup=_admin_ai_kb())  # type: ignore[union-attr]
    await call.answer("Отменено")


@router.callback_query(AdminStates.confirming_ai_action, F.data == "admin_ai_confirm")
async def cb_admin_ai_confirm(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    plan = data.get("admin_ai_plan")
    request = str(data.get("admin_ai_request") or "")
    memory = list(data.get("admin_ai_memory") or [])
    if not isinstance(plan, dict):
        await state.set_state(AdminStates.waiting_ai_request)
        await call.message.answer("План не найден. Напишите задачу заново.", reply_markup=_admin_ai_kb())  # type: ignore[union-attr]
        await call.answer()
        return

    error = admin_ai_service.validate_plan(plan)
    if error:
        await state.set_state(AdminStates.waiting_ai_request)
        await call.message.answer(html.escape(error), reply_markup=_admin_ai_kb())  # type: ignore[union-attr]
        await call.answer()
        return

    wait = await call.message.answer("🤖 Выполняю подтверждённый план...")  # type: ignore[union-attr]
    try:
        result = await execute_admin_ai_plan(
            plan,
            session=session,
            admin_id=call.from_user.id,
            message=call.message,  # type: ignore[arg-type]
        )
    except Exception as exc:
        logger.exception("admin_ai confirmed execution failed: %s", exc)
        await wait.edit_text(
            "⚠️ Не удалось выполнить подтверждённый план. Ошибка записана в лог.",
            reply_markup=_admin_ai_kb(),
        )
        await call.answer()
        return

    memory = _remember_admin_ai_context(memory, request=request, plan=plan, result=result)
    await state.update_data(admin_ai_plan=None, admin_ai_request=None, admin_ai_memory=memory)
    await state.set_state(AdminStates.waiting_ai_request)
    await wait.delete()
    await _send_admin_ai_text(call.message, "✅ Выполнено", result, reply_markup=_admin_ai_kb())  # type: ignore[arg-type]
    await call.answer("Готово")


@router.callback_query(F.data == "adm:promos")
async def cb_admin_promos(call: CallbackQuery) -> None:
    await call.message.answer(_promo_admin_help_text(), reply_markup=_admin_back_kb())  # type: ignore[union-attr]
    await call.answer()


@router.message(Command("admin_promo"))
async def cmd_admin_promo(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split()
    if len(parts) < 5:
        await message.answer(_promo_admin_help_text(), reply_markup=_admin_back_kb())
        return

    _, raw_code, raw_type, raw_value, *tail_parts = parts
    kind = raw_type.strip().lower()
    reward_map = {
        "credits": PromoRewardType.credits,
        "credit": PromoRewardType.credits,
        "bananas": PromoRewardType.credits,
        "banana": PromoRewardType.credits,
        "discount": PromoRewardType.discount_percent,
        "discount_percent": PromoRewardType.discount_percent,
        "discount_rub": PromoRewardType.discount_amount,
        "rub": PromoRewardType.discount_amount,
        "free": PromoRewardType.free_generation,
        "free_generation": PromoRewardType.free_generation,
    }
    reward_type = reward_map.get(kind)
    if reward_type is None:
        await message.answer("Не знаю такой тип. Доступно: credits, discount, discount_rub, free.")
        return

    percent_marker = False
    value_text = raw_value.replace(",", ".").strip()
    if value_text.endswith("%"):
        percent_marker = True
        value_text = value_text[:-1].strip()
    if tail_parts and tail_parts[0] == "%":
        percent_marker = True
        tail_parts = tail_parts[1:]
    if not tail_parts:
        await message.answer(_promo_admin_help_text(), reply_markup=_admin_back_kb())
        return

    raw_limit, *note_parts = tail_parts
    if percent_marker and reward_type == PromoRewardType.discount_amount:
        reward_type = PromoRewardType.discount_percent

    try:
        value = float(value_text)
        max_uses = int(raw_limit)
    except ValueError:
        await message.answer("Значение должно быть числом, лимит — целым числом.")
        return
    if value <= 0 or max_uses <= 0:
        await message.answer("Значение и лимит должны быть больше нуля.")
        return
    if reward_type == PromoRewardType.discount_percent and value > 100:
        await message.answer("Процент скидки должен быть от 1 до 100.")
        return

    promo = await repo.upsert_promo_code(
        session,
        code=raw_code,
        reward_type=reward_type,
        value=value,
        max_uses=max_uses,
        per_user_limit=1,
        note=" ".join(note_parts) or None,
    )
    await message.answer(
        "✅ <b>Промокод сохранён</b>\n\n"
        f"Код: <code>{promo.code}</code>\n"
        f"Тип: <b>{promo.reward_type.value}</b>\n"
        f"Значение: <b>{promo.value:g}</b>\n"
        f"Лимит: <b>{promo.max_uses}</b>\n"
        f"Использовано: <b>{promo.uses_count}</b>",
        reply_markup=_admin_back_kb(),
    )


def _user_label(user: User) -> str:
    username = f"@{user.username}" if user.username else "без username"
    return f"{username} · <code>{user.tg_id}</code>"


def _admin_back_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="← Админ-панель", callback_data="adm:back")
    return builder.as_markup()


def _admin_ai_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📘 Инструкция", callback_data="admin_ai_help")],
            [InlineKeyboardButton(text="🔙 Админ-панель", callback_data="adm:back")],
            [InlineKeyboardButton(text="🏠 Домой", callback_data="menu:main")],
        ]
    )


def _admin_ai_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнить", callback_data="admin_ai_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_ai_cancel"),
            ],
            [InlineKeyboardButton(text="🔙 Админ-панель", callback_data="adm:back")],
        ]
    )


def _admin_ai_help_text() -> str:
    return (
        "📘 <b>Инструкция: ИИ-админ</b>\n\n"
        "Как пользоваться:\n"
        "1. Откройте /admin → 🤖 ИИ-админ.\n"
        "2. Напишите задачу обычным текстом.\n"
        "3. Если действие меняет данные, подтвердите выполнение.\n\n"
        "Примеры:\n"
        "• сделай отчёт по боту\n"
        "• проанализируй последние логи\n"
        "• найди новые ИИ для генерации видео и фото\n"
        "• проверь пользователя 123456789\n"
        "• начисли 50 бананов пользователю 123456789\n"
        "• создай промокод VIP20 скидка 20 лимит 100\n"
        "• очисти контекст"
    )


async def _edit_or_answer(message: Message, text: str, *, reply_markup: InlineKeyboardMarkup) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "there is no text in the message to edit" not in str(e).lower():
            raise
        await message.answer(text, reply_markup=reply_markup)


async def _open_admin_ai_for_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    memory = list(data.get("admin_ai_memory") or [])[-8:]
    await state.clear()
    await state.set_state(AdminStates.waiting_ai_request)
    await state.update_data(admin_ai_memory=memory)
    await message.answer(
        "🤖 <b>ИИ-админ</b>\n\n"
        "Напишите задачу обычным текстом. Изменения баланса, баны, техрежим, промокоды "
        "и экспорт я сначала покажу планом для подтверждения.",
        reply_markup=_admin_ai_kb(),
    )


async def _open_admin_ai_for_callback(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    memory = list(data.get("admin_ai_memory") or [])[-8:]
    await state.clear()
    await state.set_state(AdminStates.waiting_ai_request)
    await state.update_data(admin_ai_memory=memory)
    await _edit_or_answer(
        call.message,  # type: ignore[arg-type]
        "🤖 <b>ИИ-админ</b>\n\n"
        "Напишите задачу обычным текстом. Изменения баланса, баны, техрежим, промокоды "
        "и экспорт я сначала покажу планом для подтверждения.",
        reply_markup=_admin_ai_kb(),
    )
    await call.answer()


def _compact_admin_ai_plan(plan: dict) -> dict:
    actions = [item.get("action") for item in plan.get("actions") or [] if isinstance(item, dict)]
    return {"action": plan.get("action"), "actions": actions}


def _remember_admin_ai_context(
    memory: list,
    *,
    request: str,
    plan: dict,
    result: str,
) -> list[dict]:
    compact = [
        item for item in memory[-7:]
        if isinstance(item, dict)
    ]
    compact.append(
        {
            "request": request[:500],
            "plan": _compact_admin_ai_plan(plan),
            "result": result[:1200],
        }
    )
    return compact[-8:]


def _chunk_plain_text(text: str, *, limit: int = 3600) -> list[str]:
    source = text or "Готово."
    chunks: list[str] = []
    while len(source) > limit:
        split_at = source.rfind("\n", 0, limit)
        if split_at < 1000:
            split_at = limit
        chunks.append(source[:split_at].strip())
        source = source[split_at:].strip()
    if source:
        chunks.append(source)
    return chunks or ["Готово."]


async def _send_admin_ai_text(
    message: Message,
    title: str,
    body: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    plain = f"{title}\n\n{body}" if title else body
    chunks = _chunk_plain_text(plain)
    for index, chunk in enumerate(chunks):
        await message.answer(
            html.escape(chunk),
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


def _plan_preview_text(plan: dict) -> str:
    lines = [
        "⚠️ <b>Нужно подтверждение</b>",
        "",
        html.escape(str(plan.get("summary") or "План ИИ-админа")),
        "",
    ]
    steps = plan.get("actions") or [plan]
    for index, item in enumerate(steps, start=1):
        action = str(item.get("action") or "unknown")
        params = item.get("params") or {}
        params_text = json_like(params)
        lines.append(
            f"{index}. <b>{html.escape(action)}</b>\n"
            f"   <code>{html.escape(params_text)}</code>"
        )
    return "\n".join(lines)[:3900]


def json_like(value: dict) -> str:
    if not value:
        return "{}"
    parts = [f"{key}={value[key]}" for key in sorted(value)]
    return ", ".join(parts)


def _maintenance_status_text() -> str:
    return "Техрежим включён." if is_maintenance_mode() else "Техрежим выключен."


def _format_admin_stats(total_users: float, gens_today: float, revenue_today: float) -> str:
    return (
        "Статистика\n"
        f"Пользователей: {int(total_users)}\n"
        f"Генераций сегодня: {int(gens_today)}\n"
        f"Выручка сегодня: {float(revenue_today):.2f}₽"
    )


def _format_admin_ai_user(user: User) -> str:
    created_at = user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "—"
    username = f"@{user.username}" if user.username else "—"
    full_name = user.full_name or "—"
    return (
        "Пользователь\n"
        f"TG ID: {user.tg_id}\n"
        f"Username: {username}\n"
        f"Имя: {full_name}\n"
        f"Баланс: {float(user.credits or 0):g} 💋\n"
        f"Реф. баланс: {float(user.referral_balance or 0):.2f}₽\n"
        f"Бан: {'да' if user.is_banned else 'нет'}\n"
        f"Подписка: {'активна' if user.is_subscribed else 'нет'}\n"
        f"Создан: {created_at}"
    )


def _format_promo_line(promo: PromoCode) -> str:
    status = "активен" if promo.is_active else "выключен"
    max_uses = promo.max_uses if promo.max_uses is not None else promo.max_redemptions
    return (
        f"{promo.code}: {promo.reward_type.value}, value={float(promo.value or 0):g}, "
        f"лимит={max_uses or '∞'}, использовано={promo.uses_count}, {status}"
    )


def _promo_reward_type(value: str) -> PromoRewardType:
    return {
        "credits": PromoRewardType.credits,
        "discount_percent": PromoRewardType.discount_percent,
        "discount_amount": PromoRewardType.discount_amount,
        "free_generation": PromoRewardType.free_generation,
    }[value]


async def execute_admin_ai_plan(
    plan: dict,
    *,
    session: AsyncSession,
    admin_id: int,
    message: Message,
) -> str:
    actions = plan.get("actions") or []
    if not actions and plan.get("action") == "bot_report":
        actions = [
            {"action": "stats", "params": {}},
            {"action": "maintenance_status", "params": {}},
            {"action": "list_promos", "params": {}},
            {"action": "analyze_logs", "params": {"lines": 250}},
        ]

    if actions:
        sections = []
        for index, item in enumerate(actions, start=1):
            result = await execute_admin_ai_action(
                str(item.get("action")),
                item.get("params") or {},
                session=session,
                admin_id=admin_id,
                message=message,
            )
            sections.append(f"Шаг {index}: {item.get('action')}\n{result}")
        return "\n\n".join(sections)

    return await execute_admin_ai_action(
        str(plan.get("action")),
        plan.get("params") or {},
        session=session,
        admin_id=admin_id,
        message=message,
    )


async def execute_admin_ai_action(
    action: str,
    params: dict,
    *,
    session: AsyncSession,
    admin_id: int,
    message: Message,
) -> str:
    if action == "stats":
        return _format_admin_stats(
            await repo.count_users(session),
            await repo.count_generations_today(session),
            await repo.get_revenue_today(session),
        )

    if action == "user_info":
        user = await repo.get_user_by_tg_id(session, int(params["telegram_id"]))
        return _format_admin_ai_user(user) if user else "Пользователь не найден."

    if action == "maintenance_status":
        return _maintenance_status_text()

    if action == "maintenance_set":
        set_maintenance_mode(bool(params["enabled"]))
        return _maintenance_status_text()

    if action == "list_promos":
        result = await session.execute(select(PromoCode).order_by(PromoCode.created_at.desc()).limit(20))
        promos = list(result.scalars().all())
        if not promos:
            return "Промокодов пока нет."
        return "Промокоды\n" + "\n".join(f"• {_format_promo_line(promo)}" for promo in promos)

    if action == "add_credits":
        return await _execute_credit_adjustment(
            session,
            admin_id=admin_id,
            message=message,
            telegram_id=int(params["telegram_id"]),
            amount=float(params["amount"]),
            deduct=False,
        )

    if action == "deduct_credits":
        return await _execute_credit_adjustment(
            session,
            admin_id=admin_id,
            message=message,
            telegram_id=int(params["telegram_id"]),
            amount=float(params["amount"]),
            deduct=True,
        )

    if action == "ban_user":
        ok = await repo.ban_user(session, int(params["telegram_id"]))
        return f"Пользователь {params['telegram_id']} забанен." if ok else "Пользователь не найден."

    if action == "unban_user":
        ok = await repo.unban_user(session, int(params["telegram_id"]))
        return f"Пользователь {params['telegram_id']} разбанен." if ok else "Пользователь не найден."

    if action == "create_promo":
        promo = await repo.upsert_promo_code(
            session,
            code=params["code"],
            reward_type=_promo_reward_type(params["reward_type"]),
            value=float(params["value"]),
            max_uses=params.get("max_uses"),
            per_user_limit=int(params.get("per_user_limit") or 1),
            note=f"admin_ai:{admin_id}",
            expires_at=datetime.strptime(params["expires_at"], "%Y-%m-%d") if params.get("expires_at") else None,
        )
        return "Промокод создан/обновлён.\n" + _format_promo_line(promo)

    if action == "deactivate_promo":
        promo = await repo.get_promo_code(session, params["code"])
        if not promo:
            return "Промокод не найден."
        promo.is_active = False
        await session.commit()
        return f"Промокод {promo.code} отключён."

    if action == "analyze_logs":
        return await admin_ai_service.analyze_logs(int(params.get("lines") or 250))

    if action == "research_ai":
        return await admin_ai_service.research_ai(params.get("query"))

    if action == "export_users":
        return await _export_users_csv(session, message, limit=int(params.get("limit") or 100000))

    if action == "help":
        return re.sub(r"<[^>]+>", "", _admin_ai_help_text())

    if action == "clear_context":
        return "Контекст ИИ-админа очищен."

    return "Неизвестное действие."


async def _execute_credit_adjustment(
    session: AsyncSession,
    *,
    admin_id: int,
    message: Message,
    telegram_id: int,
    amount: float,
    deduct: bool,
) -> str:
    user = await repo.get_user_by_tg_id(session, telegram_id)
    if not user:
        return "Пользователь не найден."
    action = "deduct" if deduct else "add"
    source_id = f"admin_ai:{admin_id}:{message.message_id}:{action}:{telegram_id}"
    existing = await session.execute(
        select(CreditLedgerEntry.id).where(
            CreditLedgerEntry.source_type == "admin_ai",
            CreditLedgerEntry.source_id == source_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return "Это изменение баланса уже было применено ранее."

    if deduct:
        ok = await repo.spend_credits(
            session,
            user.id,
            amount,
            entry_type="admin_ai_adjustment_deduct",
            source_type="admin_ai",
            source_id=source_id,
            note=f"AI admin deduct by {admin_id}",
        )
        if not ok:
            return f"Недостаточно баланса у пользователя {telegram_id}."
        user = await repo.get_user_by_tg_id(session, telegram_id)
        return f"Списано {amount:g} 💋 у {telegram_id}. Новый баланс: {float(user.credits or 0):g} 💋."

    new_balance = await repo.add_credits(
        session,
        user.id,
        amount,
        entry_type="admin_ai_adjustment_add",
        source_type="admin_ai",
        source_id=source_id,
        note=f"AI admin add by {admin_id}",
    )
    return f"Начислено {amount:g} 💋 пользователю {telegram_id}. Новый баланс: {float(new_balance):g} 💋."


async def _export_users_csv(session: AsyncSession, message: Message, *, limit: int) -> str:
    result = await session.execute(select(User).order_by(User.id).limit(limit))
    users = list(result.scalars().all())
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "tg_id", "username", "full_name", "credits", "is_banned", "created_at"])
    for user in users:
        writer.writerow([
            user.id,
            user.tg_id,
            user.username or "",
            user.full_name or "",
            f"{float(user.credits or 0):g}",
            int(bool(user.is_banned)),
            user.created_at.isoformat() if user.created_at else "",
        ])
    data = buffer.getvalue().encode("utf-8-sig")
    document = BufferedInputFile(data, filename=f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    await message.answer_document(document, caption=f"Экспорт пользователей: {len(users)} строк.")
    return f"CSV-экспорт отправлен файлом. Строк: {len(users)}."


def _price_done_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 К прайс-листу", callback_data="adm:price")
    builder.button(text="← Админ-панель", callback_data="adm:back")
    builder.adjust(1)
    return builder.as_markup()


def _models_done_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="⚙️ К моделям", callback_data="adm:models")
    builder.button(text="← Админ-панель", callback_data="adm:back")
    builder.adjust(1)
    return builder.as_markup()


def _credits_done_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Ещё начислить", callback_data="adm:add_credits")
    builder.button(text="← Админ-панель", callback_data="adm:back")
    builder.adjust(1)
    return builder.as_markup()


def _promo_admin_help_text() -> str:
    return (
        "🎟 <b>Промокоды</b>\n\n"
        "Создать/обновить:\n"
        "<code>/admin_promo CODE credits 20 100</code>\n"
        "<code>/admin_promo CODE discount 20 100</code>\n"
        "<code>/admin_promo CODE discount_rub 20% 100</code>\n"
        "<code>/admin_promo CODE discount_rub 20 % 100</code>\n"
        "<code>/admin_promo CODE discount_rub 300 100</code>\n"
        "<code>/admin_promo CODE free 5 100</code>\n\n"
        "Формат: <code>код тип значение лимит</code>\n"
        "• <b>credits</b> — сразу начисляет 💋\n"
        "• <b>discount</b> — % скидки на следующую оплату\n"
        "• <b>discount_rub 20%</b> — тоже % скидки, удобно для команды с символом %\n"
        "• <b>discount_rub</b> — скидка в рублях\n"
        "• <b>free</b> — бесплатная генерация как 💋-лимит"
    )


def _ban_done_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Ещё бан / разбан", callback_data="adm:ban")
    builder.button(text="← Админ-панель", callback_data="adm:back")
    builder.adjust(1)
    return builder.as_markup()


def _withdrawal_done_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="💸 К заявкам", callback_data="adm:withdrawals")
    builder.button(text="← Админ-панель", callback_data="adm:back")
    builder.adjust(1)
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
        builder.button(text="📋 Все приглашённые", callback_data="adm:ref_all")
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

    builder.button(text="📋 Все приглашённые", callback_data="adm:ref_all")
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


@router.callback_query(F.data == "adm:ref_all")
async def cb_referrals_all(call: CallbackQuery, session: AsyncSession) -> None:
    items = await repo.get_all_referral_bindings(session, limit=100)
    builder = InlineKeyboardBuilder()
    builder.button(text="← К рефералам", callback_data="adm:referrals")
    builder.button(text="← Админ-панель", callback_data="adm:back")
    builder.adjust(1)

    if not items:
        await call.message.edit_text(  # type: ignore[union-attr]
            "👥 <b>Все приглашённые</b>\n\nПока нет ни одного зафиксированного реферала.",
            reply_markup=builder.as_markup(),
        )
        await call.answer()
        return

    lines = ["👥 <b>Все приглашённые</b>\n"]
    for i, item in enumerate(items, 1):
        parent = _user_label(item.referrer) if item.referrer else "—"
        lines.append(
            f"{i}. {_user_label(item.user)}\n"
            f"   Имя: {item.user.full_name or '—'}\n"
            f"   Пригласил: {parent}\n"
            f"   Генераций: <b>{item.generations_count}</b> · оплат: <b>{item.paid_rub:.0f}₽</b>"
        )

    await call.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())  # type: ignore[arg-type]
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
        reply_markup=_withdrawal_done_kb(),
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
        reply_markup=_price_done_kb(),
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
    await message.answer(
        f"✅ Цена тарифа <code>{plan_key}</code> обновлена: {_fmt_price(new_price)}₽",
        reply_markup=_price_done_kb(),
    )


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
    await message.answer(
        f"✅ Кредиты тарифа <code>{plan_key}</code> обновлены: {new_credits}",
        reply_markup=_price_done_kb(),
    )


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
    await message.answer(
        f"✅ Название тарифа <code>{plan_key}</code> обновлено: <b>{new_label}</b>",
        reply_markup=_price_done_kb(),
    )


# ─── Стоимость моделей ────────────────────────────────────────────────────────

_MODELS_PAGE_SIZE = 12


def _model_family_key(model_key: str) -> str:
    return model_key.split("__", 1)[0]


def _variant_label(model_key: str) -> str:
    if "__" not in model_key:
        return "база"
    suffix = model_key.split("__", 1)[1]
    parts: list[str] = []
    for part in suffix.split("__"):
        if "=" in part:
            key, value = part.split("=", 1)
            if key in {"resolution", "quality"}:
                parts.append(value)
            elif key == "duration":
                parts.append(f"{value}с")
            else:
                parts.append(f"{key}={value}")
        else:
            parts.append(part)
    return " · ".join(parts)


def _model_kind_label(model_key: str) -> str:
    return "вариант" if "__" in model_key else "базовая"


def _sort_model_costs_for_admin(costs: list) -> list:
    def sort_key(mc):
        gen_type_value = getattr(mc.gen_type, "value", str(mc.gen_type))
        return (gen_type_value, _model_family_key(mc.model_key), 1 if "__" in mc.model_key else 0, mc.model_key)
    return sorted(costs, key=sort_key)


def _related_costs(costs: list, model_key: str) -> list:
    family_key = _model_family_key(model_key)
    related = [mc for mc in costs if _model_family_key(mc.model_key) == family_key]
    return _sort_model_costs_for_admin(related)


def _related_costs_text(costs: list, current_key: str) -> str:
    lines: list[str] = []
    for item in _related_costs(costs, current_key):
        marker = "👉 " if item.model_key == current_key else "• "
        label = _variant_label(item.model_key)
        price = model_cost_display_text(item).replace("💋", "кр")
        lines.append(f"{marker}<code>{label}</code> — <b>{price}</b>")
    return "\n".join(lines)


def _models_kb(costs: list, page: int) -> "InlineKeyboardMarkup":
    """Build paginated model costs keyboard."""
    costs = _sort_model_costs_for_admin(costs)
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
        label = mc.display_name[:24]
        variant_label = _variant_label(mc.model_key)

        if gen_type_value in ("video", "GenerationType.video"):
            cred_label = model_cost_display_text(mc).replace("💋", "кр")
        else:
            cred_label = f"{mc.credits:g} кр"

        item_label = f"{label} · {variant_label}"
        builder.button(
            text=f"{prefix} {item_label} — {cred_label}",
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
    base_count = sum(1 for mc in costs if "__" not in mc.model_key)
    variant_count = len(costs) - base_count
    await call.message.edit_text(
        f"⚙️ <b>Стоимость моделей</b> ({len(costs)} активных)\n"
        f"Базовых: <b>{base_count}</b> · вариантов: <b>{variant_count}</b>\n\n"
        f"Нажми для изменения:",
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
    model_key = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    model_cost = await repo.get_model_cost(session, model_key)
    if not model_cost:
        await call.answer("Модель не найдена", show_alert=True)
        return

    all_costs = await repo.get_all_model_costs(session)
    costs = [mc for mc in all_costs if "::" not in mc.model_key]
    related_text = _related_costs_text(costs, model_key)
    price_text = model_cost_display_text(model_cost).replace("💋", "кр")

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить стоимость", callback_data=f"adm:model_set_cr:{model_key}")
    builder.button(text="✏️ Изменить название", callback_data=f"adm:model_set_name:{model_key}")
    builder.button(text="← Назад", callback_data="adm:models")
    builder.adjust(1)

    await call.message.edit_text(  # type: ignore[union-attr]
        f"⚙️ <b>Редактирование стоимости модели</b>\n\n"
        f"Тип: <b>{_model_kind_label(model_cost.model_key)}</b>\n"
        f"Вариант: <code>{_variant_label(model_cost.model_key)}</code>\n"
        f"Ключ: <code>{model_cost.model_key}</code>\n"
        f"Название: <b>{model_cost.display_name}</b>\n"
        f"Стоимость: <b>{price_text}</b>\n\n"
        f"Связанные цены:\n{related_text}",
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
        await message.answer(
            f"✅ Стоимость <code>{model_key}</code> обновлена: {new_credits} кр",
            reply_markup=_models_done_kb(),
        )
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
    await message.answer(
        f"✅ Название <code>{model_key}</code> обновлено: <b>{new_name}</b>",
        reply_markup=_models_done_kb(),
    )


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
    new_balance = await repo.add_credits(session, data["target_user_id"], amount, entry_type="admin_adjustment", source_type="admin", source_id=str(message.from_user.id), note="Manual admin balance adjustment")
    await state.clear()
    await message.answer(
        f"✅ Начислено <b>{amount}</b> 💋 пользователю {data['target_tg_id']}\n"
        f"Новый баланс: <b>{new_balance}</b> 💋",
        reply_markup=_credits_done_kb(),
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
        await message.answer(
            f"✅ Разбан {tg_id}" if ok else "❌ Пользователь не найден",
            reply_markup=_ban_done_kb() if ok else None,
        )
    else:
        ok = await repo.ban_user(session, tg_id)
        await message.answer(
            f"🚫 Забанен {tg_id}" if ok else "❌ Пользователь не найден",
            reply_markup=_ban_done_kb() if ok else None,
        )
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
async def handle_broadcast(message: Message, state: FSMContext, session: AsyncSession | None = None) -> None:
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
