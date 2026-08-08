"""Shared, admin-editable APIX pricing seeds for MiniMax H3.

MiniMax H3 is one public product. KIE exposes three transport endpoints, but
quality pricing is the same user-facing choice regardless of the internally
selected T2V/I2V/Reference route.
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
PUBLIC_DISPLAY_NAME = "🎞 MiniMax H3"

# Initial editable APIX rates. Keep the existing 10:14 product ratio while
# exposing it consistently as the 768P / 2K quality choice for the family.
DEFAULT_CREDITS_PER_SECOND = 14.0
RESOLUTION_CREDITS = {"768P": 10.0, "2K": 14.0}
# Backwards-compatible name used by existing tests/admin code.
T2V_RESOLUTION_CREDITS = RESOLUTION_CREDITS

logger = logging.getLogger(__name__)


def credits_per_second(model_key: str, *, resolution: str | None = None) -> float:
    if model_key in MODEL_KEYS and resolution in RESOLUTION_CREDITS:
        return RESOLUTION_CREDITS[str(resolution)]
    return DEFAULT_CREDITS_PER_SECOND


def minimax_h3_model_cost_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model_key in MODEL_KEYS:
        internal_suffix = {
            T2V_MODEL: "",
            I2V_MODEL: " · internal I2V",
            REFERENCE_MODEL: " · internal Reference",
        }[model_key]
        rows.append(
            {
                "model_key": model_key,
                "display_name": f"{PUBLIC_DISPLAY_NAME}{internal_suffix}",
                "gen_type": GenerationType.video,
                "credits": credits_per_second(model_key),
            }
        )

    # Public quality variants are the source of truth for user billing.
    for resolution, credits in RESOLUTION_CREDITS.items():
        rows.append(
            {
                "model_key": pricing_variant_key(T2V_MODEL, resolution=resolution),
                "display_name": f"{PUBLIC_DISPLAY_NAME} · {resolution_label(resolution)} · за сек",
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
