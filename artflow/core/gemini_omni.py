from __future__ import annotations

from collections.abc import Iterable
from typing import Any

GEMINI_OMNI_VIDEO_MODEL = "gemini-omni-video"
GEMINI_OMNI_AUDIO_MODEL = "gemini-omni-audio"
GEMINI_OMNI_CHARACTER_MODEL = "gemini-omni-character"

GEMINI_OMNI_DURATIONS = (4, 6, 8, 10)
GEMINI_OMNI_ASPECT_RATIOS = ("16:9", "9:16")
GEMINI_OMNI_PROVIDER_RESOLUTIONS = ("720p", "1080p", "4k")
GEMINI_OMNI_RESOLUTIONS = GEMINI_OMNI_PROVIDER_RESOLUTIONS

GEMINI_OMNI_MAX_IMAGE_SLOTS = 7
GEMINI_OMNI_MAX_AUDIO_IDS = 1
GEMINI_OMNI_MAX_CHARACTER_IDS = 3
GEMINI_OMNI_MAX_VIDEO_CLIPS = 1
GEMINI_OMNI_MAX_VIDEO_TRIM_SECONDS = 10

GEMINI_OMNI_PRICE_TABLE: dict[str, dict[int, int]] = {
    "720p": {4: 90, 6: 120, 8: 150, 10: 180},
    "1080p": {4: 18, 6: 22, 8: 26, 10: 30},
    "4k": {4: 36, 6: 40, 8: 44, 10: 48},
}
GEMINI_OMNI_VIDEO_INPUT_PRICES: dict[str, int] = {
    "720p": 240,
    "1080p": 38,
    "4k": 54,
}

GEMINI_OMNI_AUDIO_VOICES: dict[str, str] = {
    "achernar": "female, soft, high pitch",
    "achird": "male, friendly, mid pitch",
    "algenib": "male, raspy, low pitch",
    "algieba": "male, easygoing, mid-low pitch",
    "alnilam": "male, steady, mid-low pitch",
    "aoede": "female, brisk, mid pitch",
    "autonoe": "female, bright, mid pitch",
    "callirrhoe": "female, easygoing, mid pitch",
    "charon": "male, intellectual, low pitch",
    "despina": "female, smooth, mid pitch",
    "enceladus": "male, breathy, low pitch",
    "erinome": "female, clear, mid pitch",
    "fenrir": "male, lively, younger pitch",
    "gacrux": "female, mature, mid pitch",
    "iapetus": "male, clear, mid-low pitch",
    "kore": "female, capable, mid pitch",
    "laomedeia": "female, cheerful, mid-high pitch",
    "leda": "female, young, mid-high pitch",
    "orus": "male, steady, mid-low pitch",
    "puck": "male, cheerful, mid pitch",
    "pulcherrima": "genderless, forward, mid-high pitch",
    "rasalgethi": "male, intellectual, mid pitch",
    "sadachbia": "male, vivid, low pitch",
    "sadaltager": "male, knowledgeable, mid pitch",
    "schedar": "male, smooth, mid-low pitch",
    "sulafat": "female, warm, mid pitch",
    "umbriel": "male, smooth, low pitch",
    "vindemiatrix": "female, gentle, mid pitch",
    "zephyr": "female, bright, mid-high pitch",
    "zubenelgenubi": "male, casual, mid-low pitch",
}


def normalize_gemini_omni_resolution(value: str | None) -> str:
    if not value:
        return "720p"
    normalized = str(value).strip()
    aliases = {
        "720P": "720p",
        "1080P": "1080p",
        "4K": "4k",
        "2160p": "4k",
        "2160P": "4k",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in GEMINI_OMNI_RESOLUTIONS:
        raise ValueError(
            "Unsupported resolution for Gemini Omni. "
            f"Allowed: {', '.join(GEMINI_OMNI_RESOLUTIONS)}"
        )
    return normalized


def normalize_gemini_omni_duration(value: Any) -> int:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        duration = GEMINI_OMNI_DURATIONS[0]
    if duration not in GEMINI_OMNI_DURATIONS:
        raise ValueError(
            "Unsupported duration for Gemini Omni. "
            f"Allowed: {', '.join(str(item) for item in GEMINI_OMNI_DURATIONS)}"
        )
    return duration


def normalize_gemini_omni_aspect_ratio(value: str | None) -> str:
    aspect_ratio = str(value or "16:9").strip()
    if aspect_ratio not in GEMINI_OMNI_ASPECT_RATIOS:
        raise ValueError(
            "Unsupported aspect_ratio for Gemini Omni. "
            f"Allowed: {', '.join(GEMINI_OMNI_ASPECT_RATIOS)}"
        )
    return aspect_ratio


def normalize_gemini_omni_seed(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        seed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Gemini Omni seed must be an integer") from exc
    if seed < 0 or seed > 2_147_483_647:
        raise ValueError("Gemini Omni seed must be between 0 and 2147483647")
    return seed


def normalize_gemini_omni_ids(
    value: str | Iterable[str] | None,
    *,
    max_items: int,
    field_name: str,
) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        raw_items = value.replace("\n", ",").split(",")
    else:
        raw_items = list(value)
    result = [str(item).strip() for item in raw_items if str(item).strip()]
    if len(result) > max_items:
        raise ValueError(f"{field_name} supports at most {max_items} item(s)")
    return result


def validate_gemini_omni_media_slots(
    *,
    image_count: int = 0,
    video_count: int = 0,
    character_count: int = 0,
) -> None:
    if video_count > GEMINI_OMNI_MAX_VIDEO_CLIPS:
        raise ValueError("Gemini Omni supports at most 1 source video")
    if character_count > GEMINI_OMNI_MAX_CHARACTER_IDS:
        raise ValueError(f"Gemini Omni supports at most {GEMINI_OMNI_MAX_CHARACTER_IDS} character IDs")
    used_slots = image_count + video_count * 2 + character_count
    if used_slots > GEMINI_OMNI_MAX_IMAGE_SLOTS:
        raise ValueError(
            "Gemini Omni media quota exceeded: "
            f"images + videos*2 + character_ids must be <= {GEMINI_OMNI_MAX_IMAGE_SLOTS}"
        )


def gemini_omni_video_credits(
    *,
    duration: int,
    resolution: str | None,
    has_video_input: bool = False,
) -> int:
    normalized_resolution = normalize_gemini_omni_resolution(resolution)
    if has_video_input:
        return GEMINI_OMNI_VIDEO_INPUT_PRICES[normalized_resolution]
    normalized_duration = normalize_gemini_omni_duration(duration)
    return GEMINI_OMNI_PRICE_TABLE[normalized_resolution][normalized_duration]


def build_gemini_omni_audio_payload(
    *,
    audio_id: str,
    name: str,
    voice_description: str | None = None,
    example_dialogue: str | None = None,
) -> dict[str, Any]:
    preset = audio_id.strip()
    if preset not in GEMINI_OMNI_AUDIO_VOICES:
        raise ValueError(f"Unsupported Gemini Omni audio_id: {audio_id}")
    voice_name = name.strip()
    if not voice_name:
        raise ValueError("Gemini Omni audio name is required")
    payload: dict[str, Any] = {"audio_id": preset, "name": voice_name[:210]}
    if voice_description:
        payload["voice_description"] = voice_description.strip()[:20000]
    if example_dialogue:
        payload["example_dialogue"] = example_dialogue.strip()[:120]
    return payload


def build_gemini_omni_character_payload(
    *,
    descriptions: str,
    image_urls: str | Iterable[str],
    audio_ids: str | Iterable[str] | None = None,
    character_name: str | None = None,
) -> dict[str, Any]:
    description = descriptions.strip()
    if not description:
        raise ValueError("Gemini Omni character description is required")
    image_url_values = image_urls if not isinstance(image_urls, str) else [image_urls]
    urls = normalize_gemini_omni_ids(
        image_url_values,
        max_items=1,
        field_name="image_urls",
    )
    if not urls:
        raise ValueError("Gemini Omni character image_urls is required")
    audio = normalize_gemini_omni_ids(audio_ids, max_items=GEMINI_OMNI_MAX_AUDIO_IDS, field_name="audio_ids")
    payload: dict[str, Any] = {
        "descriptions": description,
        "image_urls": urls,
    }
    if audio:
        payload["audio_ids"] = audio
    if character_name:
        payload["character_name"] = character_name.strip()
    return payload
