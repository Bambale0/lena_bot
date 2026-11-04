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
PrimaryProvider = Literal["neironych", "nexus", "kie"]
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


SEEDREAM_5_MODEL = "seedream-5.0-pro"
SEEDREAM_5_MODELS = frozenset({"seedream/5-pro-text-to-image", "seedream/5-pro-image-to-image"})
SeedreamProvider = Literal["neironych", "kie"]


async def get_seedream5_route(session: AsyncSession) -> ProviderRoute:
    record = await session.get(ProviderRoutingSetting, SEEDREAM_5_MODEL)
    if record is not None:
        if record.primary_provider not in {"neironych", "kie"}:
            raise ValueError("Unsupported Seedream 5 Pro provider")
        return ProviderRoute(SEEDREAM_5_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)
    return ProviderRoute(SEEDREAM_5_MODEL, settings.SEEDREAM_5_PRIMARY_PROVIDER, "environment")


async def set_seedream5_route(
    session: AsyncSession, primary_provider: SeedreamProvider, *,
    admin_tg_id: int, source: Literal["telegram", "web"],
) -> ProviderRoute:
    if primary_provider not in {"neironych", "kie"}:
        raise ValueError("Unsupported Seedream 5 Pro provider")
    if not int(admin_tg_id) or source not in {"telegram", "web"}:
        raise ValueError("Valid audit actor and source are required")
    await session.execute(
        pg_insert(ProviderRoutingSetting).values(
            model_key=SEEDREAM_5_MODEL, primary_provider=settings.SEEDREAM_5_PRIMARY_PROVIDER,
            updated_by_admin_tg_id=None,
        ).on_conflict_do_nothing(index_elements=["model_key"])
    )
    record = (await session.execute(
        select(ProviderRoutingSetting).where(ProviderRoutingSetting.model_key == SEEDREAM_5_MODEL).with_for_update()
    )).scalar_one()
    previous = record.primary_provider
    if previous != primary_provider:
        record.primary_provider = primary_provider
        record.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(ProviderRoutingAudit(
            model_key=SEEDREAM_5_MODEL, previous_provider=previous, new_provider=primary_provider,
            changed_by_admin_tg_id=int(admin_tg_id), source=source,
        ))
    await session.commit()
    return ProviderRoute(SEEDREAM_5_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)


NANO_2_MODEL = "nano-banana-2"


async def get_nano2_route(session: AsyncSession) -> ProviderRoute:
    record = await session.get(ProviderRoutingSetting, NANO_2_MODEL)
    if record is not None:
        if record.primary_provider not in _ALLOWED:
            raise ValueError("Unsupported Nano Banana 2 provider")
        return ProviderRoute(NANO_2_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)
    return ProviderRoute(NANO_2_MODEL, settings.NANO_BANANA_2_PRIMARY_PROVIDER, "environment")


async def set_nano2_route(
    session: AsyncSession, primary_provider: Literal["neironych", "nexus"], *,
    admin_tg_id: int, source: Literal["telegram", "web"],
) -> ProviderRoute:
    if primary_provider not in _ALLOWED or not int(admin_tg_id) or source not in {"telegram", "web"}:
        raise ValueError("Valid provider, audit actor and source are required")
    await session.execute(
        pg_insert(ProviderRoutingSetting).values(
            model_key=NANO_2_MODEL, primary_provider=settings.NANO_BANANA_2_PRIMARY_PROVIDER,
            updated_by_admin_tg_id=None,
        ).on_conflict_do_nothing(index_elements=["model_key"])
    )
    record = (await session.execute(
        select(ProviderRoutingSetting).where(ProviderRoutingSetting.model_key == NANO_2_MODEL).with_for_update()
    )).scalar_one()
    previous = record.primary_provider
    if previous != primary_provider:
        record.primary_provider = primary_provider
        record.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(ProviderRoutingAudit(
            model_key=NANO_2_MODEL, previous_provider=previous, new_provider=primary_provider,
            changed_by_admin_tg_id=int(admin_tg_id), source=source,
        ))
    await session.commit()
    return ProviderRoute(NANO_2_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)


NANO_PRO_MODEL = "nano-banana-pro"


async def get_nano_pro_route(session: AsyncSession) -> ProviderRoute:
    record = await session.get(ProviderRoutingSetting, NANO_PRO_MODEL)
    if record is not None:
        if record.primary_provider not in _ALLOWED:
            raise ValueError("Unsupported Nano Banana Pro provider")
        return ProviderRoute(NANO_PRO_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)
    return ProviderRoute(NANO_PRO_MODEL, settings.NANO_BANANA_PRO_PRIMARY_PROVIDER, "environment")


async def set_nano_pro_route(
    session: AsyncSession, primary_provider: Literal["neironych", "nexus"], *,
    admin_tg_id: int, source: Literal["telegram", "web"],
) -> ProviderRoute:
    if primary_provider not in _ALLOWED or not int(admin_tg_id) or source not in {"telegram", "web"}:
        raise ValueError("Valid provider, audit actor and source are required")
    await session.execute(
        pg_insert(ProviderRoutingSetting).values(
            model_key=NANO_PRO_MODEL, primary_provider=settings.NANO_BANANA_PRO_PRIMARY_PROVIDER,
            updated_by_admin_tg_id=None,
        ).on_conflict_do_nothing(index_elements=["model_key"])
    )
    record = (await session.execute(
        select(ProviderRoutingSetting).where(ProviderRoutingSetting.model_key == NANO_PRO_MODEL).with_for_update()
    )).scalar_one()
    previous = record.primary_provider
    if previous != primary_provider:
        record.primary_provider = primary_provider
        record.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(ProviderRoutingAudit(
            model_key=NANO_PRO_MODEL, previous_provider=previous, new_provider=primary_provider,
            changed_by_admin_tg_id=int(admin_tg_id), source=source,
        ))
    await session.commit()
    return ProviderRoute(NANO_PRO_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)


GPT2_MODEL = "gpt-image-2"


async def get_gpt2_route(session: AsyncSession) -> ProviderRoute:
    record = await session.get(ProviderRoutingSetting, GPT2_MODEL)
    if record is not None:
        if record.primary_provider not in _ALLOWED:
            raise ValueError("Unsupported GPT Image 2 provider")
        return ProviderRoute(GPT2_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)
    return ProviderRoute(GPT2_MODEL, settings.GPT_IMAGE_2_PRIMARY_PROVIDER, "environment")


async def set_gpt2_route(
    session: AsyncSession, primary_provider: Literal["neironych", "nexus"], *,
    admin_tg_id: int, source: Literal["telegram", "web"],
) -> ProviderRoute:
    if primary_provider not in _ALLOWED or not int(admin_tg_id) or source not in {"telegram", "web"}:
        raise ValueError("Valid provider, audit actor and source are required")
    await session.execute(
        pg_insert(ProviderRoutingSetting).values(
            model_key=GPT2_MODEL, primary_provider=settings.GPT_IMAGE_2_PRIMARY_PROVIDER,
            updated_by_admin_tg_id=None,
        ).on_conflict_do_nothing(index_elements=["model_key"])
    )
    record = (await session.execute(
        select(ProviderRoutingSetting).where(ProviderRoutingSetting.model_key == GPT2_MODEL).with_for_update()
    )).scalar_one()
    previous = record.primary_provider
    if previous != primary_provider:
        record.primary_provider = primary_provider
        record.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(ProviderRoutingAudit(
            model_key=GPT2_MODEL, previous_provider=previous, new_provider=primary_provider,
            changed_by_admin_tg_id=int(admin_tg_id), source=source,
        ))
    await session.commit()
    return ProviderRoute(GPT2_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)


GPT25_MODEL = "gpt-image-2.5-sunburst"


async def get_gpt25_route(session: AsyncSession) -> ProviderRoute:
    record = await session.get(ProviderRoutingSetting, GPT25_MODEL)
    if record is not None:
        if record.primary_provider not in {"neironych"}:
            raise ValueError("Unsupported GPT Image 2.5 provider")
        return ProviderRoute(GPT25_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)
    return ProviderRoute(GPT25_MODEL, settings.GPT_IMAGE_25_PRIMARY_PROVIDER, "environment")


async def set_gpt25_route(
    session: AsyncSession, primary_provider: Literal["neironych", "nexus"], *,
    admin_tg_id: int, source: Literal["telegram", "web"],
) -> ProviderRoute:
    if primary_provider not in {"neironych"} or not int(admin_tg_id) or source not in {"telegram", "web"}:
        raise ValueError("Valid provider, audit actor and source are required")
    await session.execute(
        pg_insert(ProviderRoutingSetting).values(
            model_key=GPT25_MODEL, primary_provider=settings.GPT_IMAGE_25_PRIMARY_PROVIDER,
            updated_by_admin_tg_id=None,
        ).on_conflict_do_nothing(index_elements=["model_key"])
    )
    record = (await session.execute(
        select(ProviderRoutingSetting).where(ProviderRoutingSetting.model_key == GPT25_MODEL).with_for_update()
    )).scalar_one()
    previous = record.primary_provider
    if previous != primary_provider:
        record.primary_provider = primary_provider
        record.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(ProviderRoutingAudit(
            model_key=GPT25_MODEL, previous_provider=previous, new_provider=primary_provider,
            changed_by_admin_tg_id=int(admin_tg_id), source=source,
        ))
    await session.commit()
    return ProviderRoute(GPT25_MODEL, record.primary_provider, "database", record.updated_by_admin_tg_id)


GPT_IMAGE_MODELS = frozenset({"gpt-image-2-text-to-image", "gpt-image-2-image-to-image", "gpt-image-2.5-sunburst"})
