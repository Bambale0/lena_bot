"""Install the final fail-closed pricing resolver for provider operations."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api import provider_operation_registry as registry
from bot.services.generation_service import (
    get_image_price_for_model,
    get_midjourney_price,
    get_music_price_for_model,
    get_video_price_for_model,
)
from db.models import GenerationType


async def resolve_operation_price(
    session: AsyncSession,
    spec: registry.OperationSpec,
    params: dict[str, Any],
) -> int:
    if not spec.billable:
        return 0

    # Contract family wins over result media type. Midjourney video still uses
    # the Midjourney video tariff, not the generic video per-second catalogue.
    if spec.contract_id.startswith("midjourney."):
        return await get_midjourney_price(
            spec.contract_id.split(".", 1)[1],
            session=session,
        )

    if spec.contract_id.startswith("suno."):
        model = str(params.get("model") or "V5")
        model_aliases = {
            "V3_5": "suno/v4.5",
            "V4": "suno/v4.5",
            "V4_5": "suno/v4.5",
            "V4_5PLUS": "suno/v4.5",
            "V4_5ALL": "suno/v4.5",
            "V5": "suno/v5.0",
            "V5_5": "suno/v5.5",
        }
        return await get_music_price_for_model(
            model_aliases.get(model, model),
            session=session,
        )

    if spec.generation_type == GenerationType.IMAGE:
        return await get_image_price_for_model(
            spec.price_alias or spec.model,
            quality=str(params.get("quality") or params.get("resolution") or "") or None,
            count=int(params.get("n") or params.get("count") or 1),
            session=session,
        )

    if spec.generation_type == GenerationType.VIDEO:
        return await get_video_price_for_model(
            spec.price_alias or spec.model,
            duration=int(params.get("duration") or params.get("extend_times") or 1),
            resolution=str(params.get("resolution") or params.get("mode") or "") or None,
            has_video_input=bool(
                params.get("reference_video_url")
                or params.get("reference_video_urls")
                or params.get("video_url")
                or params.get("first_clip_url")
            ),
            session=session,
        )

    if spec.generation_type == GenerationType.MUSIC:
        return await get_music_price_for_model(
            str(params.get("model") or spec.price_alias or spec.model),
            session=session,
        )

    raise LookupError(f"No pricing policy for billable contract {spec.contract_id}")


registry.resolve_operation_price = resolve_operation_price
