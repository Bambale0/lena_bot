"""Shared, admin-editable APIX pricing seeds for MiniMax H3.

These are initial APIX credit rates, not a claim about KIE's retail USD price.
The base/variant rows are inserted idempotently and can be changed later from
the existing admin pricing UI without touching provider code.
"""
from __future__ import annotations

import logging
from typing import Any

from core.model_pricing import pricing_variant_key, resolution_label
from db.models import GenerationType

T2V_MODEL = "minimax-h3/text-to-video"
I2V_MODEL = "minimax-h3/image-to-video"
REFERENCE_MODEL = "minimax-h3/reference-to-video"
MODEL_KEYS = (T2V_MODEL, I2V_MODEL, REFERENCE_MODEL)

DISPLAY_NAMES = {
    T2V_MODEL: "🎞 MiniMax H3 Text",
    I2V_MODEL: "🎞 MiniMax H3 Image",
    REFERENCE_MODEL: "🎞 MiniMax H3 Reference",
}

# Initial editable APIX rates. H3's market pricing is commonly quoted around
# $0.10/s at 768p and $0.14/s at 2K, so the credit ratio is seeded 10:14.
DEFAULT_CREDITS_PER_SECOND = 14.0
T2V_RESOLUTION_CREDITS = {"768P": 10.0, "2K": 14.0}

logger = logging.getLogger(__name__)


def credits_per_second(model_key: str, *, resolution: str | None = None) -> float:
    if model_key == T2V_MODEL and resolution in T2V_RESOLUTION_CREDITS:
        return T2V_RESOLUTION_CREDITS[str(resolution)]
    return DEFAULT_CREDITS_PER_SECOND


def minimax_h3_model_cost_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model_key in MODEL_KEYS:
        rows.append(
            {
                "model_key": model_key,
                "display_name": DISPLAY_NAMES[model_key],
                "gen_type": GenerationType.video,
                "credits": credits_per_second(model_key),
            }
        )

    for resolution, credits in T2V_RESOLUTION_CREDITS.items():
        rows.append(
            {
                "model_key": pricing_variant_key(T2V_MODEL, resolution=resolution),
                "display_name": f"{DISPLAY_NAMES[T2V_MODEL]} · {resolution_label(resolution)} · за сек",
                "gen_type": GenerationType.video,
                "credits": credits,
            }
        )
    return rows


def install_minimax_h3_seed_rows() -> None:
    try:
        from db import seed
    except Exception as exc:  # pragma: no cover
        logger.warning("MiniMax H3 pricing seed hook skipped: %s", exc)
        return

    existing = {str(item.get("model_key") or "") for item in getattr(seed, "DEFAULT_MODEL_COSTS", [])}
    added = 0
    for row in minimax_h3_model_cost_rows():
        if row["model_key"] in existing:
            continue
        seed.DEFAULT_MODEL_COSTS.append(row)
        existing.add(row["model_key"])
        added += 1
    if added:
        logger.info("MiniMax H3 pricing seed rows installed: %d", added)
