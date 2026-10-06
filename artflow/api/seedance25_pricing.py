"""Seedance 2.5 pricing helpers.

The Mini App, Telegram bot and web admin must all read the same DB-backed
`ModelCost` rows. Seedance 2.5 was introduced as a runtime adapter first, so
this module injects real seed rows before `db.seed.run_seed()` executes.
"""
from __future__ import annotations

import logging
from typing import Any

from core.model_pricing import pricing_variant_key, resolution_label
from db.models import GenerationType

MODEL_KEY = "bytedance/seedance-2-5"
DISPLAY_NAME = "🌱 Seedance 2.5"
DEFAULT_RESOLUTION = "480p"
CREDITS_PER_SECOND: dict[str, float] = {"480p": 7.0, "720p": 10.0}

logger = logging.getLogger(__name__)


def seedance25_model_cost_rows() -> list[dict[str, Any]]:
    """Return base + resolution-variant rows editable from `/admin/pricing`."""
    rows: list[dict[str, Any]] = [
        {
            "model_key": MODEL_KEY,
            "display_name": DISPLAY_NAME,
            "gen_type": GenerationType.video,
            "credits": CREDITS_PER_SECOND[DEFAULT_RESOLUTION],
        }
    ]
    for resolution, credits in CREDITS_PER_SECOND.items():
        rows.append(
            {
                "model_key": pricing_variant_key(MODEL_KEY, resolution=resolution),
                "display_name": f"{DISPLAY_NAME} · {resolution_label(resolution)} · за сек",
                "gen_type": GenerationType.video,
                "credits": credits,
            }
        )
    return rows


def install_seedance25_seed_rows() -> None:
    """Patch `db.seed.DEFAULT_MODEL_COSTS` before the idempotent seed runs.

    This avoids a second pricing source: after deploy, rows are inserted into the
    database if missing, then both the Mini App and the Telegram bot resolve the
    same admin-editable `ModelCost` records.
    """
    try:
        from db import seed
    except Exception as exc:  # pragma: no cover - defensive bootstrap guard
        logger.warning("Seedance 2.5 pricing seed hook skipped: %s", exc)
        return

    existing = {str(item.get("model_key") or "") for item in getattr(seed, "DEFAULT_MODEL_COSTS", [])}
    added = 0
    for row in seedance25_model_cost_rows():
        if row["model_key"] in existing:
            continue
        seed.DEFAULT_MODEL_COSTS.append(row)
        existing.add(row["model_key"])
        added += 1
    if added:
        logger.info("Seedance 2.5 pricing seed rows installed: %d", added)
