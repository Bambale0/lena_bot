from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.auth import web_referral_link
from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import (
    ReferralChildCard,
    ReferralStatsCard,
    ReferralWithdrawalCard,
    ReferralWithdrawalRequest,
)
from core.config import settings
from db import repository as repo
from db.session import get_session

router = APIRouter(tags=["web"])


def _rub_per_credit() -> float:
    return float(getattr(settings, "REFERRAL_EXCHANGE_RUB_PER_CREDIT", 10.0) or 10.0)


async def _notify_withdrawal_admins(user, item) -> None:
    from bot.handlers.balance import withdrawal_request_admin_kb
    from bot.i18n import t
    from main import bot

    if not bot:
        return
    admin_text = t(
        "withdraw_admin_notify",
        getattr(user, "language", "ru") or "ru",
        id=item.id,
        username=user.username or "—",
        tg_id=user.tg_id,
        full_name=user.full_name or "—",
        amount=float(item.amount_rub),
        details=item.payout_details,
    )
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, reply_markup=withdrawal_request_admin_kb(item.id))
        except (TelegramBadRequest, TelegramForbiddenError):
            continue
        except Exception:
            continue


@router.get("/referrals")
async def referrals(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")

    l1, l2, l3 = await repo.count_user_referrals(session, user.id)
    snapshot = await repo.get_user_referral_balance_snapshot(session, user.id)
    feed_reward = await repo.get_user_feed_remix_reward_rub(session, user.id)
    withdrawals = await repo.get_user_withdrawal_requests(session, user.id, limit=10)

    children: dict[str, list[dict]] = {}
    for level in (1, 2, 3):
        rows = await repo.get_referral_children(session, user.id, level=level, limit=10)
        children[f"l{level}"] = [
            ReferralChildCard(
                id=row.user.id,
                username=row.user.username,
                full_name=row.user.full_name,
                generations_count=row.generations_count,
                paid_rub=row.paid_rub,
            ).model_dump()
            for row in rows
        ]

    total = float(snapshot.total_earned if snapshot else getattr(user, "referral_balance", 0) or 0)
    pending = float(snapshot.pending_withdrawals if snapshot else 0)
    available = float(snapshot.available_to_withdraw if snapshot else total)
    payload = ReferralStatsCard(
        referral_code=user.referral_code,
        referral_link=web_referral_link(user.referral_code),
        bonus_l1_credits=float(settings.REFERRAL_L1_CREDITS),
        commission_l1=float(settings.REFERRAL_COMMISSION_L1),
        commission_l2=float(settings.REFERRAL_COMMISSION_L2),
        commission_l3=float(settings.REFERRAL_COMMISSION_L3),
        withdraw_min_rub=float(settings.REFERRAL_WITHDRAW_MIN_RUB),
        withdraw_min_credits=float(settings.REFERRAL_EXCHANGE_MIN_RUB / _rub_per_credit()),
        exchange_min_rub=float(settings.REFERRAL_EXCHANGE_MIN_RUB),
        exchange_rate_rub_per_credit=_rub_per_credit(),
        counts={"l1": l1, "l2": l2, "l3": l3},
        balance={
            "total_earned": total,
            "pending_withdrawals": pending,
            "available_to_withdraw": available,
        },
        feed_remix_reward_rub=float(feed_reward or 0),
        children=children,
        withdrawals=[ReferralWithdrawalCard.from_withdrawal(item) for item in withdrawals],
    )
    return ok(payload.model_dump())


@router.post("/referrals/withdrawals")
async def create_referral_withdrawal(
    body: ReferralWithdrawalRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")

    min_amount = float(settings.REFERRAL_WITHDRAW_MIN_RUB)
    if body.amount_rub < min_amount:
        return error_response(422, f"Минимальная сумма вывода — {min_amount:.0f}₽")
    details = body.payout_details.strip()
    if len(details) < 5 or details == "AUTO_CREDITS":
        return error_response(422, "Укажите реквизиты для вывода")
    try:
        item = await repo.create_withdrawal_request(
            session,
            user_id=user.id,
            amount_rub=body.amount_rub,
            payout_details=details,
        )
    except repo.InsufficientReferralBalanceError as exc:
        return error_response(402, f"Доступно к выводу {exc.available_amount:.2f}₽")

    await _notify_withdrawal_admins(user, item)
    return ok(ReferralWithdrawalCard.from_withdrawal(item).model_dump())


@router.post("/referrals/exchange")
async def exchange_referral_balance(
    body: ReferralWithdrawalRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")

    min_amount = float(settings.REFERRAL_EXCHANGE_MIN_RUB)
    if body.amount_rub < min_amount:
        return error_response(422, f"Минимальный обмен — {min_amount:.0f}₽")
    try:
        item = await repo.convert_referral_balance_to_credits(
            session,
            user_id=user.id,
            amount_rub=body.amount_rub,
            rub_per_credit=_rub_per_credit(),
        )
    except repo.InsufficientReferralBalanceError as exc:
        return error_response(402, f"Доступно для обмена {exc.available_amount:.2f}₽")

    return ok(ReferralWithdrawalCard.from_withdrawal(item).model_dump())
