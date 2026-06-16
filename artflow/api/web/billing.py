from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import TransactionCard
from core.config import settings
from db.models import Transaction
from db.session import get_session

router = APIRouter(tags=["web"])


def enabled_payment_methods() -> list[dict[str, str]]:
    methods: list[dict[str, str]] = []
    if getattr(settings, "TBANK_TERMINAL_KEY", "") and getattr(settings, "TBANK_PASSWORD", ""):
        methods.append({"key": "tbank", "provider": "tbank", "label": "Карта", "status": "enabled"})
    if getattr(settings, "TELEGRAM_STARS_ENABLED", False):
        methods.append({"key": "stars", "provider": "telegram_stars", "label": "Telegram", "status": "enabled"})
    if getattr(settings, "CRYPTOBOT_TOKEN", ""):
        methods.append({"key": "crypto", "provider": "cryptobot", "label": "Крипто", "status": "enabled"})
    if settings.lava_is_enabled():
        methods.append({"key": "lava", "provider": "lava", "label": "Lava", "status": "enabled"})
    return methods


@router.get("/billing/transactions")
async def billing_transactions(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")

    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(desc(Transaction.created_at), desc(Transaction.id))
        .limit(limit)
    )
    transactions = [TransactionCard.from_transaction(item).model_dump() for item in result.scalars().all()]
    return ok(
        {
            "methods": enabled_payment_methods(),
            "transactions": transactions,
            "pending": [item for item in transactions if item["status"] == "pending"],
        }
    )
