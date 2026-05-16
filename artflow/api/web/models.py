from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.deps import ok
from api.web.schemas import ModelCostCard, PricePlanCard
from db import repository as repo
from db.session import get_session

router = APIRouter(tags=["web"])


@router.get("/models")
async def models(session: AsyncSession = Depends(get_session)) -> dict:
    model_costs = await repo.get_all_model_costs(session)
    return ok([ModelCostCard.from_model_cost(item).model_dump() for item in model_costs])


@router.get("/price-plans")
async def price_plans(session: AsyncSession = Depends(get_session)) -> dict:
    plans = await repo.get_active_price_plans(session)
    return ok([PricePlanCard.from_price_plan(item).model_dump() for item in plans])
