"""Authenticated, audited rollout shared by site, Mini App and Telegram."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select

from core.config import settings
from db.models import Kling4AccessAudit, Kling4AccessPolicy


def is_kling4_key(key: str) -> bool:
    return str(key).split("__", 1)[0] in {
        "kling-4.0/reference-to-video",
        "kling-4.0/keyframe-to-video",
    }


async def kling4_visible(session, user=None) -> bool:
    policy = await session.get(Kling4AccessPolicy, 1)
    audience = policy.audience if policy else "admin"
    return audience == "public" or (
        audience == "admin" and getattr(user, "tg_id", None) in settings.ADMIN_IDS
    )


async def require_kling4_access(session, user) -> None:
    if not await kling4_visible(session, user):
        raise HTTPException(status_code=403, detail="Kling 4 пока доступен только администратору")


async def visible_model_costs(session, costs, user=None):
    if not any(is_kling4_key(cost.model_key) for cost in costs):
        return costs
    visible = await kling4_visible(session, user)
    return [cost for cost in costs if visible or not is_kling4_key(cost.model_key)]


async def set_kling4_access(session, audience: str, *, admin_tg_id: int, source: str) -> str:
    if admin_tg_id not in settings.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Administrator required")
    if audience not in {"admin", "public", "disabled"} or source not in {"web", "bot"}:
        raise ValueError("Invalid Kling 4 rollout policy")
    policy = (
        await session.execute(
            select(Kling4AccessPolicy).where(Kling4AccessPolicy.id == 1).with_for_update()
        )
    ).scalar_one()
    if policy.audience != audience:
        session.add(
            Kling4AccessAudit(
                previous_audience=policy.audience,
                new_audience=audience,
                changed_by_admin_tg_id=admin_tg_id,
                source=source,
            )
        )
        policy.audience = audience
        policy.updated_by_admin_tg_id = admin_tg_id
    await session.commit()
    return audience
