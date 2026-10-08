"""Typed DB-backed primary provider selection for Nano Banana 2.1."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.models import ProviderRoutingAudit, ProviderRoutingSetting

NANO_21_MODEL = "nano-banana-2.1"
PrimaryProvider = Literal["neironych", "nexus"]
_ALLOWED = frozenset({"neironych", "nexus"})


@dataclass(frozen=True)
class ProviderRoute:
    model_key: str
    primary_provider: PrimaryProvider
    source: str
    updated_by_admin_tg_id: int | None = None


async def get_nano21_route(session: AsyncSession) -> ProviderRoute:
    record = await session.get(ProviderRoutingSetting, NANO_21_MODEL)
    if record is not None:
        return ProviderRoute(NANO_21_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)
    return ProviderRoute(
        NANO_21_MODEL, settings.NANO_BANANA_21_PRIMARY_PROVIDER, "environment"
    )


async def set_nano21_route(
    session: AsyncSession,
    primary_provider: PrimaryProvider,
    *,
    admin_tg_id: int,
    source: Literal["telegram", "web"],
) -> ProviderRoute:
    if primary_provider not in _ALLOWED:
        raise ValueError("Unsupported Nano Banana 2.1 provider")
    if not int(admin_tg_id):
        raise ValueError("admin_tg_id is required for audit")
    if source not in {"telegram", "web"}:
        raise ValueError("invalid route change source")

    # Concurrent admin changes serialize through the row lock. The initial
    # insert is ON CONFLICT DO NOTHING, so it never overwrites another writer.
    await session.execute(
        pg_insert(ProviderRoutingSetting)
        .values(
            model_key=NANO_21_MODEL,
            primary_provider=settings.NANO_BANANA_21_PRIMARY_PROVIDER,
            updated_by_admin_tg_id=None,
        )
        .on_conflict_do_nothing(index_elements=["model_key"])
    )
    record = (await session.execute(
        select(ProviderRoutingSetting)
        .where(ProviderRoutingSetting.model_key == NANO_21_MODEL)
        .with_for_update()
    )).scalar_one()
    previous = record.primary_provider
    if previous != primary_provider:
        record.primary_provider = primary_provider
        record.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(ProviderRoutingAudit(
            model_key=NANO_21_MODEL, previous_provider=previous,
            new_provider=primary_provider, changed_by_admin_tg_id=int(admin_tg_id),
            source=source,
        ))
    await session.commit()
    return ProviderRoute(
        NANO_21_MODEL, record.primary_provider, "database",
        record.updated_by_admin_tg_id
    )
