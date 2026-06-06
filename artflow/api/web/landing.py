from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.billing import enabled_payment_methods
from api.web.deps import ok
from api.web.schemas import FeedCard, ModelCostCard, PricePlanCard, PromptCard
from db import repository as repo
from db.prompt_repository import get_approved_prompts
from db.session import get_session

router = APIRouter(tags=["web"])


def _group_model_cards(model_costs) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {"image": [], "video": [], "music": [], "all": []}
    for item in model_costs:
        card = ModelCostCard.from_model_cost(item).model_dump()
        grouped["all"].append(card)
        if card["gen_type"] in grouped:
            grouped[card["gen_type"]].append(card)
    return grouped


@router.get("/landing")
async def landing_payload(session: AsyncSession = Depends(get_session)) -> dict:
    model_costs = await repo.get_all_model_costs(session)
    feed_cards = await repo.get_feed_generations(session, limit=300)
    prompts = await get_approved_prompts(session, offset=0, limit=24)
    plans = await repo.get_active_price_plans(session)

    return ok(
        {
            "models": _group_model_cards(model_costs),
            "examples": [FeedCard.from_feed_card(item).model_dump() for item in feed_cards],
            "prompts": {
                "items": [PromptCard.from_prompt(item).model_dump() for item in prompts],
                "total": len(prompts),
            },
            "plans": [PricePlanCard.from_price_plan(item).model_dump() for item in plans],
            "payment_methods": enabled_payment_methods(),
        }
    )
