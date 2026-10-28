"""Audited, revision-checked Wan routing; credentials never enter business settings."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.models import WanRoutingAudit, WanRoutingSetting

WanPolicy = Literal["neironych_kie", "kie_neironych", "neironych_only", "kie_only"]
MODELS = {"standard": "wan/3-0-video", "prime": "wan/3-0-video-prime"}


class WanRouteConflict(ValueError):
    pass


@dataclass(frozen=True)
class WanRoute:
    model_key: str
    policy: WanPolicy
    neironych_model_id: str
    revision: int = 0
    source: str = "bootstrap"
    updated_by_admin_tg_id: int | None = None


def validate_route(model: str, policy: str, native_id: str) -> None:
    if model not in MODELS.values() or policy not in {"neironych_kie", "kie_neironych", "neironych_only", "kie_only"}:
        raise ValueError("Unsupported Wan routing policy")
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,80}", native_id or ""):
        raise ValueError("Invalid Neironych model ID")
    if not re.fullmatch(r"wan-3(?:[._/-][A-Za-z0-9_./-]+)?", native_id) or ("prime" in native_id) != model.endswith("prime"):
        raise ValueError("Neironych mapping must preserve the Wan model family and variant")


def _bootstrap(model: str) -> WanRoute:
    if model not in MODELS.values():
        raise ValueError("Unknown Wan model")
    native = settings.WAN30_PRIME_NEIRONYCH_MODEL_ID if model == MODELS["prime"] else settings.WAN30_NEIRONYCH_MODEL_ID
    return WanRoute(model, "neironych_kie" if native.strip() else "kie_only", native.strip())


async def get_wan30_route(model: str, session: AsyncSession | None = None) -> WanRoute:
    default = _bootstrap(model)
    if session is None:
        from db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as own:
            return await get_wan30_route(model, own)
    row = await session.get(WanRoutingSetting, model)
    if row is None:
        return default
    validate_route(model, row.policy, row.neironych_model_id)
    return WanRoute(model, row.policy, row.neironych_model_id, row.revision, "database", row.updated_by_admin_tg_id)


async def set_wan30_route(
    session: AsyncSession, model: str, *, policy: WanPolicy,
    neironych_model_id: str, expected_revision: int,
    admin_tg_id: int, source: Literal["web", "telegram"],
) -> WanRoute:
    validate_route(model, policy, neironych_model_id)
    if not admin_tg_id or source not in {"web", "telegram"} or type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Authenticated admin and route revision required")
    default = _bootstrap(model)
    await session.execute(pg_insert(WanRoutingSetting).values(
        model_key=model, policy=default.policy,
        neironych_model_id=default.neironych_model_id, revision=0,
    ).on_conflict_do_nothing(index_elements=["model_key"]))
    row = (await session.execute(select(WanRoutingSetting).where(
        WanRoutingSetting.model_key == model,
    ).with_for_update())).scalar_one()
    if row.revision != expected_revision:
        raise WanRouteConflict("Настройки изменились. Обновите страницу перед сохранением.")
    revision = row.revision + 1
    session.add(WanRoutingAudit(
        model_key=model, previous_policy=row.policy, new_policy=policy,
        previous_model_id=row.neironych_model_id, new_model_id=neironych_model_id,
        revision=revision, changed_by_admin_tg_id=admin_tg_id, source=source,
    ))
    row.policy, row.neironych_model_id = policy, neironych_model_id
    row.revision, row.updated_by_admin_tg_id = revision, admin_tg_id
    await session.commit()
    return WanRoute(model, policy, neironych_model_id, revision, "database", admin_tg_id)
