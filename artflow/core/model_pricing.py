from __future__ import annotations

from typing import Iterable


QUALITY_LABELS: dict[str, str] = {
    "basic": "2K",
    "high": "4K",
    "1K": "1K",
    "2K": "2K",
    "4K": "4K",
}

RESOLUTION_LABELS: dict[str, str] = {
    "std": "Std",
    "pro": "Pro",
    "2K": "2K",
    "4K": "4K",
    "480p": "480p",
    "720p": "720p",
    "1080p": "1080p",
}


def pricing_variant_key(
    model_key: str,
    *,
    quality: str | None = None,
    duration: int | None = None,
    resolution: str | None = None,
) -> str:
    parts: list[str] = []
    if quality:
        parts.append(f"quality={quality}")
    if duration is not None:
        parts.append(f"duration={duration}")
    if resolution:
        parts.append(f"resolution={resolution}")
    if not parts:
        return model_key
    return f"{model_key}__{'__'.join(parts)}"


def image_pricing_keys(model_key: str, quality: str | None = None) -> list[str]:
    keys: list[str] = []
    if quality:
        keys.append(pricing_variant_key(model_key, quality=quality))
    keys.append(model_key)
    return _unique(keys)


def video_pricing_keys(
    model_key: str,
    *,
    duration: int | None = None,
    resolution: str | None = None,
) -> list[str]:
    """Pricing lookup: full match → resolution-only → duration-only → base."""
    keys: list[str] = []
    if resolution and duration is not None:
        keys.append(pricing_variant_key(model_key, duration=duration, resolution=resolution))
    if resolution:
        keys.append(pricing_variant_key(model_key, resolution=resolution))
    if duration is not None:
        keys.append(pricing_variant_key(model_key, duration=duration))
    keys.append(model_key)
    return _unique(keys)


def quality_label(value: str | None) -> str | None:
    if not value:
        return None
    return QUALITY_LABELS.get(value, value)


def resolution_label(value: str | None) -> str | None:
    if not value:
        return None
    return RESOLUTION_LABELS.get(value, value)


def duration_label(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{value} сек"


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
