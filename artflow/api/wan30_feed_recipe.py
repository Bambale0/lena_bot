"""Restore a public Wan recipe with reader photos, never the author's identity.

No network, supplier lookup or financial operations. Call only after the public
source and model have been authorized. Durations are re-probed at checkout.
"""
from __future__ import annotations

from typing import Any

from api.wan30_contract import WAN30_MODELS
from api.wan30_launch import _clean_urls


def required_reader_photos(model: str, params: dict[str, Any]) -> int | None:
    """Public count only; unknown recipes remain subject to checkout validation."""
    snapshot = params.get("wan30_request")
    if model not in WAN30_MODELS or not isinstance(snapshot, dict) or snapshot.get("model") != model:
        return None
    mode = snapshot.get("mode")
    if mode not in {"text", "first", "first_last", "reference", "edit", "file", "link"}:
        return None
    return 2 if mode == "first_last" else 1 if mode == "first" else len(
        _clean_urls(snapshot.get("reference_image_urls"))
    )


def restore_feed_recipe(model: str, params: dict[str, Any], photos: list[str]) -> dict[str, Any]:
    if model not in WAN30_MODELS:
        raise ValueError("Unsupported Wan repeat model")
    snapshot = params.get("wan30_request")
    if snapshot is None:
        # Legacy recipes still use the strict constructor/quote, not the
        # provider's request history. Do not manufacture missing source media.
        return {}
    if not isinstance(snapshot, dict) or snapshot.get("model") != model:
        raise ValueError("Исходные параметры Wan недоступны; кредиты не списаны.")
    mode = snapshot.get("mode")
    if mode not in {"text", "first", "first_last", "reference", "edit", "file", "link"}:
        raise ValueError("Исходный режим Wan недоступен; кредиты не списаны.")
    refs = list(dict.fromkeys(photos))
    required = required_reader_photos(model, params)
    assert required is not None  # Canonical snapshot validated above.
    if len(refs) < required or (mode in {"first", "first_last"} and len(refs) != required):
        raise ValueError(f"Для повтора Wan добавь {required} своих фото; кредиты не списаны.")
    videos = list(_clean_urls(snapshot.get("reference_video_urls")))
    # A text recipe with a reader photo is deliberately image-conditioned;
    # reference recipes must not become first/last-frame mode by photo count.
    source_mode = "reference" if mode == "text" and refs else mode
    return {
        "mode": "video" if mode == "edit" else "image" if mode in {"first", "first_last"} else "text",
        "duration": snapshot.get("duration"),
        "resolution": snapshot.get("resolution"),
        "aspect_ratio": snapshot.get("aspect_ratio"),
        "seed": snapshot.get("seed"),
        "reference_video_url": videos[0] if videos else None,
        "wan_source_mode": source_mode,
        "wan_audio": snapshot.get("audio", True),
        "wan_nsfw_checker": snapshot.get("nsfw_checker", True),
        "wan_reference_image_urls": refs if source_mode == "reference" else [],
        "wan_reference_video_urls": videos,
        "wan_reference_audio_urls": list(_clean_urls(snapshot.get("reference_audio_urls"))),
        "wan_reference_file_urls": list(_clean_urls(snapshot.get("reference_file_urls"))),
        "wan_reference_link_urls": list(_clean_urls(snapshot.get("reference_link_urls"))),
        "wan_first_frame_url": refs[0] if mode in {"first", "first_last"} else None,
        "wan_last_frame_url": refs[1] if mode == "first_last" else None,
    }


def recipe_options(data: dict[str, Any]) -> dict[str, Any]:
    """Select constructor fields only; measured durations never come from JSON."""
    return {
        "source_mode": data.get("wan_source_mode"),
        "audio": data.get("wan_audio", True),
        "nsfw_checker": data.get("wan_nsfw_checker", True),
        "seed": data.get("seed"),
        **{key: data.get("wan_" + key, []) for key in (
            "reference_image_urls", "reference_video_urls", "reference_audio_urls",
            "reference_file_urls", "reference_link_urls",
        )},
        "first_frame_url": data.get("wan_first_frame_url"),
        "last_frame_url": data.get("wan_last_frame_url"),
    }
