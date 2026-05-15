# bot/handlers/balance.py
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.main_menu import back_to_menu_kb, balance_screen_kb
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from db import repository as repo
from db.repository import InsufficientReferralBalanceError
from db.models import GenerationType, ModelCost, User

logger = logging.getLogger(__name__)
router = Router(name="balance")


class WithdrawalFSM(StatesGroup):
    amount = State()
    details = State()


def referral_screen_kb(lang: str = "ru"):
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 " + ("Мои партнёры" if lang == "ru" else "My partners"), callback_data="referral:list")
    builder.button(text="💸 " + ("Запросить вывод" if lang == "ru" else "Request withdrawal"), callback_data="referral:withdraw")
    builder.button(text=t("btn_main_menu", lang), callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def withdrawal_request_admin_kb(request_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить выплату", callback_data=f"adm:wd:approve:{request_id}")
    builder.button(text="❌ Отклонить", callback_data=f"adm:wd:reject:{request_id}")
    builder.adjust(1)
    return builder.as_markup()


def _format_credit_amount(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_cost_range(costs: list[float]) -> str:
    values = sorted({_format_credit_amount(float(cost)) for cost in costs}, key=lambda item: float(item))
    if not values:
        return "—"
    if len(values) == 1:
        return f"{values[0]} 💋"
    return f"{values[0]}–{values[-1]} 💋"


def _build_balance_costs_text(lang: str, model_costs: list[ModelCost]) -> str:
    image_costs = [float(mc.credits) for mc in model_costs if mc.gen_type == GenerationType.image]
    video_costs = [float(mc.credits) for mc in model_costs if mc.gen_type == GenerationType.video]
    music_costs = [float(mc.credits) for mc in model_costs if mc.gen_type == GenerationType.music]
    midjourney_costs = [float(mc.credits) for mc in model_costs if mc.model_key.startswith("midjourney-")]

    lines = [t("balance_costs_title", lang)]
    if image_costs:
        lines.append(t("balance_costs_image", lang, amount=_format_cost_range(image_costs)))
    if video_costs:
        lines.append(t("balance_costs_video", lang, amount=_format_cost_range(video_costs)))
    if music_costs:
        lines.append(t("balance_costs_music", lang, amount=_format_cost_range(music_costs)))
    if midjourney_costs:
        lines.append(t("balance_costs_midjourney", lang, amount=_format_cost_range(midjourney_costs)))
    return "\n".join(lines)


@router.callback_query(F.data == "menu:balance")
async def cb_balance(call: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language or "ru"
    model_costs = await repo.get_all_model_costs(session)
    sub_status = (
        t("balance_sub_active", lang, date=db_user.subscription_until.strftime("%d.%m.%Y"))
        if db_user.is_subscribed and db_user.subscription_until
        else t("balance_sub_inactive", lang)
    )
    text = (
        t("balance_title", lang) + "\n\n"
        + t("balance_credits", lang, credits=db_user.credits) + "\n"
        + t("user_tg_id", lang, tg_id=db_user.tg_id) + "\n"
        + t("balance_subscription", lang, status=sub_status) + "\n\n"
        + _build_balance_costs_text(lang, model_costs) + "\n\n"
        + t("balance_topup_hint", lang)
    )
    await safe_edit_message(call.message, text, reply_markup=balance_screen_kb())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "menu:referral")
@router.callback_query(F.data == "referrals")
async def cb_referral(call: CallbackQuery, db_user: User, bot: Bot, session: AsyncSession) -> None:
    lang = db_user.language or "ru"
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={db_user.referral_code}"
    l1, l2, l3 = await repo.count_user_referrals(session, db_user.id)
    withdrawals = await repo.get_user_withdrawal_requests(session, db_user.id, limit=3)
    balance_snapshot = await repo.get_user_referral_balance_snapshot(session, db_user.id)
    feed_remix_rewards = await repo.get_user_feed_remix_reward_rub(session, db_user.id)
    withdrawal_lines = []
    for request in withdrawals:
        withdrawal_lines.append(
            f"• #{request.id}: {request.amount_rub:.0f}₽ · {request.status.value}"
        )

    earned = balance_snapshot.total_earned if balance_snapshot else float(db_user.referral_balance or 0.0)
    available = balance_snapshot.available_to_withdraw if balance_snapshot else earned
    pending = balance_snapshot.pending_withdrawals if balance_snapshot else 0.0
    text = (
        t("referral_title", lang) + "\n\n"
        + t("referral_link", lang, link=ref_link) + "\n\n"
        + t("referral_stats", lang, l1=l1, l2=l2, l3=l3) + "\n\n"
        + t("referral_earned", lang, amount=earned) + "\n"
        + t("referral_available", lang, amount=available) + "\n"
        + t("referral_withdraw_min", lang, amount=settings.REFERRAL_WITHDRAW_MIN_RUB) + "\n"
        + t("referral_feed_remix_rewards", lang, amount=feed_remix_rewards)
        + (("\n" + t("referral_pending_withdrawals", lang, amount=pending)) if pending > 0 else "")
        + "\n\n"
        + t("referral_conditions", lang,
            bonus=settings.REFERRAL_L1_CREDITS,
            l1_pct=int(settings.REFERRAL_COMMISSION_L1 * 100),
            l2_pct=int(settings.REFERRAL_COMMISSION_L2 * 100),
            l3_pct=int(settings.REFERRAL_COMMISSION_L3 * 100))
    )
    if withdrawal_lines:
        text += "\n\n💸 <b>" + ("Последние заявки на вывод" if lang == "ru" else "Recent withdrawal requests") + ":</b>\n" + "\n".join(withdrawal_lines)
    await safe_edit_message(call.message, text, reply_markup=referral_screen_kb(lang))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "referral:list")
async def cb_referral_list(call: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language or "ru"
    children = await repo.get_referral_children(session, db_user.id, level=1, limit=30)

    if not children:
        text = (
            "👥 <b>Мои партнёры</b>\n\n"
            "Пока здесь пусто.\n\n"
            "Партнёр появится в списке, если человек:\n"
            "• открыл бота именно по твоей ссылке\n"
            "• запустил бота через <code>/start</code> с твоим кодом\n"
            "• не был зарегистрирован раньше\n\n"
            "Если человек уже был в боте до этого, новым партнёром он не станет."
        ) if lang == "ru" else (
            "👥 <b>My partners</b>\n\n"
            "Nothing here yet.\n\n"
            "A person appears here if they:\n"
            "• open the bot using your partner link\n"
            "• start the bot with your <code>/start</code> code\n"
            "• were not registered before\n\n"
            "If they had already used the bot earlier, they will not count as a new partner."
        )
        await safe_edit_message(call.message, text, reply_markup=referral_screen_kb(lang))  # type: ignore[arg-type]
        await safe_answer_callback(call)
        return

    lines: list[str] = []
    for child in children:
        user = child.user
        name = f"@{user.username}" if user.username else (user.full_name or f"ID {user.tg_id}")
        joined = user.created_at.strftime("%d.%m.%Y") if user.created_at else "—"
        if child.paid_rub > 0:
            status = f"💳 оплатил {child.paid_rub:.0f}₽" if lang == "ru" else f"💳 paid {child.paid_rub:.0f}₽"
        elif child.generations_count > 0:
            status = f"🎨 активен · {child.generations_count} генерац." if lang == "ru" else f"🎨 active · {child.generations_count} generations"
        else:
            status = "👋 зашёл в бота" if lang == "ru" else "👋 opened the bot"
        lines.append(
            f"• <b>{name}</b>\n"
            f"  <code>{user.tg_id}</code> · {joined}\n"
            f"  {status}"
        )

    title = "👥 <b>Мои партнёры</b>" if lang == "ru" else "👥 <b>My partners</b>"
    hint = "\n\nПоказываю прямых партнёров по твоей ссылке." if lang == "ru" else "\n\nShowing direct partners from your link."
    text = title + "\n\n" + "\n\n".join(lines) + hint
    await safe_edit_message(call.message, text, reply_markup=referral_screen_kb(lang))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "referral:withdraw")
async def cb_referral_withdraw(
    call: CallbackQuery,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
) -> None:
    lang = db_user.language or "ru"
    balance_snapshot = await repo.get_user_referral_balance_snapshot(session, db_user.id)
    available = balance_snapshot.available_to_withdraw if balance_snapshot else 0.0
    min_amount = settings.REFERRAL_WITHDRAW_MIN_RUB
    if available + 1e-9 < min_amount:
        await call.message.answer(  # type: ignore[union-attr]
            t("withdraw_unavailable", lang, min_amount=min_amount),
            reply_markup=back_to_menu_kb(),
        )
        await call.answer()
        return
    await state.set_state(WithdrawalFSM.amount)
    await call.message.answer(  # type: ignore[union-attr]
        t("withdraw_title", lang) + "\n\n" + t("withdraw_amount_prompt", lang, available=available, min_amount=min_amount),
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.message(WithdrawalFSM.amount, F.text)
async def handle_withdraw_amount(
    message: Message,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
) -> None:
    lang = db_user.language or "ru"
    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        await message.answer(t("withdraw_amount_invalid", lang), reply_markup=back_to_menu_kb())
        return
    if amount <= 0:
        await message.answer(t("withdraw_amount_zero", lang), reply_markup=back_to_menu_kb())
        return
    min_amount = settings.REFERRAL_WITHDRAW_MIN_RUB
    if amount + 1e-9 < min_amount:
        await message.answer(t("withdraw_amount_min", lang, min_amount=min_amount), reply_markup=back_to_menu_kb())
        return
    balance_snapshot = await repo.get_user_referral_balance_snapshot(session, db_user.id)
    available = balance_snapshot.available_to_withdraw if balance_snapshot else 0.0
    if amount > available + 1e-9:
        await message.answer(
            t("withdraw_amount_exceeds", lang, available=available),
            reply_markup=back_to_menu_kb(),
        )
        return
    await state.update_data(withdraw_amount=amount)
    await state.set_state(WithdrawalFSM.details)
    await message.answer(
        t("withdraw_details_prompt", lang),
        reply_markup=back_to_menu_kb(),
    )


@router.message(WithdrawalFSM.details, F.text)
async def handle_withdraw_details(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    lang = db_user.language or "ru"
    details = (message.text or "").strip()
    if len(details) < 5:
        await message.answer(t("withdraw_details_short", lang), reply_markup=back_to_menu_kb())
        return
    data = await state.get_data()
    amount = float(data["withdraw_amount"])
    try:
        request = await repo.create_withdrawal_request(
            session,
            user_id=db_user.id,
            amount_rub=amount,
            payout_details=details,
        )
    except InsufficientReferralBalanceError as exc:
        await state.clear()
        await message.answer(
            t("withdraw_amount_exceeds", lang, available=exc.available_amount),
            reply_markup=back_to_menu_kb(),
        )
        return
    await state.clear()
    await message.answer(
        t("withdraw_created", lang, id=request.id, amount=amount),
        reply_markup=back_to_menu_kb(),
    )

    admin_text = t(
        "withdraw_admin_notify", lang,
        id=request.id,
        username=db_user.username or "—",
        tg_id=db_user.tg_id,
        full_name=db_user.full_name or "—",
        amount=amount,
        details=details,
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
    lang = db_user.language or "ru"
    history = await repo.get_user_history(session, db_user.id, limit=10)

    if not history:
        await call.message.edit_text(  # type: ignore[union-attr]
            t("history_empty", lang),
            reply_markup=back_to_menu_kb(),
        )
        await call.answer()
        return

    lines = [t("history_title", lang) + "\n"]
    for i, gen in enumerate(history, 1):
        icon = "🎨" if gen.gen_type == GenerationType.image else "🎬"
        status_icon = {"done": "✅", "pending": "⏳", "failed": "❌", "processing": "🔄"}.get(
            gen.status.value, "❓"
        )
        lines.append(
            f"{i}. {icon} {status_icon} <code>{gen.model}</code>\n"
            f"   <i>{gen.prompt[:60]}{'...' if len(gen.prompt) > 60 else ''}</i>\n"
            f"   -{gen.credits_spent} 💋"
        )

    await call.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines), reply_markup=back_to_menu_kb()
    )
    await call.answer()
