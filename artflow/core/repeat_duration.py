"""Output-duration choices from the installed runtime catalog, shared by repeats."""
from __future__ import annotations

from core.model_pricing import split_pricing_variant_key


def duration_options(model: str) -> list[int]:
    # Read at call time: Seedance/Veo install their truthful public capabilities.
    from bot.keyboards.models import VIDEO_CAPS

    runtime, _ = split_pricing_variant_key(model)
    caps = VIDEO_CAPS.get(runtime, {})
    if caps.get("duration_from_source"):
        return []
    if runtime == "midjourney-video":
        return [5]
    return sorted({v for v in caps.get("duration_options", []) if type(v) is int and v > 0})


def resolve_repeat_duration(model: str, default: int, override: int | None, *, source_edit: bool = False) -> int:
    from bot.keyboards.models import VIDEO_CAPS

    runtime, _ = split_pricing_variant_key(model)
    caps = VIDEO_CAPS.get(runtime, {})
    if override is None:
        options = duration_options(runtime)
        # Provider-managed output is already fixed, including old 5/10s drafts.
        # Preserve their request identity, but quote the actual installed output.
        return options[0] if caps.get("provider_managed_duration") and len(options) == 1 else default
    if source_edit or caps.get("duration_from_source"):
        raise ValueError("Длительность определяется исходным видео; изменить её нельзя.")
    if type(override) is not int or override not in duration_options(runtime):
        raise ValueError("Выбери доступную для этой модели длительность.")
    return override


def duration_offer(model: str, default: int, effective: int, *, source_edit: bool = False) -> dict:
    options = [] if source_edit else duration_options(model)
    reason = (
        "Длительность определяется исходным видео. Оплата по измеренной длине."
        if source_edit or not options else "Модель поддерживает фиксированную длительность."
        if len(options) == 1 else None
    )
    return {"duration_options": options, "default_duration": default,
            "effective_duration": effective, "duration_lock_reason": reason}
