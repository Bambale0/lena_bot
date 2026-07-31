from __future__ import annotations

from datetime import datetime
from typing import Any

from db.models import PromptStatus, UserPrompt

TREND_TAG = "trend"
TREND_VIDEO_TAG = "trend-video"
TREND_PREFIX = "trend-"


def normalized_tags(prompt_or_tags: UserPrompt | list[str] | tuple[str, ...] | None) -> set[str]:
    raw = getattr(prompt_or_tags, "tags", prompt_or_tags) or []
    return {str(item).strip().lower() for item in raw if str(item or "").strip()}


def is_trend_prompt(prompt: UserPrompt | None) -> bool:
    return bool(prompt and TREND_TAG in normalized_tags(prompt))


def trend_kind(prompt: UserPrompt) -> str:
    tags = normalized_tags(prompt)
    return "video" if TREND_VIDEO_TAG in tags else "image"


def _tag_value(tags: set[str], prefix: str) -> str | None:
    for tag in tags:
        if tag.startswith(prefix):
            value = tag[len(prefix):].strip()
            if value:
                return value
    return None


def trend_settings(prompt: UserPrompt) -> dict[str, Any]:
    tags = normalized_tags(prompt)
    kind = trend_kind(prompt)
    duration_raw = _tag_value(tags, "trend-duration:")
    try:
        duration = int(duration_raw) if duration_raw else None
    except (TypeError, ValueError):
        duration = None

    requires_reference = "trend-requires-reference" in tags
    scenario = _tag_value(tags, "trend-scenario:")
    if scenario in {"image", "imgtxt", "i2v"}:
        requires_reference = True

    return {
        "scenario": scenario or ("image" if requires_reference else "text"),
        "duration": duration,
        "ratio": _tag_value(tags, "trend-ratio:"),
        "quality": _tag_value(tags, "trend-quality:"),
        "resolution": _tag_value(tags, "trend-resolution:"),
        "requires_reference": requires_reference,
        "kind": kind,
    }


def build_trend_tags(kind: str, settings: dict[str, Any] | None = None) -> list[str]:
    kind = "video" if str(kind).lower() == "video" else "image"
    settings = dict(settings or {})
    tags = [TREND_TAG]
    if kind == "video":
        tags.append(TREND_VIDEO_TAG)

    scenario = str(settings.get("scenario") or "").strip().lower()
    if scenario:
        tags.append(f"trend-scenario:{scenario}")
    duration = settings.get("duration")
    if duration not in (None, ""):
        tags.append(f"trend-duration:{int(duration)}")
    ratio = str(settings.get("ratio") or "").strip()
    if ratio:
        tags.append(f"trend-ratio:{ratio}")
    quality = str(settings.get("quality") or "").strip()
    if quality:
        tags.append(f"trend-quality:{quality}")
    resolution = str(settings.get("resolution") or "").strip()
    if resolution:
        tags.append(f"trend-resolution:{resolution}")
    if bool(settings.get("requires_reference")):
        tags.append("trend-requires-reference")
    return list(dict.fromkeys(tags))


def trend_is_public(prompt: UserPrompt | None) -> bool:
    return bool(
        is_trend_prompt(prompt)
        and prompt.status == PromptStatus.approved
        and prompt.is_public
    )


def trend_public_payload(prompt: UserPrompt) -> dict[str, Any]:
    created_at: datetime | None = getattr(prompt, "created_at", None)
    return {
        "id": int(prompt.id),
        "kind": trend_kind(prompt),
        "title": prompt.title,
        "description": prompt.description,
        "preview_url": prompt.preview_url,
        "model": prompt.model,
        "settings": trend_settings(prompt),
        "uses_count": int(prompt.uses_count or 0),
        "likes": int(prompt.likes or 0),
        "created_at": created_at.isoformat() if created_at else "",
    }


def trend_admin_payload(prompt: UserPrompt) -> dict[str, Any]:
    payload = trend_public_payload(prompt)
    payload.update({
        "prompt_template": prompt.prompt_text,
        "status": getattr(prompt.status, "value", str(prompt.status)),
        "is_public": bool(prompt.is_public),
        "author_id": int(prompt.author_id),
    })
    return payload
