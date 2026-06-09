from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.billing import enabled_payment_methods
from api.web.deps import ok
from api.web.schemas import FeedCard, ModelCostCard, PricePlanCard, PromptCard
from api.web.prompts import _prompt_cards
from db import repository as repo
from db.models import GenerationType
from db.prompt_repository import get_approved_prompts
from db.session import get_session

router = APIRouter(tags=["web"])


async def _group_model_cards(session: AsyncSession) -> dict[str, list[dict]]:
    cards = [ModelCostCard.from_model_cost(item).model_dump() for item in await repo.get_all_model_costs(session)]
    image = [item for item in cards if item["gen_type"] == GenerationType.image.value]
    video = [item for item in cards if item["gen_type"] == GenerationType.video.value]
    music = [item for item in cards if item["gen_type"] == GenerationType.music.value]
    return {
        "image": image,
        "video": video,
        "music": music,
        "all": [*image, *video, *music],
    }


@router.get("/landing")
async def landing_payload(session: AsyncSession = Depends(get_session)) -> dict:
    feed_cards = await repo.get_feed_generations(session, limit=120)
    prompts = await get_approved_prompts(session, offset=0, limit=40)
    plans = await repo.get_active_price_plans(session)

    return ok(
        {
            "models": await _group_model_cards(session),
            "examples": [FeedCard.from_feed_card(item).model_dump() for item in feed_cards],
            "prompts": {
                "items": await _prompt_cards(session, prompts),
                "total": len(prompts),
            },
            "plans": [PricePlanCard.from_price_plan(item).model_dump() for item in plans],
            "payment_methods": enabled_payment_methods(),
        }
    )
