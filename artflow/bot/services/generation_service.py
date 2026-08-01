"""Central pricing helpers shared by Telegram, Mini App and provider gateway.

The repository stores image prices as flat credits, most video resolution
variants as credits per second, and Gemini Omni variants as final flat prices.
This module is the only place that applies those rules.
"""
from __future__ import annotations

from collections.abc import Iterable
import math

from sqlalchemy.ext.asyncio import AsyncSession

from core.gemini_omni import GEMINI_OMNI_VIDEO_MODEL, gemini_omni_video_credits
from core.model_pricing import image_pricing_keys, video_pricing_keys
from db import repository as repo
from db.session import AsyncSessionLocal


_FLAT_VIDEO_MODELS = {
    "veo3",
    "veo3_fast",
    "veo3_lite",
}
_VIDEO_POST_PROCESS_MODELS = {
    "grok-imagine/upscale",
    "grok-imagine/extend",
    "veo/extend",
    "veo/get-1080p-video",
    "veo/get-4k-video",
}


async def _first_cost(session: AsyncSession, keys: Iterable[str]) -> float | None:
    for key in keys:
        cost = await repo.get_model_cost(session, key)
        if cost is not None:
            return float(cost)
    return None


async def get_image_price_for_model(
    model: str,
    *,
    quality: str | None = None,
    count: int = 1,
    session: AsyncSession | None = None,
) -> int:
    owns_session = session is None
    active_session = session or AsyncSessionLocal()
    try:
        unit = await _first_cost(active_session, image_pricing_keys(model, quality))
        if unit is None:
            raise LookupError(f"No active image price configured for {model}")
        safe_count = max(1, int(count or 1))
        return max(1, math.ceil(unit * safe_count))
    finally:
        if owns_session:
            await active_session.close()


async def get_video_price_for_model(
    model: str,
    *,
    duration: int | None = None,
    resolution: str | None = None,
    has_video_input: bool = False,
    session: AsyncSession | None = None,
) -> int:
    safe_duration = max(1, int(duration or 1))

    if model == GEMINI_OMNI_VIDEO_MODEL:
        return int(
            gemini_omni_video_credits(
                duration=safe_duration,
                resolution=resolution,
                has_video_input=has_video_input,
            )
        )

    owns_session = session is None
    active_session = session or AsyncSessionLocal()
    try:
        unit = await _first_cost(
            active_session,
            video_pricing_keys(
                model,
                duration=safe_duration,
                resolution=resolution,
            ),
        )
        if unit is None:
            raise LookupError(f"No active video price configured for {model}")

        # Seeded resolution variants for generative video are explicitly marked
        # "за сек". Veo and post-processing operations are flat provider tasks.
        if model in _FLAT_VIDEO_MODELS or model in _VIDEO_POST_PROCESS_MODELS:
            return max(1, math.ceil(unit))
        return max(1, math.ceil(unit * safe_duration))
    finally:
        if owns_session:
            await active_session.close()


async def get_music_price_for_model(
    model: str,
    *,
    session: AsyncSession | None = None,
) -> int:
    owns_session = session is None
    active_session = session or AsyncSessionLocal()
    try:
        cost = await repo.get_model_cost(active_session, model)
        if cost is None:
            raise LookupError(f"No active music price configured for {model}")
        return max(1, math.ceil(float(cost)))
    finally:
        if owns_session:
            await active_session.close()


async def get_midjourney_price(
    operation: str,
    *,
    session: AsyncSession | None = None,
) -> int:
    aliases = {
        "imagine": "midjourney-imagine",
        "action": "midjourney-action",
        "change": "midjourney-action",
        "modal": "midjourney-action",
        "editor": "midjourney-action",
        "blend": "midjourney-blend",
        "describe": "midjourney-describe",
        "video": "midjourney-video",
    }
    price_key = aliases.get(str(operation))
    if not price_key:
        raise LookupError(f"Midjourney operation is not billable: {operation}")

    owns_session = session is None
    active_session = session or AsyncSessionLocal()
    try:
        cost = await repo.get_model_cost(active_session, price_key)
        if cost is None:
            raise LookupError(f"No active Midjourney price configured for {operation}")
        return max(1, math.ceil(float(cost)))
    finally:
        if owns_session:
            await active_session.close()


async def get_video_price(
    duration: int,
    resolution: str | None = None,
    *,
    model: str = "kling-2.6/text-to-video",
) -> int:
    """Backward-compatible helper used by older handlers."""
    return await get_video_price_for_model(
        model,
        duration=duration,
        resolution=resolution,
    )


async def get_wan27pro_price(
    quality: str = "2K",
    count: int = 1,
) -> int:
    return await get_image_price_for_model(
        "wan/2-7-image-pro",
        quality=quality,
        count=count,
    )
