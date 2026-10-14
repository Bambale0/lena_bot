"""Typed and audited image customer refund deadlines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.models import ImageRecoveryPolicy, ImageRecoveryPolicyAudit

ImageProvider = Literal["neironych", "nexus"]
_PROVIDERS = frozenset({"neironych", "nexus"})
_MIN_SECONDS = 600
_MAX_SECONDS = 86400


@dataclass(frozen=True)
class ImageRecoveryDeadline:
    provider: ImageProvider
    auto_refund_seconds: int
    source: str
    updated_by_admin_tg_id: int | None = None


async def get_image_recovery_policy(
    session: AsyncSession, provider: ImageProvider,
) -> ImageRecoveryDeadline:
    if provider not in _PROVIDERS:
        raise ValueError("Unsupported image provider")
    record = await session.get(ImageRecoveryPolicy, provider)
    if record is not None:
        return ImageRecoveryDeadline(
            provider, record.auto_refund_seconds, "database", record.updated_by_admin_tg_id,
        )
    return ImageRecoveryDeadline(provider, settings.IMAGE_AUTO_REFUND_SECONDS, "environment")


async def set_image_recovery_policy(
    session: AsyncSession, provider: ImageProvider, auto_refund_seconds: int, *, admin_tg_id: int,
) -> ImageRecoveryDeadline:
    if provider not in _PROVIDERS:
        raise ValueError("Unsupported image provider")
    if isinstance(auto_refund_seconds, bool) or not _MIN_SECONDS <= auto_refund_seconds <= _MAX_SECONDS:
        raise ValueError("Image refund deadline is out of range")
    if not int(admin_tg_id):
        raise ValueError("Admin actor is required")
    await session.execute(
        pg_insert(ImageRecoveryPolicy)
        .values(
            provider=provider, auto_refund_seconds=settings.IMAGE_AUTO_REFUND_SECONDS,
            updated_by_admin_tg_id=None,
        )
        .on_conflict_do_nothing(index_elements=["provider"])
    )
    record = (await session.execute(
        select(ImageRecoveryPolicy)
        .where(ImageRecoveryPolicy.provider == provider)
        .with_for_update()
    )).scalar_one()
    previous = record.auto_refund_seconds
    if previous != auto_refund_seconds or record.updated_by_admin_tg_id is None:
        record.auto_refund_seconds = auto_refund_seconds
        record.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(ImageRecoveryPolicyAudit(
            provider=provider, previous_seconds=previous, new_seconds=auto_refund_seconds,
            changed_by_admin_tg_id=int(admin_tg_id),
        ))
    await session.commit()
    return ImageRecoveryDeadline(provider, record.auto_refund_seconds, "database", record.updated_by_admin_tg_id)
