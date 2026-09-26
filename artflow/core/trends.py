from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Mapping

from db.models import PromptStatus, UserPrompt

TREND_TAG = "trend"
TREND_VIDEO_TAG = "trend-video"
TREND_PREFIX = "trend-"
TREND_CATEGORY_PREFIX = "trend-category:"
TREND_USER_FIELDS_PREFIX = "trend-user-fields:"
TREND_MIN_REFERENCES_PREFIX = "trend-min-references:"
TREND_MAX_REFERENCES_PREFIX = "trend-max-references:"
DEFAULT_TREND_CATEGORY = "featured"
MAX_TREND_USER_FIELDS = 6
MAX_TREND_FIELD_VALUE_LENGTH = 160
MAX_TREND_REFERENCES = 8
TREND_CATEGORIES: dict[str, dict[str, str]] = {
    "featured": {"title": "Тренды", "emoji": "🔥"},
    "photo-video": {"title": "Фото → видео", "emoji": "🎬"},
    "portrait": {"title": "Портреты", "emoji": "✨"},
    "cartoon": {"title": "Мультфильм", "emoji": "🎨"},
    "animals": {"title": "С животными", "emoji": "🦁"},
    "holidays": {"title": "Праздники", "emoji": "🎉"},
    "style": {"title": "Образы", "emoji": "💫"},
}
_FIELD_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
_NUMBER_RE = re.compile(r"^-?\d+(?:[\.,]\d+)?$")


def _raw_tags(prompt_or_tags: UserPrompt | list[str] | tuple[str, ...] | None) -> list[str]:
    raw = getattr(prompt_or_tags, "tags", prompt_or_tags) or []
    return [str(item).strip() for item in raw if str(item or "").strip()]


def normalized_tags(prompt_or_tags: UserPrompt | list[str] | tuple[str, ...] | None) -> set[str]:
    return {item.lower() for item in _raw_tags(prompt_or_tags)}


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


def _raw_tag_value(
    prompt_or_tags: UserPrompt | list[str] | tuple[str, ...] | None,
    prefix: str,
) -> str | None:
    for tag in _raw_tags(prompt_or_tags):
        if tag.lower().startswith(prefix.lower()):
            value = tag[len(prefix):].strip()
            if value:
                return value
    return None


def normalize_trend_category(value: Any) -> str:
    category = str(value or "").strip().lower()
    return category if category in TREND_CATEGORIES else DEFAULT_TREND_CATEGORY


def _safe_reference_limit(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(1, min(MAX_TREND_REFERENCES, parsed))


def normalize_trend_user_fields(raw_fields: Any) -> list[dict[str, Any]]:
    if raw_fields in (None, ""):
        return []
    if not isinstance(raw_fields, list) or len(raw_fields) > MAX_TREND_USER_FIELDS:
        raise ValueError(f"В одном тренде можно настроить не больше {MAX_TREND_USER_FIELDS} полей")

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_fields:
        if not isinstance(raw, Mapping):
            raise ValueError("Поля тренда настроены неверно")
        key = str(raw.get("key") or "").strip()
        label = str(raw.get("label") or key).strip()
        field_type = str(raw.get("type") or "text").strip().lower()
        if not _FIELD_KEY_RE.fullmatch(key) or not label or len(label) > 64:
            raise ValueError("Поля тренда настроены неверно")
        if field_type not in {"text", "number"}:
            raise ValueError(f"Неподдерживаемый тип поля «{label}»")
        if key.casefold() in seen:
            raise ValueError("Поля тренда не должны повторяться")
        seen.add(key.casefold())
        try:
            max_length = int(raw.get("max_length") or MAX_TREND_FIELD_VALUE_LENGTH)
        except (TypeError, ValueError):
            max_length = MAX_TREND_FIELD_VALUE_LENGTH
        result.append(
            {
                "key": key,
                "label": label,
                "type": field_type,
                "required": bool(raw.get("required", True)),
                "placeholder": str(raw.get("placeholder") or "")[:80],
                "max_length": max(1, min(MAX_TREND_FIELD_VALUE_LENGTH, max_length)),
            }
        )
    return result


def trend_category(prompt: UserPrompt) -> str:
    return normalize_trend_category(_tag_value(normalized_tags(prompt), TREND_CATEGORY_PREFIX))


def trend_category_payload(category: str) -> dict[str, str]:
    key = normalize_trend_category(category)
    meta = TREND_CATEGORIES[key]
    return {"key": key, "title": meta["title"], "emoji": meta["emoji"]}


def trend_settings(prompt: UserPrompt) -> dict[str, Any]:
    """Resolve the server-owned trend recipe stored in tag-backed metadata."""
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

    fields_raw = _raw_tag_value(prompt, TREND_USER_FIELDS_PREFIX)
    try:
        user_fields = normalize_trend_user_fields(json.loads(fields_raw)) if fields_raw else []
    except (json.JSONDecodeError, ValueError, TypeError):
        user_fields = []

    min_references = _safe_reference_limit(
        _tag_value(tags, TREND_MIN_REFERENCES_PREFIX),
        1,
    )
    max_references = _safe_reference_limit(
        _tag_value(tags, TREND_MAX_REFERENCES_PREFIX),
        max(1, min_references),
    )
    max_references = max(min_references, max_references)

    return {
        "scenario": scenario or ("image" if requires_reference else "text"),
        "duration": duration,
        "ratio": _tag_value(tags, "trend-ratio:"),
        "quality": _tag_value(tags, "trend-quality:"),
        "resolution": _tag_value(tags, "trend-resolution:"),
        # APIX legacy trends launch with at least one user image. Keep that
        # contract while allowing new templates to request more identity refs.
        "requires_reference": True,
        "min_references": min_references,
        "max_references": max_references,
        "user_fields": user_fields,
        "kind": kind,
        "category": trend_category(prompt),
        "settings_version": 2 if user_fields or max_references > 1 else 1,
    }


def build_trend_tags(kind: str, settings: dict[str, Any] | None = None) -> list[str]:
    kind = "video" if str(kind).lower() == "video" else "image"
    settings = dict(settings or {})
    tags = [TREND_TAG, f"{TREND_CATEGORY_PREFIX}{normalize_trend_category(settings.get('category'))}"]
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

    min_references = _safe_reference_limit(settings.get("min_references"), 1)
    max_references = max(
        min_references,
        _safe_reference_limit(settings.get("max_references"), min_references),
    )
    tags.append(f"{TREND_MIN_REFERENCES_PREFIX}{min_references}")
    tags.append(f"{TREND_MAX_REFERENCES_PREFIX}{max_references}")

    user_fields = normalize_trend_user_fields(settings.get("user_fields"))
    if user_fields:
        tags.append(
            TREND_USER_FIELDS_PREFIX
            + json.dumps(user_fields, ensure_ascii=False, separators=(",", ":"))
        )
    if bool(settings.get("requires_reference")) or min_references > 0:
        tags.append("trend-requires-reference")
    return list(dict.fromkeys(tags))


def render_trend_prompt(prompt: str, user_fields: list[dict[str, Any]], raw_values: Any) -> str:
    """Render validated user choices into the hidden server-side trend prompt."""
    if raw_values in (None, ""):
        values: dict[str, str] = {}
    elif isinstance(raw_values, Mapping) and len(raw_values) <= MAX_TREND_USER_FIELDS:
        values = {
            str(key).strip(): str(value if value is not None else "").strip()
            for key, value in raw_values.items()
        }
    else:
        raise ValueError("Некорректные поля тренда")

    fields = normalize_trend_user_fields(user_fields)
    allowed = {field["key"] for field in fields}
    if set(values) - allowed:
        raise ValueError("Переданы лишние поля тренда")

    validated: dict[str, str] = {}
    for field in fields:
        key = field["key"]
        value = values.get(key, "")
        if not value and field["required"]:
            raise ValueError(f"Заполните поле «{field['label']}»")
        if len(value) > field["max_length"]:
            raise ValueError(f"Слишком длинное значение поля «{field['label']}»")
        if value and field["type"] == "number" and not _NUMBER_RE.fullmatch(value):
            raise ValueError(f"Поле «{field['label']}» должно быть числом")
        validated[key] = value

    rendered = str(prompt or "").strip()
    for field in fields:
        rendered = re.sub(
            r"\{\{\s*" + re.escape(field["key"]) + r"\s*\}\}",
            lambda _match, value=validated[field["key"]]: value,
            rendered,
        )

    overrides = "\n".join(
        f"- {field['label']}: {validated[field['key']]}"
        for field in fields
        if validated[field["key"]]
    )
    if overrides:
        rendered += (
            "\n\nВАЖНО: примените следующие параметры пользователя как приоритетные изменения. "
            "Если они противоречат исходному prompt, значения ниже имеют приоритет. "
            "Остальные детали сохраните без изменений:\n"
            + overrides
        )
    return rendered.strip()


def trend_is_public(prompt: UserPrompt | None) -> bool:
    return bool(
        is_trend_prompt(prompt)
        and prompt.status == PromptStatus.approved
        and prompt.is_public
    )


def trend_public_payload(prompt: UserPrompt) -> dict[str, Any]:
    created_at: datetime | None = getattr(prompt, "created_at", None)
    category = trend_category_payload(trend_category(prompt))
    kind = trend_kind(prompt)
    settings = trend_settings(prompt)
    minimum = int(settings["min_references"])
    maximum = int(settings["max_references"])
    hint = (
        "Загрузите одно чёткое фото. Остальные настройки тренда уже сохранены."
        if maximum == 1
        else f"Добавьте {minimum}–{maximum} фото-референса. Можно использовать разные ракурсы нужного человека или объекта."
    )
    return {
        "id": int(prompt.id),
        "kind": kind,
        "category": category["key"],
        "category_title": category["title"],
        "category_emoji": category["emoji"],
        "title": prompt.title,
        "description": prompt.description,
        "user_photo_hint": hint,
        "preview_url": prompt.preview_url,
        "min_references": minimum,
        "max_references": maximum,
        "user_fields": settings["user_fields"],
        "status": "active" if trend_is_public(prompt) else "inactive",
        "uses_count": int(prompt.uses_count or 0),
        "likes": int(prompt.likes or 0),
        "created_at": created_at.isoformat() if created_at else "",
    }


def trend_admin_payload(prompt: UserPrompt) -> dict[str, Any]:
    payload = trend_public_payload(prompt)
    payload.update({
        "prompt_template": prompt.prompt_text,
        "model": prompt.model,
        "settings": trend_settings(prompt),
        "status": getattr(prompt.status, "value", str(prompt.status)),
        "is_public": bool(prompt.is_public),
        "author_id": int(prompt.author_id),
    })
    return payload
