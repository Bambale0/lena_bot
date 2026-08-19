"""Keep the canonical Kling 3.0 Motion Control rows visible in production.

The provider contract and Mini App renderer already support the model. This guard
repairs stale production pricing rows that were disabled or missed by an older
seed, so `/models/video` can expose the model again without inventing a frontend
fallback that billing cannot resolve.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from core.model_pricing import pricing_variant_key
from db.models import GenerationType, ModelCost

logger = logging.getLogger(__name__)

KLING_30_MOTION = "kling-3.0/motion-control"
_REQUIRED_ROWS = (
    (KLING_30_MOTION, "🕺 Kling 3.0 Motion", 9.0),
    (
        pricing_variant_key(KLING_30_MOTION, resolution="720p"),
        "🕺 Kling 3.0 Motion · 720p · за сек",
        9.0,
    ),
    (
        pricing_variant_key(KLING_30_MOTION, resolution="1080p"),
        "🕺 Kling 3.0 Motion · 1080p · за сек",
        11.0,
    ),
)


async def _ensure_required_rows(session: Any) -> None:
    keys = [key for key, _name, _credits in _REQUIRED_ROWS]
    result = await session.execute(
        select(ModelCost).where(ModelCost.model_key.in_(keys))
    )
    existing = {row.model_key: row for row in result.scalars().all()}
    changed = False

    for model_key, display_name, credits in _REQUIRED_ROWS:
        row = existing.get(model_key)
        if row is None:
            session.add(
                ModelCost(
                    model_key=model_key,
                    display_name=display_name,
                    gen_type=GenerationType.video,
                    credits=credits,
                    is_active=True,
                )
            )
            changed = True
            continue

        if not bool(getattr(row, "is_active", False)):
            row.is_active = True
            changed = True

    if changed:
        await session.commit()
        logger.warning(
            "Repaired required Mini App model visibility: %s",
            KLING_30_MOTION,
        )


def install_kling_motion_visibility(repository: Any) -> None:
    if getattr(repository, "_kling_motion_visibility_installed", False):
        return

    original_get_all = repository.get_all_model_costs

    async def get_all_model_costs(session: Any):
        try:
            await _ensure_required_rows(session)
        except Exception as exc:
            try:
                await session.rollback()
            except Exception:
                pass
            logger.warning("Could not repair Kling 3.0 Motion visibility: %s", exc)
        return await original_get_all(session)

    repository.get_all_model_costs = get_all_model_costs
    repository._kling_motion_visibility_installed = True
