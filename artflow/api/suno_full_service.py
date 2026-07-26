"""Complete typed Suno API client for KIE.

This module covers the current official music generation, audio-processing,
lyrics, persona, cover-art, music-video and custom-voice endpoints. Validation
happens before a credit-consuming request and all local audio is uploaded to KIE
storage through the shared media gateway.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlencode

from api import kieai_client
from api.media_gateway import AUDIO_POLICY, MediaKind, MediaPolicy, prepare_media_url, prepare_media_urls


class SunoModel(StrEnum):
    V3_5 = "V3_5"
    V4 = "V4"
    V4_5 = "V4_5"
    V4_5PLUS = "V4_5PLUS"
    V4_5ALL = "V4_5ALL"
    V5 = "V5"
    V5_5 = "V5_5"


class VocalGender(StrEnum):
    MALE = "m"
    FEMALE = "f"


class PersonaModel(StrEnum):
    STYLE = "style_persona"
    VOICE = "voice_persona"


class SeparationType(StrEnum):
    VOCAL = "separate_vocal"
    STEMS = "split_stem"


@dataclass(frozen=True)
class SunoTask:
    task_id: str
    operation: str


@dataclass(frozen=True)
class SunoTuning:
    negative_tags: str | None = None
    vocal_gender: VocalGender | str | None = None
    style_weight: float | None = None
    weirdness_constraint: float | None = None
    audio_weight: float | None = None
    persona_id: str | None = None
    persona_model: PersonaModel | str | None = None
    voice_id: str | None = None


_MODEL_LIMITS: dict[SunoModel, tuple[int, int, int]] = {
    SunoModel.V3_5: (3000, 200, 80),
    SunoModel.V4: (3000, 200, 80),
    SunoModel.V4_5: (5000, 1000, 100),
    SunoModel.V4_5PLUS: (5000, 1000, 100),
    SunoModel.V4_5ALL: (5000, 1000, 80),
    SunoModel.V5: (5000, 1000, 100),
    SunoModel.V5_5: (5000, 1000, 100),
}
_UPLOAD_AUDIO_POLICY = MediaPolicy(
    kind=MediaKind.AUDIO,
    max_items=2,
    upload_path="audio/apix-suno-inputs",
    allowed_mime_types=AUDIO_POLICY.allowed_mime_types,
    max_duration_seconds=480,
)


def _required(value: str, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required")
    return result


def _limit(value: str | None, field: str, maximum: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    return text


def _model(value: SunoModel | str) -> SunoModel:
    try:
        return value if isinstance(value, SunoModel) else SunoModel(str(value))
    except ValueError as exc:
        raise ValueError(f"Unsupported Suno model: {value}") from exc


def _unit(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    try:
        result = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if result < 0 or result > 1:
        raise ValueError(f"{field} must be between 0 and 1")
    return result


def _gender(value: VocalGender | str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        return VocalGender(str(value)).value
    except ValueError as exc:
        raise ValueError("vocal_gender must be m or f") from exc


def _persona_model(value: PersonaModel | str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        return PersonaModel(str(value)).value
    except ValueError as exc:
        raise ValueError("persona_model must be style_persona or voice_persona") from exc


def _callback(payload: dict[str, Any], callback_url: str | None) -> None:
    if callback_url:
        payload["callBackUrl"] = _required(callback_url, "callback_url")


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean(item)
            for key, item in value.items()
            if item is not None and item != "" and item != []
        }
    if isinstance(value, list):
        return [_clean(item) for item in value if item is not None and item != ""]
    return value


def _tuning_payload(tuning: SunoTuning | None, *, allow_persona: bool = True) -> dict[str, Any]:
    tuning = tuning or SunoTuning()
    persona_id = _required(tuning.persona_id, "persona_id") if tuning.persona_id else None
    if persona_id and not allow_persona:
        raise ValueError("persona_id is not supported for this operation")
    voice_id = _required(tuning.voice_id, "voice_id") if tuning.voice_id else None
    return _clean(
        {
            "negativeTags": str(tuning.negative_tags or "").strip(),
            "vocalGender": _gender(tuning.vocal_gender),
            "styleWeight": _unit(tuning.style_weight, "style_weight"),
            "weirdnessConstraint": _unit(tuning.weirdness_constraint, "weirdness_constraint"),
            "audioWeight": _unit(tuning.audio_weight, "audio_weight"),
            "personaId": persona_id,
            "personaModel": _persona_model(tuning.persona_model) if persona_id else None,
            "voiceId": voice_id,
        }
    )


def _generation_fields(
    *,
    model: SunoModel | str,
    prompt: str,
    custom_mode: bool,
    instrumental: bool,
    style: str | None,
    title: str | None,
    tuning: SunoTuning | None,
    custom_flag_name: str = "customMode",
) -> dict[str, Any]:
    selected = _model(model)
    prompt_limit, style_limit, title_limit = _MODEL_LIMITS[selected]

    if not custom_mode:
        simple_prompt = _limit(prompt, "prompt", 500, required=True)
        if any((str(style or "").strip(), str(title or "").strip(), _clean(_tuning_payload(tuning)))):
            raise ValueError("Simple Suno mode accepts only prompt, instrumental, model and callback")
        return {
            "prompt": simple_prompt,
            custom_flag_name: False,
            "instrumental": bool(instrumental),
            "model": selected.value,
        }

    custom_prompt = _limit(
        prompt,
        "prompt",
        prompt_limit,
        required=not instrumental,
    )
    custom_style = _limit(style, "style", style_limit, required=True)
    custom_title = _limit(title, "title", title_limit, required=True)
    payload: dict[str, Any] = {
        "prompt": custom_prompt,
        custom_flag_name: True,
        "instrumental": bool(instrumental),
        "model": selected.value,
        "style": custom_style,
        "title": custom_title,
    }
    payload.update(_tuning_payload(tuning))
    return _clean(payload)


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await kieai_client.post(path, _clean(payload))
    if not isinstance(response, dict):
        raise RuntimeError(f"Suno {path}: invalid response: {response!r}")
    code = response.get("code")
    if code not in (None, 0, 200, "0", "200"):
        raise RuntimeError(f"Suno {path}: {code} {response.get('msg') or response.get('message')}")
    return response


def _task_id(response: dict[str, Any], operation: str) -> SunoTask:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    task_id = str(data.get("taskId") or data.get("task_id") or response.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError(f"Suno {operation}: response has no taskId: {response!r}")
    return SunoTask(task_id=task_id, operation=operation)


async def _post_task(path: str, operation: str, payload: dict[str, Any]) -> SunoTask:
    return _task_id(await _post(path, payload), operation)


async def _get(path: str, task_id: str) -> dict[str, Any]:
    query = urlencode({"taskId": _required(task_id, "task_id")})
    response = await kieai_client.get(f"{path}?{query}")
    if not isinstance(response, dict):
        raise RuntimeError(f"Suno {path}: invalid response: {response!r}")
    code = response.get("code")
    if code not in (None, 0, 200, "0", "200"):
        raise RuntimeError(f"Suno {path}: {code} {response.get('msg')}")
    return response


async def generate_music(
    prompt: str,
    *,
    model: SunoModel | str = SunoModel.V5,
    custom_mode: bool = False,
    instrumental: bool = False,
    style: str | None = None,
    title: str | None = None,
    tuning: SunoTuning | None = None,
    callback_url: str | None = None,
) -> SunoTask:
    payload = _generation_fields(
        model=model,
        prompt=prompt,
        custom_mode=custom_mode,
        instrumental=instrumental,
        style=style,
        title=title,
        tuning=tuning,
    )
    _callback(payload, callback_url)
    return await _post_task("/api/v1/generate", "generate", payload)


async def extend_music(
    audio_id: str,
    *,
    use_custom_parameters: bool = False,
    prompt: str = "",
    model: SunoModel | str = SunoModel.V5,
    style: str | None = None,
    title: str | None = None,
    continue_at: float | None = None,
    tuning: SunoTuning | None = None,
    callback_url: str | None = None,
) -> SunoTask:
    payload: dict[str, Any] = {
        "audioId": _required(audio_id, "audio_id"),
        "defaultParamFlag": bool(use_custom_parameters),
    }
    if use_custom_parameters:
        selected = _model(model)
        prompt_limit, style_limit, title_limit = _MODEL_LIMITS[selected]
        if continue_at is None or float(continue_at) <= 0:
            raise ValueError("continue_at must be greater than zero")
        payload.update(
            {
                "prompt": _limit(prompt, "prompt", prompt_limit, required=True),
                "model": selected.value,
                "style": _limit(style, "style", style_limit, required=True),
                "title": _limit(title, "title", title_limit, required=True),
                "continueAt": round(float(continue_at), 2),
            }
        )
        payload.update(_tuning_payload(tuning))
    elif any((prompt, style, title, continue_at, _clean(_tuning_payload(tuning)))):
        raise ValueError("Original-parameter extend accepts only audio_id and callback")
    _callback(payload, callback_url)
    return await _post_task("/api/v1/generate/extend", "extend", payload)


async def upload_and_cover(
    upload_url: str,
    prompt: str,
    *,
    model: SunoModel | str = SunoModel.V5,
    custom_mode: bool = False,
    instrumental: bool = False,
    style: str | None = None,
    title: str | None = None,
    tuning: SunoTuning | None = None,
    callback_url: str | None = None,
) -> SunoTask:
    audio = await prepare_media_url(upload_url, policy=_UPLOAD_AUDIO_POLICY)
    payload = _generation_fields(
        model=model,
        prompt=prompt,
        custom_mode=custom_mode,
        instrumental=instrumental,
        style=style,
        title=title,
        tuning=tuning,
    )
    payload["uploadUrl"] = audio
    _callback(payload, callback_url)
    return await _post_task("/api/v1/generate/upload-cover", "upload-cover", payload)


async def upload_and_extend(
    upload_url: str,
    prompt: str,
    *,
    model: SunoModel | str = SunoModel.V5,
    use_custom_parameters: bool = False,
    instrumental: bool = False,
    style: str | None = None,
    title: str | None = None,
    continue_at: float | None = None,
    tuning: SunoTuning | None = None,
    callback_url: str | None = None,
) -> SunoTask:
    audio = await prepare_media_url(upload_url, policy=_UPLOAD_AUDIO_POLICY)
    selected = _model(model)
    payload: dict[str, Any] = {
        "uploadUrl": audio,
        "defaultParamFlag": bool(use_custom_parameters),
        "instrumental": bool(instrumental),
        "model": selected.value,
        "prompt": _limit(prompt, "prompt", 500 if not use_custom_parameters else _MODEL_LIMITS[selected][0], required=True),
    }
    if continue_at is None or float(continue_at) <= 0:
        raise ValueError("continue_at must be greater than zero")
    payload["continueAt"] = round(float(continue_at), 2)
    if use_custom_parameters:
        payload["style"] = _limit(style, "style", _MODEL_LIMITS[selected][1], required=True)
        payload["title"] = _limit(title, "title", _MODEL_LIMITS[selected][2], required=True)
        payload.update(_tuning_payload(tuning))
    elif any((style, title, _clean(_tuning_payload(tuning)))):
        raise ValueError("Default upload-extend does not accept custom style/title/tuning")
    _callback(payload, callback_url)
    return await _post_task("/api/v1/generate/upload-extend", "upload-extend", payload)


async def add_instrumental(
    upload_url: str,
    *,
    title: str,
    tags: str,
    model: SunoModel | str = SunoModel.V4_5PLUS,
    tuning: SunoTuning | None = None,
    callback_url: str | None = None,
) -> SunoTask:
    selected = _model(model)
    payload: dict[str, Any] = {
        "uploadUrl": await prepare_media_url(upload_url, policy=_UPLOAD_AUDIO_POLICY),
        "title": _limit(title, "title", _MODEL_LIMITS[selected][2], required=True),
        "tags": _limit(tags, "tags", _MODEL_LIMITS[selected][1], required=True),
        "model": selected.value,
    }
    payload.update(_tuning_payload(tuning, allow_persona=False))
    _callback(payload, callback_url)
    return await _post_task("/api/v1/generate/add-instrumental", "add-instrumental", payload)


async def add_vocals(
    upload_url: str,
    *,
    prompt: str,
    style: str,
    title: str,
    model: SunoModel | str = SunoModel.V4_5PLUS,
    tuning: SunoTuning | None = None,
    callback_url: str | None = None,
) -> SunoTask:
    selected = _model(model)
    limits = _MODEL_LIMITS[selected]
    payload: dict[str, Any] = {
        "uploadUrl": await prepare_media_url(upload_url, policy=_UPLOAD_AUDIO_POLICY),
        "prompt": _limit(prompt, "prompt", limits[0], required=True),
        "style": _limit(style, "style", limits[1], required=True),
        "title": _limit(title, "title", limits[2], required=True),
        "model": selected.value,
    }
    payload.update(_tuning_payload(tuning, allow_persona=False))
    _callback(payload, callback_url)
    return await _post_task("/api/v1/generate/add-vocals", "add-vocals", payload)


async def replace_section(
    task_id: str,
    audio_id: str,
    *,
    prompt: str,
    tags: str,
    title: str,
    infill_start_s: float,
    infill_end_s: float,
    negative_tags: str | None = None,
    full_lyrics: str | None = None,
    callback_url: str | None = None,
) -> SunoTask:
    start = round(float(infill_start_s), 2)
    end = round(float(infill_end_s), 2)
    if start >= end:
        raise ValueError("infill_start_s must be less than infill_end_s")
    if end - start < 6 or end - start > 60:
        raise ValueError("replacement range must be between 6 and 60 seconds")
    payload = {
        "taskId": _required(task_id, "task_id"),
        "audioId": _required(audio_id, "audio_id"),
        "prompt": _required(prompt, "prompt"),
        "tags": _required(tags, "tags"),
        "title": _limit(title, "title", 100, required=True),
        "negativeTags": str(negative_tags or "").strip(),
        "infillStartS": start,
        "infillEndS": end,
        "fullLyrics": str(full_lyrics or "").strip(),
    }
    _callback(payload, callback_url)
    return await _post_task("/api/v1/generate/replace-section", "replace-section", payload)


async def generate_persona(
    task_id: str,
    audio_id: str,
    *,
    name: str,
    description: str,
    vocal_start: float | None = None,
    vocal_end: float | None = None,
    style: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "taskId": _required(task_id, "task_id"),
        "audioId": _required(audio_id, "audio_id"),
        "name": _limit(name, "name", 120, required=True),
        "description": _limit(description, "description", 1000, required=True),
        "style": str(style or "").strip(),
    }
    if vocal_start is not None or vocal_end is not None:
        if vocal_start is None or vocal_end is None:
            raise ValueError("vocal_start and vocal_end must be provided together")
        start = round(float(vocal_start), 2)
        end = round(float(vocal_end), 2)
        if start < 0 or end <= start:
            raise ValueError("vocal range is invalid")
        payload.update({"vocalStart": start, "vocalEnd": end})
    response = await _post("/api/v1/generate/generate-persona", payload)
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    if not data.get("personaId"):
        raise RuntimeError(f"Suno persona response has no personaId: {response!r}")
    return data


async def generate_mashup(
    upload_urls: list[str],
    prompt: str,
    *,
    model: SunoModel | str = SunoModel.V5,
    custom_mode: bool = False,
    instrumental: bool = False,
    style: str | None = None,
    title: str | None = None,
    tuning: SunoTuning | None = None,
    callback_url: str | None = None,
) -> SunoTask:
    if len(upload_urls) != 2:
        raise ValueError("Suno mashup requires exactly two audio files")
    audio_urls = await prepare_media_urls(upload_urls, policy=_UPLOAD_AUDIO_POLICY)
    payload = _generation_fields(
        model=model,
        prompt=prompt,
        custom_mode=custom_mode,
        instrumental=instrumental,
        style=style,
        title=title,
        tuning=tuning,
    )
    payload["uploadUrlList"] = audio_urls
    _callback(payload, callback_url)
    return await _post_task("/api/v1/generate/mashup", "mashup", payload)


async def generate_lyrics(prompt: str, *, callback_url: str | None = None) -> SunoTask:
    payload = {"prompt": _limit(prompt, "prompt", 3000, required=True)}
    _callback(payload, callback_url)
    return await _post_task("/api/v1/lyrics", "lyrics", payload)


async def get_timestamped_lyrics(task_id: str, audio_id: str) -> dict[str, Any]:
    response = await _post(
        "/api/v1/generate/get-timestamped-lyrics",
        {
            "taskId": _required(task_id, "task_id"),
            "audioId": _required(audio_id, "audio_id"),
        },
    )
    data = response.get("data")
    return data if isinstance(data, dict) else {}


async def boost_style(content: str) -> dict[str, Any]:
    response = await _post("/api/v1/style/generate", {"content": _required(content, "content")})
    data = response.get("data")
    return data if isinstance(data, dict) else {}


async def generate_cover_art(task_id: str, *, callback_url: str | None = None) -> SunoTask:
    payload = {"taskId": _required(task_id, "task_id")}
    _callback(payload, callback_url)
    return await _post_task("/api/v1/suno/cover/generate", "cover-art", payload)


async def convert_to_wav(
    task_id: str,
    audio_id: str,
    *,
    callback_url: str | None = None,
) -> SunoTask:
    payload = {
        "taskId": _required(task_id, "task_id"),
        "audioId": _required(audio_id, "audio_id"),
    }
    _callback(payload, callback_url)
    return await _post_task("/api/v1/wav/generate", "wav", payload)


async def separate_stems(
    task_id: str,
    audio_id: str,
    *,
    separation_type: SeparationType | str = SeparationType.VOCAL,
    callback_url: str | None = None,
) -> SunoTask:
    try:
        mode = separation_type if isinstance(separation_type, SeparationType) else SeparationType(str(separation_type))
    except ValueError as exc:
        raise ValueError("separation_type must be separate_vocal or split_stem") from exc
    payload = {
        "taskId": _required(task_id, "task_id"),
        "audioId": _required(audio_id, "audio_id"),
        "type": mode.value,
    }
    _callback(payload, callback_url)
    return await _post_task("/api/v1/vocal-removal/generate", "stem-separation", payload)


async def generate_midi(
    separation_task_id: str,
    *,
    callback_url: str,
    audio_id: str | None = None,
) -> SunoTask:
    payload = {
        "taskId": _required(separation_task_id, "separation_task_id"),
        "audioId": _required(audio_id, "audio_id") if audio_id else None,
        "callBackUrl": _required(callback_url, "callback_url"),
    }
    return await _post_task("/api/v1/midi/generate", "midi", payload)


async def create_music_video(
    task_id: str,
    audio_id: str,
    *,
    callback_url: str | None = None,
    author: str | None = None,
    domain_name: str | None = None,
) -> SunoTask:
    payload = {
        "taskId": _required(task_id, "task_id"),
        "audioId": _required(audio_id, "audio_id"),
        "author": _limit(author, "author", 120),
        "domainName": _limit(domain_name, "domain_name", 255),
    }
    _callback(payload, callback_url)
    return await _post_task("/api/v1/mp4/generate", "music-video", payload)


async def get_music_task(task_id: str) -> dict[str, Any]:
    return await _get("/api/v1/generate/record-info", task_id)


async def get_lyrics_task(task_id: str) -> dict[str, Any]:
    return await _get("/api/v1/lyrics/record-info", task_id)


async def get_wav_task(task_id: str) -> dict[str, Any]:
    return await _get("/api/v1/wav/record-info", task_id)


async def get_stem_task(task_id: str) -> dict[str, Any]:
    return await _get("/api/v1/vocal-removal/record-info", task_id)


async def get_midi_task(task_id: str) -> dict[str, Any]:
    return await _get("/api/v1/midi/record-info", task_id)


async def get_music_video_task(task_id: str) -> dict[str, Any]:
    return await _get("/api/v1/mp4/record-info", task_id)


async def get_cover_art_task(task_id: str) -> dict[str, Any]:
    return await _get("/api/v1/suno/cover/record-info", task_id)


async def create_voice_validation(
    voice_url: str,
    *,
    vocal_start_s: float,
    vocal_end_s: float,
    language: str = "en",
    callback_url: str | None = None,
) -> SunoTask:
    source = await prepare_media_url(voice_url, policy=_UPLOAD_AUDIO_POLICY)
    start = round(float(vocal_start_s), 2)
    end = round(float(vocal_end_s), 2)
    if start < 0 or end <= start:
        raise ValueError("voice validation segment is invalid")
    payload = {
        "voiceUrl": source,
        "vocalStartS": start,
        "vocalEndS": end,
        "language": _limit(language, "language", 16, required=True),
    }
    _callback(payload, callback_url)
    return await _post_task("/api/v1/voice/validate", "voice-validate", payload)


async def regenerate_voice_validation(task_id: str) -> SunoTask:
    return await _post_task(
        "/api/v1/voice/regenerate",
        "voice-regenerate",
        {"taskId": _required(task_id, "task_id")},
    )


async def create_custom_voice(
    validation_task_id: str,
    verify_url: str,
    *,
    voice_name: str,
    description: str | None = None,
    style: str | None = None,
    singer_skill_level: str | None = None,
    callback_url: str | None = None,
) -> SunoTask:
    verify = await prepare_media_url(verify_url, policy=_UPLOAD_AUDIO_POLICY)
    payload = {
        "taskId": _required(validation_task_id, "validation_task_id"),
        "verifyUrl": verify,
        "voiceName": _limit(voice_name, "voice_name", 128, required=True),
        "description": _limit(description, "description", 1000),
        "style": _limit(style, "style", 256),
        "singerSkillLevel": _limit(singer_skill_level, "singer_skill_level", 32),
    }
    _callback(payload, callback_url)
    return await _post_task("/api/v1/voice/generate", "voice-generate", payload)


async def get_voice_validation(task_id: str) -> dict[str, Any]:
    return await _get("/api/v1/voice/validate-info", task_id)


async def get_custom_voice(task_id: str) -> dict[str, Any]:
    return await _get("/api/v1/voice/record-info", task_id)


async def check_custom_voice(task_id: str) -> bool:
    response = await _post(
        "/api/v1/voice/check-voice",
        {"task_id": _required(task_id, "task_id")},
    )
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    return bool(data.get("isAvailable"))
