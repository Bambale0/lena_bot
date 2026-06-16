from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Date, case, cast, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.auth import web_referral_link
from api.web.billing import enabled_payment_methods
from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import enum_value, iso_datetime
from core.config import settings
from db import repository as repo
from db.models import (
    CreditLedgerEntry,
    Generation,
    GenerationStatus,
    GenerationType,
    ModelCost,
    PricePlan,
    PromptStatus,
    ReferralWithdrawalRequest,
    Transaction,
    TransactionStatus,
    User,
    UserPrompt,
    WithdrawalStatus,
)
from db.repository import InsufficientReferralBalanceError
from db.session import get_session

router = APIRouter(tags=["web-admin"])


class AdminCreditAdjustmentRequest(BaseModel):
    amount: float = Field(..., ge=-100_000, le=100_000)
    note: str | None = Field(default=None, max_length=500)


class AdminBanRequest(BaseModel):
    banned: bool


class AdminModelCostUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    credits: float | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None


class AdminPricePlanUpdateRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    credits: float | None = Field(default=None, gt=0, le=1_000_000)
    price_rub: float | None = Field(default=None, gt=0, le=100_000_000)
    price_stars: int | None = Field(default=None, ge=1, le=1_000_000)
    sort_order: int | None = Field(default=None, ge=-10_000, le=10_000)
    is_active: bool | None = None


class AdminGenerationFailRequest(BaseModel):
    error: str = Field(default="Marked failed by web admin", max_length=500)
    refund: bool = True


class AdminWithdrawalActionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    note: str | None = Field(default=None, max_length=500)


def _is_admin(user: Any) -> bool:
    try:
        tg_id = int(getattr(user, "tg_id", 0) or 0)
    except (TypeError, ValueError):
        tg_id = 0
    return bool(user and tg_id in set(settings.ADMIN_IDS or []))


def _admin_error(user: Any):
    if user is None:
        return error_response(401, "Authentication required")
    if not _is_admin(user):
        return error_response(403, "Admin access required")
    return None


async def _scalar(session: AsyncSession, statement, default: Any = 0) -> Any:
    value = (await session.execute(statement)).scalar_one_or_none()
    return default if value is None else value


def _date_key(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _date_range(days: int) -> list[str]:
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _user_card(user: User, stats: dict[str, Any] | None = None) -> dict:
    stats = stats or {}
    return {
        "id": user.id,
        "tg_id": user.tg_id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "credits": float(user.credits or 0),
        "referral_balance": float(user.referral_balance or 0),
        "referral_code": user.referral_code,
        "referral_link": web_referral_link(user.referral_code),
        "language": user.language,
        "is_banned": bool(user.is_banned),
        "is_admin": _is_admin(user),
        "created_at": iso_datetime(user.created_at),
        "generations_count": int(stats.get("generations_count") or 0),
        "credits_spent": float(stats.get("credits_spent") or 0),
        "paid_rub": _money(stats.get("paid_rub")),
        "last_generation_at": iso_datetime(stats.get("last_generation_at")),
    }


def _generation_card(gen: Generation, user: User | None = None) -> dict:
    return {
        "id": gen.id,
        "user_id": gen.user_id,
        "user": _user_mini(user),
        "model": gen.model,
        "gen_type": enum_value(gen.gen_type),
        "status": enum_value(gen.status),
        "prompt": gen.prompt if not gen.source_feed_gen_id else "",
        "prompt_hidden": bool(gen.source_feed_gen_id),
        "task_id": gen.task_id,
        "credits_spent": float(gen.credits_spent or 0),
        "result_url": gen.result_url,
        "is_public_feed": bool(gen.is_public_feed),
        "is_prompt_library": bool(gen.is_prompt_library),
        "source_feed_gen_id": gen.source_feed_gen_id,
        "error": gen.error_msg,
        "created_at": iso_datetime(gen.created_at),
        "finished_at": iso_datetime(gen.finished_at),
    }


def _transaction_card(tx: Transaction, user: User | None = None) -> dict:
    return {
        "id": tx.id,
        "user_id": tx.user_id,
        "user": _user_mini(user),
        "amount_rub": _money(tx.amount_rub),
        "credits": float(tx.credits or 0),
        "provider": enum_value(tx.provider),
        "status": enum_value(tx.status),
        "external_id": tx.external_id,
        "created_at": iso_datetime(tx.created_at),
    }


def _user_mini(user: User | None) -> dict | None:
    if not user:
        return None
    return {
        "id": user.id,
        "tg_id": user.tg_id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "credits": float(user.credits or 0),
        "is_banned": bool(user.is_banned),
    }


def _model_cost_card(item: ModelCost) -> dict:
    return {
        "id": item.id,
        "model_key": item.model_key,
        "display_name": item.display_name,
        "gen_type": enum_value(item.gen_type),
        "credits": float(item.credits or 0),
        "is_active": bool(item.is_active),
    }


def _price_plan_card(item: PricePlan) -> dict:
    return {
        "id": item.id,
        "key": item.key,
        "label": item.label,
        "credits": float(item.credits or 0),
        "price_rub": _money(item.price_rub),
        "price_stars": item.price_stars,
        "is_active": bool(item.is_active),
        "sort_order": int(item.sort_order or 0),
    }


def _withdrawal_card(item: ReferralWithdrawalRequest, user: User | None = None) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "user": _user_mini(user),
        "amount_rub": _money(item.amount_rub),
        "payout_details": item.payout_details,
        "status": enum_value(item.status),
        "admin_tg_id": item.admin_tg_id,
        "admin_note": item.admin_note,
        "created_at": iso_datetime(item.created_at),
        "reviewed_at": iso_datetime(item.reviewed_at),
    }


async def _count_by_enum(session: AsyncSession, model, column) -> dict[str, int]:
    result = await session.execute(select(column, func.count()).select_from(model).group_by(column))
    return {enum_value(key): int(value or 0) for key, value in result.all()}


async def _daily_series(session: AsyncSession, column, table_model, *, days: int, value_expr=None, filters=()) -> list[dict]:
    start = datetime.now(timezone.utc) - timedelta(days=days - 1)
    day_expr = cast(column, Date)
    metric = value_expr if value_expr is not None else func.count()
    statement = (
        select(day_expr.label("day"), func.coalesce(metric, 0))
        .select_from(table_model)
        .where(column >= start, *filters)
        .group_by(day_expr)
        .order_by(day_expr)
    )
    rows = {_date_key(day): float(value or 0) for day, value in (await session.execute(statement)).all()}
    return [{"date": day, "value": rows.get(day, 0)} for day in _date_range(days)]


async def _admin_overview_payload(session: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    totals = {
        "users": int(await _scalar(session, select(func.count()).select_from(User))),
        "banned_users": int(await _scalar(session, select(func.count()).select_from(User).where(User.is_banned.is_(True)))),
        "generations": int(await _scalar(session, select(func.count()).select_from(Generation))),
        "active_generations": int(await _scalar(
            session,
            select(func.count()).select_from(Generation).where(
                Generation.status.in_([GenerationStatus.pending, GenerationStatus.processing])
            ),
        )),
        "transactions_paid": int(await _scalar(
            session,
            select(func.count()).select_from(Transaction).where(Transaction.status == TransactionStatus.paid),
        )),
        "revenue_total": _money(await _scalar(
            session,
            select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(Transaction.status == TransactionStatus.paid),
        )),
        "credits_spent": _money(await _scalar(session, select(func.coalesce(func.sum(Generation.credits_spent), 0)))),
        "credits_on_balance": _money(await _scalar(session, select(func.coalesce(func.sum(User.credits), 0)))),
        "pending_prompts": int(await _scalar(
            session,
            select(func.count()).select_from(UserPrompt).where(UserPrompt.status == PromptStatus.pending),
        )),
        "pending_withdrawals": int(await _scalar(
            session,
            select(func.count()).select_from(ReferralWithdrawalRequest).where(
                ReferralWithdrawalRequest.status == WithdrawalStatus.pending
            ),
        )),
        "active_models": int(await _scalar(session, select(func.count()).select_from(ModelCost).where(ModelCost.is_active.is_(True)))),
        "active_price_plans": int(await _scalar(session, select(func.count()).select_from(PricePlan).where(PricePlan.is_active.is_(True)))),
    }
    periods = {
        "new_users_today": int(await _scalar(session, select(func.count()).select_from(User).where(User.created_at >= today_start))),
        "new_users_7d": int(await _scalar(session, select(func.count()).select_from(User).where(User.created_at >= week_start))),
        "new_users_30d": int(await _scalar(session, select(func.count()).select_from(User).where(User.created_at >= month_start))),
        "generations_today": int(await _scalar(session, select(func.count()).select_from(Generation).where(Generation.created_at >= today_start))),
        "generations_7d": int(await _scalar(session, select(func.count()).select_from(Generation).where(Generation.created_at >= week_start))),
        "revenue_today": _money(await _scalar(
            session,
            select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(
                Transaction.status == TransactionStatus.paid,
                Transaction.created_at >= today_start,
            ),
        )),
        "revenue_7d": _money(await _scalar(
            session,
            select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(
                Transaction.status == TransactionStatus.paid,
                Transaction.created_at >= week_start,
            ),
        )),
        "revenue_30d": _money(await _scalar(
            session,
            select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(
                Transaction.status == TransactionStatus.paid,
                Transaction.created_at >= month_start,
            ),
        )),
    }

    model_count = func.count().label("count")
    model_rows = await session.execute(
        select(
            Generation.model,
            Generation.gen_type,
            model_count,
            func.coalesce(func.sum(Generation.credits_spent), 0).label("credits"),
            func.sum(case((Generation.status == GenerationStatus.done, 1), else_=0)).label("done"),
            func.sum(case((Generation.status == GenerationStatus.failed, 1), else_=0)).label("failed"),
        )
        .group_by(Generation.model, Generation.gen_type)
        .order_by(desc(model_count))
        .limit(12)
    )
    top_models = [
        {
            "model": model,
            "gen_type": enum_value(gen_type),
            "count": int(count or 0),
            "credits": _money(credits),
            "done": int(done or 0),
            "failed": int(failed or 0),
        }
        for model, gen_type, count, credits, done, failed in model_rows.all()
    ]

    recent_generation_rows = await session.execute(
        select(Generation, User)
        .join(User, User.id == Generation.user_id)
        .order_by(desc(Generation.created_at), desc(Generation.id))
        .limit(12)
    )
    recent_transaction_rows = await session.execute(
        select(Transaction, User)
        .join(User, User.id == Transaction.user_id)
        .order_by(desc(Transaction.created_at), desc(Transaction.id))
        .limit(12)
    )
    recent_user_rows = await session.execute(select(User).order_by(desc(User.created_at), desc(User.id)).limit(10))
    active_generation_rows = await session.execute(
        select(Generation, User)
        .join(User, User.id == Generation.user_id)
        .where(Generation.status.in_([GenerationStatus.pending, GenerationStatus.processing]))
        .order_by(desc(Generation.created_at), desc(Generation.id))
        .limit(20)
    )

    alerts: list[dict[str, str]] = []
    if not getattr(settings, "KIE_WEBHOOK_SECRET", ""):
        alerts.append({"level": "danger", "title": "KIE webhook secret не задан", "message": "В production вебхуки KIE должны быть защищены секретом."})
    if not getattr(settings, "WEB_CAPTCHA_ENABLED", False):
        alerts.append({"level": "warning", "title": "CAPTCHA регистрации выключена", "message": "Для публичной регистрации включите Cloudflare Turnstile."})
    if totals["active_generations"] > 0:
        alerts.append({"level": "info", "title": "Есть активные генерации", "message": f"В очереди сейчас {totals['active_generations']} задач."})
    if totals["pending_withdrawals"] > 0:
        alerts.append({"level": "warning", "title": "Есть заявки на вывод", "message": f"Ожидают решения: {totals['pending_withdrawals']}."})

    return {
        "generated_at": iso_datetime(now),
        "totals": totals,
        "periods": periods,
        "status_counts": await _count_by_enum(session, Generation, Generation.status),
        "type_counts": await _count_by_enum(session, Generation, Generation.gen_type),
        "payment_status_counts": await _count_by_enum(session, Transaction, Transaction.status),
        "series": {
            "revenue_14d": await _daily_series(
                session,
                Transaction.created_at,
                Transaction,
                days=14,
                value_expr=func.sum(Transaction.amount_rub),
                filters=(Transaction.status == TransactionStatus.paid,),
            ),
            "generations_14d": await _daily_series(session, Generation.created_at, Generation, days=14),
            "users_14d": await _daily_series(session, User.created_at, User, days=14),
        },
        "top_models": top_models,
        "recent": {
            "generations": [_generation_card(gen, user) for gen, user in recent_generation_rows.all()],
            "transactions": [_transaction_card(tx, user) for tx, user in recent_transaction_rows.all()],
            "users": [_user_card(user) for user in recent_user_rows.scalars().all()],
            "active_generations": [_generation_card(gen, user) for gen, user in active_generation_rows.all()],
        },
        "settings": {
            "env": settings.ENV,
            "webhook_url": settings.WEBHOOK_URL,
            "web_public_url": settings.WEB_PUBLIC_URL,
            "captcha_enabled": bool(getattr(settings, "WEB_CAPTCHA_ENABLED", False)),
            "kie_webhook_secret": bool(getattr(settings, "KIE_WEBHOOK_SECRET", "")),
            "telegram_stars_enabled": bool(getattr(settings, "TELEGRAM_STARS_ENABLED", False)),
            "email_auth_enabled": bool(getattr(settings, "WEB_AUTH_EMAIL_ENABLED", False)),
            "payment_methods": enabled_payment_methods(),
        },
        "alerts": alerts,
    }


@router.get("/admin/overview")
async def admin_overview(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    return ok(await _admin_overview_payload(session))


@router.get("/admin/users")
async def admin_users(
    q: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error

    filters = []
    query = (q or "").strip()
    if query:
        parts = [
            User.username.ilike(f"%{query.lstrip('@')}%"),
            User.full_name.ilike(f"%{query}%"),
            User.email.ilike(f"%{query}%"),
            User.phone.ilike(f"%{query}%"),
            User.referral_code.ilike(f"%{query}%"),
        ]
        if query.isdigit():
            number = int(query)
            parts.extend([User.id == number, User.tg_id == number])
        filters.append(or_(*parts))

    gen_stats = (
        select(
            Generation.user_id.label("user_id"),
            func.count().label("generations_count"),
            func.coalesce(func.sum(Generation.credits_spent), 0).label("credits_spent"),
            func.max(Generation.created_at).label("last_generation_at"),
        )
        .group_by(Generation.user_id)
        .subquery()
    )
    paid_stats = (
        select(
            Transaction.user_id.label("user_id"),
            func.coalesce(func.sum(Transaction.amount_rub), 0).label("paid_rub"),
        )
        .where(Transaction.status == TransactionStatus.paid)
        .group_by(Transaction.user_id)
        .subquery()
    )
    total = int(await _scalar(session, select(func.count()).select_from(User).where(*filters)))
    result = await session.execute(
        select(User, gen_stats.c.generations_count, gen_stats.c.credits_spent, gen_stats.c.last_generation_at, paid_stats.c.paid_rub)
        .outerjoin(gen_stats, gen_stats.c.user_id == User.id)
        .outerjoin(paid_stats, paid_stats.c.user_id == User.id)
        .where(*filters)
        .order_by(desc(User.created_at), desc(User.id))
        .limit(limit)
        .offset(offset)
    )
    items = [
        _user_card(
            item,
            {
                "generations_count": generations_count,
                "credits_spent": credits_spent,
                "last_generation_at": last_generation_at,
                "paid_rub": paid_rub,
            },
        )
        for item, generations_count, credits_spent, last_generation_at, paid_rub in result.all()
    ]
    return ok({"total": total, "limit": limit, "offset": offset, "items": items})


@router.post("/admin/users/{user_id}/credits")
async def admin_adjust_user_credits(
    user_id: int,
    body: AdminCreditAdjustmentRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    target = await repo.get_user_by_id(session, user_id)
    if not target:
        return error_response(404, "User not found")
    if abs(body.amount) < 1e-9:
        return error_response(422, "Amount must not be zero")
    note = body.note or f"Web admin adjustment by {getattr(user, 'tg_id', '')}"
    if body.amount > 0:
        balance = await repo.add_credits(
            session,
            user_id,
            body.amount,
            entry_type="admin_adjustment",
            source_type="admin",
            source_id=str(getattr(user, "tg_id", "")),
            note=note,
        )
    else:
        ok_spend = await repo.spend_credits(
            session,
            user_id,
            abs(body.amount),
            entry_type="admin_adjustment",
            source_type="admin",
            source_id=str(getattr(user, "tg_id", "")),
            note=note,
        )
        if not ok_spend:
            return error_response(422, "Not enough user credits to deduct")
        target = await repo.get_user_by_id(session, user_id)
        balance = float(getattr(target, "credits", 0) or 0)
    return ok({"user_id": user_id, "balance": float(balance), "delta": body.amount})


@router.post("/admin/users/{user_id}/ban")
async def admin_set_user_ban(
    user_id: int,
    body: AdminBanRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    result = await session.execute(update(User).where(User.id == user_id).values(is_banned=body.banned).returning(User))
    updated = result.scalar_one_or_none()
    await session.commit()
    if not updated:
        return error_response(404, "User not found")
    return ok(_user_card(updated))


@router.get("/admin/generations")
async def admin_generations(
    status: str = Query(default="all", pattern="^(all|pending|processing|done|failed)$"),
    gen_type: str = Query(default="all", pattern="^(all|image|video|music)$"),
    q: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    filters = []
    if status != "all":
        filters.append(Generation.status == GenerationStatus(status))
    if gen_type != "all":
        filters.append(Generation.gen_type == GenerationType(gen_type))
    query = (q or "").strip()
    if query:
        parts = [
            Generation.model.ilike(f"%{query}%"),
            Generation.prompt.ilike(f"%{query}%"),
            Generation.task_id.ilike(f"%{query}%"),
            User.username.ilike(f"%{query.lstrip('@')}%"),
            User.email.ilike(f"%{query}%"),
        ]
        if query.isdigit():
            number = int(query)
            parts.extend([Generation.id == number, Generation.user_id == number, User.tg_id == number])
        filters.append(or_(*parts))
    total = int(await _scalar(
        session,
        select(func.count()).select_from(Generation).join(User, User.id == Generation.user_id).where(*filters),
    ))
    result = await session.execute(
        select(Generation, User)
        .join(User, User.id == Generation.user_id)
        .where(*filters)
        .order_by(desc(Generation.created_at), desc(Generation.id))
        .limit(limit)
        .offset(offset)
    )
    return ok({"total": total, "limit": limit, "offset": offset, "items": [_generation_card(gen, owner) for gen, owner in result.all()]})


@router.post("/admin/generations/{generation_id}/fail")
async def admin_fail_generation(
    generation_id: int,
    body: AdminGenerationFailRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    gen = await repo.get_generation_by_id(session, generation_id)
    if not gen:
        return error_response(404, "Generation not found")
    if enum_value(gen.status) not in {"pending", "processing"}:
        return error_response(409, "Generation is already final")
    updated = await repo.fail_generation(session, generation_id, body.error)
    if updated and body.refund and float(gen.credits_spent or 0) > 0:
        await repo.add_credits(
            session,
            gen.user_id,
            float(gen.credits_spent or 0),
            entry_type="admin_generation_refund",
            source_type="generation",
            source_id=str(generation_id),
            note=f"Refund by web admin {getattr(user, 'tg_id', '')}: {body.error}",
        )
    refreshed = await repo.get_generation_by_id(session, generation_id)
    owner = await repo.get_user_by_id(session, refreshed.user_id) if refreshed else None
    return ok(_generation_card(refreshed, owner) if refreshed else {"id": generation_id})


@router.get("/admin/pricing")
async def admin_pricing(
    q: str | None = Query(default=None, max_length=128),
    include_inactive: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    model_filters = []
    query = (q or "").strip()
    if query:
        model_filters.append(or_(ModelCost.model_key.ilike(f"%{query}%"), ModelCost.display_name.ilike(f"%{query}%")))
    if not include_inactive:
        model_filters.append(ModelCost.is_active.is_(True))
    model_rows = await session.execute(
        select(ModelCost)
        .where(*model_filters)
        .order_by(ModelCost.gen_type, ModelCost.display_name, ModelCost.model_key)
        .limit(300)
    )
    plan_rows = await session.execute(select(PricePlan).order_by(PricePlan.sort_order, PricePlan.credits, PricePlan.id))
    return ok({
        "models": [_model_cost_card(item) for item in model_rows.scalars().all()],
        "price_plans": [_price_plan_card(item) for item in plan_rows.scalars().all()],
    })


@router.patch("/admin/model-costs/{model_id}")
async def admin_update_model_cost(
    model_id: int,
    body: AdminModelCostUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    values = body.model_dump(exclude_unset=True)
    if not values:
        return error_response(422, "No changes")
    result = await session.execute(update(ModelCost).where(ModelCost.id == model_id).values(**values).returning(ModelCost))
    item = result.scalar_one_or_none()
    await session.commit()
    if not item:
        return error_response(404, "Model cost not found")
    return ok(_model_cost_card(item))


@router.patch("/admin/price-plans/{plan_id}")
async def admin_update_price_plan(
    plan_id: int,
    body: AdminPricePlanUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    values = body.model_dump(exclude_unset=True)
    if not values:
        return error_response(422, "No changes")
    result = await session.execute(update(PricePlan).where(PricePlan.id == plan_id).values(**values).returning(PricePlan))
    item = result.scalar_one_or_none()
    await session.commit()
    if not item:
        return error_response(404, "Price plan not found")
    return ok(_price_plan_card(item))


@router.get("/admin/withdrawals")
async def admin_withdrawals(
    status: str = Query(default="pending", pattern="^(all|pending|approved|rejected)$"),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    filters = []
    if status != "all":
        filters.append(ReferralWithdrawalRequest.status == WithdrawalStatus(status))
    result = await session.execute(
        select(ReferralWithdrawalRequest, User)
        .join(User, User.id == ReferralWithdrawalRequest.user_id)
        .where(*filters)
        .order_by(desc(ReferralWithdrawalRequest.created_at), desc(ReferralWithdrawalRequest.id))
        .limit(limit)
    )
    return ok({"items": [_withdrawal_card(item, owner) for item, owner in result.all()]})


@router.post("/admin/withdrawals/{request_id}")
async def admin_review_withdrawal(
    request_id: int,
    body: AdminWithdrawalActionRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    status = WithdrawalStatus.approved if body.action == "approve" else WithdrawalStatus.rejected
    try:
        view = await repo.set_withdrawal_status(
            session,
            request_id,
            status=status,
            admin_tg_id=int(getattr(user, "tg_id", 0) or 0),
            admin_note=body.note,
        )
    except InsufficientReferralBalanceError as exc:
        return error_response(422, f"Insufficient referral balance: available {exc.available_amount:g}")
    if not view:
        return error_response(404, "Pending withdrawal not found")
    return ok(_withdrawal_card(view.request, view.user))


@router.get("/admin/ledger")
async def admin_ledger(
    user_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if admin_error := _admin_error(user):
        return admin_error
    filters = [CreditLedgerEntry.user_id == user_id] if user_id else []
    result = await session.execute(
        select(CreditLedgerEntry)
        .where(*filters)
        .order_by(desc(CreditLedgerEntry.created_at), desc(CreditLedgerEntry.id))
        .limit(limit)
    )
    items = [
        {
            "id": item.id,
            "user_id": item.user_id,
            "delta": float(item.delta or 0),
            "balance_after": float(item.balance_after or 0),
            "entry_type": item.entry_type,
            "source_type": item.source_type,
            "source_id": item.source_id,
            "note": item.note,
            "created_at": iso_datetime(item.created_at),
        }
        for item in result.scalars().all()
    ]
    return ok({"items": items})
