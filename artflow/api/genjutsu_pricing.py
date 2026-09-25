"""Admin-editable APIX pricing seeds for Higgsfield Genjutsu."""
from __future__ import annotations

import logging
from typing import Any

from core.model_pricing import pricing_variant_key, resolution_label
from db.models import GenerationType

MOTION_MODEL = "higgsfield/genjutsu/motion-transfer"
OBJECT_MODEL = "higgsfield/genjutsu/object-swap"
MODEL_KEYS = (MOTION_MODEL, OBJECT_MODEL)

DISPLAY_NAMES = {
    MOTION_MODEL: "🥷 Genjutsu · Перенос движения",
    OBJECT_MODEL: "🥷 Genjutsu · Замена объекта",
}

DEFAULT_RESOLUTION = "480p"

# Initial editable APIX rates. These are seed values only: /admin/pricing and
# ModelCost remain the runtime source of truth, so price changes require no code
# or redeploy.
RESOLUTION_CREDITS_PER_SECOND: dict[str, float] = {
    "480p": 16.0,
    "720p": 35.0,
}

logger = logging.getLogger(__name__)


def genjutsu_model_cost_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model_key in MODEL_KEYS:
        display_name = DISPLAY_NAMES[model_key]
        rows.append(
            {
                "model_key": model_key,
                "display_name": display_name,
                "gen_type": GenerationType.video,
                "credits": RESOLUTION_CREDITS_PER_SECOND[DEFAULT_RESOLUTION],
            }
        )
        for resolution, credits in RESOLUTION_CREDITS_PER_SECOND.items():
            rows.append(
                {
                    "model_key": pricing_variant_key(model_key, resolution=resolution),
                    "display_name": (
                        f"{display_name} · {resolution_label(resolution)} · за сек"
                    ),
                    "gen_type": GenerationType.video,
                    "credits": credits,
                }
            )
    return rows


def install_genjutsu_seed_rows() -> None:
    try:
        from db import seed
    except Exception as exc:  # pragma: no cover
        logger.warning("Genjutsu pricing seed hook skipped: %s", exc)
        return

    existing = {
        str(item.get("model_key") or "")
        for item in getattr(seed, "DEFAULT_MODEL_COSTS", [])
    }
    added = 0
    for row in genjutsu_model_cost_rows():
        if row["model_key"] in existing:
            continue
        seed.DEFAULT_MODEL_COSTS.append(row)
        existing.add(row["model_key"])
        added += 1
    if added:
        logger.info("Genjutsu pricing seed rows installed: %d", added)
