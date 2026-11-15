"""Public-safe photo count and actionable precharge validation for feed video repeats.

Never expose the creator's hidden prompt or private reference URLs. Only
the number of reader-supplied images required by the original input recipe.
"""
from __future__ import annotations

from typing import Any

from api.seedance25_adapter import MODEL_KEY as SEEDANCE25_MODEL_KEY
from api.wan30_feed_recipe import required_reader_photos
from core.neironych_seedance_contract import (
    SeedanceContractError,
    _prompt_reference_requirements,
    canonical_seedance_model,
)


def required_feed_reader_photos(
    model: str, inputs: dict[str, Any], source_prompt: str,
) -> int | None:
    """Return an exact public count for known repeat contracts; None if unknown."""
    wan_count = required_reader_photos(model, inputs)
    if wan_count is not None:
        return wan_count
    if model != SEEDANCE25_MODEL_KEY:
        try:
            canonical_seedance_model(model)
        except SeedanceContractError:
            return None
    # Seedance's own local contract counts @ImageN as requiring N image slots.
    # The replay product always asks for at least one reader photo.
    return max(1, _prompt_reference_requirements(source_prompt)["image"])


def reader_photo_shortfall_message(required: int, uploaded: int) -> str:
    remaining = max(0, required - uploaded)
    if remaining <= 0:
        raise ValueError("No missing reader images")
    next_ref = f"@Image{uploaded + 1}"
    last_ref = f"@Image{required}"
    index_label = next_ref if remaining == 1 else f"{next_ref}–{last_ref}"
    return (
        f"Для повтора нужно фото: {required}. Загружено: {uploaded}. "
        f"Добавь ещё {remaining} фото ({index_label}); поцелуи не списаны."
    )
