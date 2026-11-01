"""Admin-audited Nexus -> Neironych image recovery route.

Fallback model aliases are an exact capability map, not user-configurable substitutions.
Whether a route is active is resolved from the existing provider routing control plane.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ProviderRoutingAudit, ProviderRoutingSetting

# Confirmed production models in Neironych. VIP variants have no exact counterpart.
EXACT_MODELS: dict[str, str] = {
    "nano-banana-pro": "nano-banana-pro",
    "nano-banana-2": "nano-banana-2",
    "gpt-image-2-text-to-image": "gpt-image-2",
    "gpt-image-2-image-to-image": "gpt-image-2",
}
_PREFIX = "image-fallback:"


@dataclass(frozen=True)
class ImageFallbackRoute:
    model_key: str
    enabled: bool
    fallback_provider: str
    source: str
    updated_by_admin_tg_id: int | None = None


def _setting_key(model_key: str) -> str:
    if model_key not in EXACT_MODELS:
        raise ValueError("Unsupported exact-model image fallback route")
    return _PREFIX + model_key


async def get_image_fallback_route(session: AsyncSession, model_key: str) -> ImageFallbackRoute:
    key = _setting_key(model_key)
    record = await session.get(ProviderRoutingSetting, key)
    if record is None:
        # Requested default. Admin can turn off any model without redeploying.
        return ImageFallbackRoute(model_key, True, "neironych", "default")
    return ImageFallbackRoute(
        model_key, record.primary_provider == "neironych",
        "neironych", "database", record.updated_by_admin_tg_id,
    )


async def fallback_enabled(session: AsyncSession, model_key: str) -> bool:
    if model_key not in EXACT_MODELS:
        return False
    return (await get_image_fallback_route(session, model_key)).enabled


async def set_image_fallback_route(
    session: AsyncSession, model_key: str, enabled: bool, *,
    admin_tg_id: int, source: str = "web",
) -> ImageFallbackRoute:
    key = _setting_key(model_key)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    if not int(admin_tg_id):
        raise ValueError("Admin actor is required")
    desired = "neironych" if enabled else "nexus"
    await session.execute(
        pg_insert(ProviderRoutingSetting).values(
            model_key=key, primary_provider="neironych", updated_by_admin_tg_id=None,
        ).on_conflict_do_nothing(index_elements=["model_key"])
    )
    record = (await session.execute(
        select(ProviderRoutingSetting).where(ProviderRoutingSetting.model_key == key)
        .with_for_update()
    )).scalar_one()
    previous = record.primary_provider
    if previous != desired or record.updated_by_admin_tg_id is None:
        record.primary_provider = desired
        record.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(ProviderRoutingAudit(
            model_key=key, previous_provider=previous, new_provider=desired,
            changed_by_admin_tg_id=int(admin_tg_id), source=source,
        ))
    await session.commit()
    return ImageFallbackRoute(model_key, enabled, "neironych", "database", int(admin_tg_id))
