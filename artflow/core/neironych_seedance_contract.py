from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


class SeedanceContractError(ValueError):
    """Request is invalid for the documented Neironych Seedance contract."""


@dataclass(frozen=True, slots=True)
class SeedanceSpec:
    model: str
    min_duration: int
    max_duration: int
    resolutions: tuple[str, ...]
    max_image_refs: int
    max_video_refs: int
    max_audio_refs: int
    max_total_refs: int
    supports_edit: bool


SEEDANCE_MODELS = ("seedance-2.0", "seedance-2.5")
SEEDANCE_FIXED_ASPECT_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "21:9")
SEEDANCE_MODEL_ALIASES: dict[str, tuple[str, ...]] = {
    "seedance-2.0": (
        "seedance-2.0",
        "seedance-2",
        "bytedance/seedance-2.0",
        "bytedance/seedance-2",
    ),
    "seedance-2.5": (
        "seedance-2.5",
        "bytedance/seedance-2.5",
    ),
}

_SPECS = {
    "seedance-2.0": SeedanceSpec(
        model="seedance-2.0",
        min_duration=4,
        max_duration=15,
        resolutions=("480p", "720p", "1080p", "4k"),
        max_image_refs=9,
        max_video_refs=3,
        max_audio_refs=3,
        max_total_refs=12,
        supports_edit=False,
    ),
    "seedance-2.5": SeedanceSpec(
        model="seedance-2.5",
        min_duration=4,
        max_duration=30,
        resolutions=("480p", "720p", "1080p"),
        max_image_refs=30,
        max_video_refs=10,
        max_audio_refs=10,
        max_total_refs=50,
        supports_edit=True,
    ),
}

_MAX_PROMPT_BYTES = 40_000
_REFERENCE_RE = re.compile(r"@(Image|Video|Audio)\s*(\d+)", flags=re.IGNORECASE)
_ALWAYS_DROP_FIELDS = {
    "return_last_frame",
    "output_format",
    "web_search",
    "nsfw_checker",
    "fixed_lens",
    "seed",
    "watermark",
}


def get_seedance_spec(model: str) -> SeedanceSpec:
    try:
        return _SPECS[str(model or "").strip()]
    except KeyError as exc:
        raise SeedanceContractError(f"Неподдерживаемая модель Seedance: {model}") from exc


def resolve_seedance_model(selected_model: str, available_models: list[str]) -> str | None:
    aliases = SEEDANCE_MODEL_ALIASES.get(str(selected_model or "").strip(), ())
    available = {str(item or "").strip() for item in available_models if str(item or "").strip()}
    return next((alias for alias in aliases if alias in available), None)


def enabled_seedance_models(available_models: list[str]) -> tuple[str, ...]:
    return tuple(
        model
        for model in SEEDANCE_MODELS
        if resolve_seedance_model(model, available_models) is not None
    )


def _https_item(value: Any, *, field: str) -> dict[str, str]:
    raw = value.get("url") if isinstance(value, dict) else value
    url = str(raw or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SeedanceContractError(f"{field}: нужен публичный HTTPS URL.")
    if parsed.username or parsed.password:
        raise SeedanceContractError(f"{field}: URL с логином/паролем не поддерживается.")
    return {"url": url}


def _reference_list(
    payload: dict[str, Any],
    *,
    canonical: str,
    aliases: tuple[str, ...],
    maximum: int,
) -> list[dict[str, str]]:
    raw = payload.get(canonical)
    if raw in (None, ""):
        for alias in aliases:
            if payload.get(alias) not in (None, ""):
                raw = payload.get(alias)
                break
    for alias in aliases:
        payload.pop(alias, None)

    if raw in (None, ""):
        payload.pop(canonical, None)
        return []
    if not isinstance(raw, list):
        raise SeedanceContractError(f"{canonical}: ожидается массив.")

    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        normalized = _https_item(item, field=canonical)
        if normalized["url"] not in seen:
            result.append(normalized)
            seen.add(normalized["url"])
    if len(result) > maximum:
        raise SeedanceContractError(f"{canonical}: максимум {maximum} референсов.")
    if result:
        payload[canonical] = result
    else:
        payload.pop(canonical, None)
    return result


def _frame(
    payload: dict[str, Any],
    *,
    canonical: str,
    aliases: tuple[str, ...],
) -> dict[str, str] | None:
    raw = payload.get(canonical)
    if raw in (None, ""):
        for alias in aliases:
            if payload.get(alias) not in (None, ""):
                raw = payload.get(alias)
                break
    for alias in aliases:
        payload.pop(alias, None)
    if raw in (None, ""):
        payload.pop(canonical, None)
        return None
    normalized = _https_item(raw, field=canonical)
    payload[canonical] = normalized
    return normalized


def _validate_prompt(payload: dict[str, Any]) -> str:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise SeedanceContractError("Промпт не может быть пустым.")
    if len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
        raise SeedanceContractError("Промпт Seedance превышает лимит 40 000 байт UTF-8.")
    payload["prompt"] = prompt
    return prompt


def _prompt_reference_requirements(prompt: str) -> dict[str, int]:
    result = {"image": 0, "video": 0, "audio": 0}
    for kind, raw_index in _REFERENCE_RE.findall(prompt):
        key = kind.lower()
        result[key] = max(result[key], int(raw_index))
    return result


def normalize_seedance_request(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize documented Seedance fields before any paid provider call.

    Unknown future provider fields intentionally pass through for the admin-only
    raw JSON escape hatch, while known legacy/unsupported fields are removed and
    current documented invariants are enforced locally.
    """

    spec = get_seedance_spec(model)
    payload = deepcopy(input_data)
    payload.pop("model", None)

    for field in _ALWAYS_DROP_FIELDS:
        payload.pop(field, None)

    if payload.get("generate_audio") is False:
        raise SeedanceContractError("Seedance не поддерживает generate_audio=false.")
    if "generate_audio" in payload and not isinstance(payload["generate_audio"], bool):
        raise SeedanceContractError("generate_audio должен быть boolean.")

    prompt = _validate_prompt(payload)

    task_type = str(payload.get("omni_reference_task_type") or "").strip().lower()
    if task_type:
        if model != "seedance-2.5":
            payload.pop("omni_reference_task_type", None)
            task_type = ""
        elif task_type not in {"auto", "reference", "edit"}:
            raise SeedanceContractError(
                "omni_reference_task_type: auto, reference или edit."
            )
        else:
            payload["omni_reference_task_type"] = task_type

    duration = payload.get("duration")
    if duration not in (None, ""):
        try:
            duration_value = int(duration)
        except (TypeError, ValueError) as exc:
            raise SeedanceContractError("duration должен быть целым числом.") from exc
        if model == "seedance-2.5" and task_type == "edit" and duration_value == -1:
            payload["duration"] = -1
        elif not spec.min_duration <= duration_value <= spec.max_duration:
            raise SeedanceContractError(
                f"duration для {model}: {spec.min_duration}–{spec.max_duration} секунд."
            )
        else:
            payload["duration"] = duration_value

    resolution = str(payload.get("resolution") or "").strip()
    if resolution == "4K":
        resolution = "4k"
    if resolution:
        if resolution not in spec.resolutions:
            raise SeedanceContractError(
                f"resolution для {model}: {', '.join(spec.resolutions)}."
            )
        payload["resolution"] = resolution

    images = _reference_list(
        payload,
        canonical="reference_images",
        aliases=("reference_image_urls", "image_urls"),
        maximum=spec.max_image_refs,
    )
    videos = _reference_list(
        payload,
        canonical="reference_videos",
        aliases=("reference_video_urls", "video_urls"),
        maximum=spec.max_video_refs,
    )
    audios = _reference_list(
        payload,
        canonical="reference_audios",
        aliases=("reference_audio_urls", "audio_urls"),
        maximum=spec.max_audio_refs,
    )
    total = len(images) + len(videos) + len(audios)
    if total > spec.max_total_refs:
        raise SeedanceContractError(
            f"Для {model} максимум {spec.max_total_refs} референсов суммарно."
        )
    if model == "seedance-2.0" and audios and not (images or videos):
        raise SeedanceContractError(
            "Для Seedance 2.0 аудио-референс требует хотя бы одно фото или видео."
        )

    start_image = _frame(
        payload,
        canonical="start_image",
        aliases=("first_frame_url", "image_url"),
    )
    end_image = _frame(
        payload,
        canonical="end_image",
        aliases=("last_frame_url", "end_image_url"),
    )
    if end_image and not start_image:
        raise SeedanceContractError("end_image требует start_image.")

    has_frames = bool(start_image or end_image)
    has_refs = bool(images or videos or audios)
    if has_frames and has_refs:
        raise SeedanceContractError("First/last frame нельзя смешивать с reference_*.")

    aspect_ratio = str(payload.get("aspect_ratio") or "").strip()
    if aspect_ratio:
        if model == "seedance-2.5" and has_frames:
            if aspect_ratio != "adaptive":
                raise SeedanceContractError(
                    "Seedance 2.5 со start/end frame использует aspect_ratio=adaptive."
                )
        elif task_type == "edit":
            if aspect_ratio != "adaptive":
                raise SeedanceContractError(
                    "Seedance 2.5 edit использует aspect_ratio=adaptive или без поля."
                )
        elif aspect_ratio not in SEEDANCE_FIXED_ASPECT_RATIOS:
            raise SeedanceContractError(
                "Неподдерживаемый aspect_ratio: "
                + ", ".join(SEEDANCE_FIXED_ASPECT_RATIOS)
                + "."
            )
        payload["aspect_ratio"] = aspect_ratio

    if task_type == "edit":
        if model != "seedance-2.5":
            raise SeedanceContractError("Edit доступен только в Seedance 2.5.")
        if not videos:
            raise SeedanceContractError("Seedance 2.5 edit требует видео-референс.")
        if has_frames:
            raise SeedanceContractError("Seedance 2.5 edit нельзя смешивать с frame mode.")

    required = _prompt_reference_requirements(prompt)
    available = {"image": len(images), "video": len(videos), "audio": len(audios)}
    missing = [
        f"@{kind.title()}{required_count}"
        for kind, required_count in required.items()
        if required_count > available[kind]
    ]
    if missing:
        raise SeedanceContractError(
            "Промпт ссылается на отсутствующие референсы: " + ", ".join(missing)
        )

    return payload


def build_seedance_payload(
    *,
    model: str,
    mode: str,
    prompt: str,
    resolution: str,
    duration: int | None = None,
    aspect_ratio: str | None = None,
    image_urls: list[str] | None = None,
    video_urls: list[str] | None = None,
    audio_urls: list[str] | None = None,
    start_image_url: str | None = None,
    end_image_url: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = get_seedance_spec(model)
    mode = str(mode or "").strip().lower()
    if mode not in {"text", "reference", "frame", "edit", "raw"}:
        raise SeedanceContractError("Неизвестный режим Seedance.")
    if mode == "edit" and not spec.supports_edit:
        raise SeedanceContractError("Edit доступен только в Seedance 2.5.")

    payload: dict[str, Any] = dict(extra or {})
    payload["prompt"] = str(prompt or "").strip()
    payload["resolution"] = str(resolution or "").strip()

    if mode == "edit":
        payload.pop("duration", None)
        payload.pop("aspect_ratio", None)
        payload["omni_reference_task_type"] = "edit"
    else:
        if duration is None:
            raise SeedanceContractError("Выберите длительность.")
        payload["duration"] = int(duration)
        if mode == "frame" and model == "seedance-2.5":
            payload["aspect_ratio"] = "adaptive"
        else:
            payload["aspect_ratio"] = str(aspect_ratio or "").strip()

    if mode in {"reference", "edit", "raw"}:
        if image_urls:
            payload["reference_images"] = [{"url": url} for url in image_urls]
        if video_urls:
            payload["reference_videos"] = [{"url": url} for url in video_urls]
        if audio_urls:
            payload["reference_audios"] = [{"url": url} for url in audio_urls]

    if mode == "frame":
        if not start_image_url:
            raise SeedanceContractError("Frame mode требует стартовое изображение.")
        payload["start_image"] = {"url": start_image_url}
        if end_image_url:
            payload["end_image"] = {"url": end_image_url}

    if mode == "reference" and model == "seedance-2.5":
        payload["omni_reference_task_type"] = "reference"

    if mode in {"reference", "edit"}:
        payload["generate_audio"] = True

    return normalize_seedance_request(model, payload)
