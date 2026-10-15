"""Authenticated, audited provider order for the three Qwen-facing workflows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import QwenRoutingAudit, QwenRoutingSetting

QwenMode = Literal["text", "image", "video"]
QwenProvider = Literal["neironych", "kie"]
DEFAULT_ROUTES: dict[QwenMode, tuple[QwenProvider, QwenProvider | None]] = {
    "text": ("neironych", "kie"),
    "image": ("neironych", "kie"),
    # Neironych accepted video_url but failed to identify a synthetic red clip.
    # KIE Gemini 3.1 Pro identified it correctly; re-verify before changing this.
    "video": ("kie", None),
}


@dataclass(frozen=True)
class QwenRoute:
    mode: QwenMode
    primary_provider: QwenProvider
    backup_provider: QwenProvider | None
    source: str
    updated_by_admin_tg_id: int | None = None


def validate_route(mode: str, primary: str, backup: str | None) -> None:
    if mode not in DEFAULT_ROUTES:
        raise ValueError("Unknown Qwen workflow")
    if primary not in {"neironych", "kie"} or backup not in {None, "neironych", "kie"}:
        raise ValueError("Unsupported Qwen provider")
    if primary == backup:
        raise ValueError("Qwen backup provider must differ from primary")
    if mode == "video" and (primary == "neironych" or backup == "neironych"):
        raise ValueError("Neironych video understanding has not passed the visual contract test")


async def get_qwen_route(mode: QwenMode, session: AsyncSession | None = None) -> QwenRoute:
    validate_route(mode, *DEFAULT_ROUTES[mode])
    if session is None:
        from db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as own_session:
            return await get_qwen_route(mode, own_session)
    record = await session.get(QwenRoutingSetting, mode)
    if record is None:
        primary, backup = DEFAULT_ROUTES[mode]
        return QwenRoute(mode, primary, backup, "default")
    validate_route(mode, record.primary_provider, record.backup_provider)
    return QwenRoute(
        mode, record.primary_provider, record.backup_provider, "database",
        record.updated_by_admin_tg_id,
    )


async def set_qwen_route(
    session: AsyncSession, mode: QwenMode, primary: QwenProvider,
    backup: QwenProvider | None, *, admin_tg_id: int, source: Literal["web", "telegram"],
) -> QwenRoute:
    validate_route(mode, primary, backup)
    if not int(admin_tg_id) or source not in {"web", "telegram"}:
        raise ValueError("An authenticated admin and valid source are required")
    default_primary, default_backup = DEFAULT_ROUTES[mode]
    await session.execute(
        pg_insert(QwenRoutingSetting).values(
            mode=mode, primary_provider=default_primary, backup_provider=default_backup,
        ).on_conflict_do_nothing(index_elements=["mode"])
    )
    record = (await session.execute(
        select(QwenRoutingSetting).where(QwenRoutingSetting.mode == mode).with_for_update()
    )).scalar_one()
    old_primary = record.primary_provider
    old_backup = record.backup_provider
    if (record.updated_by_admin_tg_id is None or (old_primary, old_backup) != (primary, backup)):
        record.primary_provider = primary
        record.backup_provider = backup
        record.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(QwenRoutingAudit(
            mode=mode, previous_primary_provider=old_primary,
            previous_backup_provider=old_backup, new_primary_provider=primary,
            new_backup_provider=backup, changed_by_admin_tg_id=int(admin_tg_id), source=source,
        ))
    await session.commit()
    return QwenRoute(mode, record.primary_provider, record.backup_provider, "database", record.updated_by_admin_tg_id)
