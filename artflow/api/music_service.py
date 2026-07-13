from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from api import kieai_client
from api.public_files import is_audio_content_type
from core.config import settings

KIE_URL = "https://api.kie.ai/api/v1/generate"

SUNO_VOICE_STATUS_VALIDATING = "validating"
SUNO_VOICE_STATUS_AWAITING_VERIFICATION = "awaiting_verification"
SUNO_VOICE_STATUS_GENERATING = "generating"
SUNO_VOICE_STATUS_READY = "ready"
SUNO_VOICE_STATUS_FAILED = "failed"

SUNO_VOICE_PROCESSING_STATUSES = {
    "wait_processing",
    "processing_validate",
    "wait_validating",
    "pending",
    "processing",
}
SUNO_VOICE_FAILED_STATUSES = {"processing_validate_fail", "fail", "failed", "error"}
SUNO_VOICE_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}

MUSIC_MODEL_ALIASES = {
    "suno/v4.5": "V4_5",
    "suno/v5.0": "V5",
    "suno/v5.5": "V5_5",
}


def normalize_music_model(model_key: str | None) -> str:
    key = str(model_key or "").strip().lower()
    return MUSIC_MODEL_ALIASES.get(key, MUSIC_MODEL_ALIASES["suno/v4.5"])

# task_id → tg_id (bot flow)
_pending: dict[str, int] = {}
# task_id → gen_id (miniapp flow)
_pending_gen: dict[str, int] = {}


def register_task(task_id: str, tg_id: int) -> None:
    _pending[task_id] = tg_id


def pop_task(task_id: str) -> int | None:
    return _pending.pop(task_id, None)


def register_miniapp_task(task_id: str, gen_id: int) -> None:
    _pending_gen[task_id] = gen_id


def pop_miniapp_task(task_id: str) -> int | None:
    return _pending_gen.pop(task_id, None)


def default_music_callback_url() -> str:
    url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/kie/music"
    secret = (settings.KIE_WEBHOOK_SECRET or "").strip()
    if secret:
        return f"{url}?{urlencode({'secret': secret})}"
    return url


def default_suno_voice_callback_url(stage: str) -> str:
    url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/kie/suno-voice"
    params = {"stage": stage}
    secret = (settings.KIE_WEBHOOK_SECRET or "").strip()
    if secret:
        params["secret"] = secret
    return f"{url}?{urlencode(params)}"


def _is_probably_audio(data: bytes, content_type: str | None = None, filename: str | None = None) -> bool:
    if is_audio_content_type(content_type):
        return True
    suffix = Path(filename or "").suffix.lower()
    if suffix in SUNO_VOICE_AUDIO_EXTENSIONS:
        return True
    return (
        data.startswith(b"ID3")
        or data.startswith(b"\xff\xfb")
        or data.startswith(b"\xff\xf3")
        or data.startswith(b"\xff\xf2")
        or (len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE")
        or (len(data) > 8 and data[4:8] == b"ftyp")
        or data.startswith(b"fLaC")
        or data.startswith(b"OggS")
    )


def is_supported_suno_voice_audio(
    data: bytes,
    content_type: str | None = None,
    filename: str | None = None,
) -> bool:
    return bool(data) and _is_probably_audio(data, content_type, filename)


def _audio_upload_name(data: bytes, filename: str | None, content_type: str | None) -> str:
    original = Path(filename or "voice.mp3")
    suffix = original.suffix.lower()
    if suffix not in SUNO_VOICE_AUDIO_EXTENSIONS:
        guessed = mimetypes.guess_extension(content_type or "") or ".mp3"
        suffix = guessed if guessed in SUNO_VOICE_AUDIO_EXTENSIONS else ".mp3"
    stem = original.stem.strip() or "voice"
    return f"{stem[:48]}{suffix}"


async def upload_suno_voice_audio(
    data: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    if not is_supported_suno_voice_audio(data, content_type, filename):
        raise ValueError("Unsupported audio file")
    upload_name = _audio_upload_name(data, filename, content_type)
    media_type = content_type or mimetypes.guess_type(upload_name)[0] or "audio/mpeg"
    return await kieai_client.upload_file_stream(
        data,
        filename=upload_name,
        content_type=media_type,
        upload_path="audio/apix-voices",
    )


def _kie_success(response: dict[str, Any]) -> bool:
    code = response.get("code")
    return code in {None, 0, 200}


def _response_data(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    return data if isinstance(data, dict) else {}


def extract_suno_voice_task_id(payload: dict[str, Any]) -> str | None:
    data = _response_data(payload)
    for source in (data, payload):
        for key in ("taskId", "task_id", "id"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def extract_suno_voice_status(payload: dict[str, Any]) -> str:
    data = _response_data(payload)
    value = data.get("status") or payload.get("status") or data.get("state") or payload.get("state") or ""
    return str(value or "").strip()


def extract_suno_voice_error(payload: dict[str, Any]) -> str:
    data = _response_data(payload)
    value = (
        data.get("errorMessage")
        or payload.get("errorMessage")
        or data.get("error")
        or payload.get("error")
        or data.get("msg")
        or payload.get("msg")
        or ""
    )
    return str(value or "").strip()


def extract_suno_validate_phrase(payload: dict[str, Any]) -> str | None:
    data = _response_data(payload)
    for key in ("validateInfo", "validate_info", "validationPhrase", "verificationPhrase"):
        value = data.get(key) or payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_suno_provider_voice_id(payload: dict[str, Any]) -> str | None:
    data = _response_data(payload)
    for key in ("voiceId", "voice_id", "id"):
        value = data.get(key) or payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _provider_task_id_or_raise(response: dict[str, Any], context: str) -> str:
    if not _kie_success(response):
        raise RuntimeError(f"KIE Suno Voice {context} error: {response}")
    task_id = extract_suno_voice_task_id(response)
    if not task_id:
        raise RuntimeError(f"KIE Suno Voice {context} response missing taskId: {response}")
    return task_id


async def create_suno_voice_validation_task(
    *,
    voice_url: str,
    vocal_start_s: float,
    vocal_end_s: float,
    language: str = "en",
    callback_url: str | None = None,
) -> str:
    payload = {
        "voiceUrl": voice_url,
        "vocalStartS": round(float(vocal_start_s), 2),
        "vocalEndS": round(float(vocal_end_s), 2),
        "language": language,
        "callBackUrl": callback_url or default_suno_voice_callback_url("validate"),
    }
    return _provider_task_id_or_raise(
        await kieai_client.create_suno_voice_validation(payload),
        "validation",
    )


async def get_suno_voice_validation_info(task_id: str) -> dict[str, Any]:
    return await kieai_client.get_suno_voice_validation(task_id)


async def create_suno_voice_generation_task(
    *,
    validate_task_id: str,
    verify_url: str,
    voice_name: str,
    description: str | None = None,
    style: str | None = None,
    singer_skill_level: str | None = None,
    callback_url: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "taskId": validate_task_id,
        "verifyUrl": verify_url,
        "voiceName": voice_name[:128],
        "callBackUrl": callback_url or default_suno_voice_callback_url("generate"),
    }
    if description:
        payload["description"] = description[:1000]
    if style:
        payload["style"] = style[:256]
    if singer_skill_level:
        payload["singerSkillLevel"] = singer_skill_level[:32]
    return _provider_task_id_or_raise(await kieai_client.create_suno_voice(payload), "generation")


async def get_suno_voice_record_info(task_id: str) -> dict[str, Any]:
    return await kieai_client.get_suno_voice_record(task_id)


async def check_suno_voice_available(task_id: str) -> bool:
    response = await kieai_client.check_suno_voice({"task_id": task_id})
    if not _kie_success(response):
        return False
    data = _response_data(response)
    return bool(data.get("isAvailable") or data.get("available"))


def extract_music_urls(payload: dict) -> list[str]:
    """Extract one best audio URL per Suno/KIE track."""
    urls: list[str] = []

    def is_url(value: object) -> bool:
        return isinstance(value, str) and (
            value.startswith("http://") or value.startswith("https://")
        )

    def pick_track_url(track: dict) -> str | None:
        # One URL per generated track. Prefer downloadable mp3.
        for key in (
            "audio_url",
            "audioUrl",
            "source_audio_url",
            "sourceAudioUrl",
            "source_stream_audio_url",
            "sourceStreamAudioUrl",
            "stream_audio_url",
            "streamAudioUrl",
        ):
            value = track.get(key)
            if is_url(value):
                return value
        return None

    data = payload.get("data") if isinstance(payload, dict) else None

    # New KIE callback shape:
    # {"data": {"callbackType": "complete", "data": [{track}, ...]}}
    if isinstance(data, dict):
        tracks = data.get("data")
        if isinstance(tracks, list):
            for track in tracks:
                if isinstance(track, dict):
                    url = pick_track_url(track)
                    if url:
                        urls.append(url)

        # Record-info / older shape:
        # {"data": {"response": {"sunoData": [{track}, ...]}}}
        response = data.get("response")
        if isinstance(response, dict):
            suno_data = response.get("sunoData")
            if isinstance(suno_data, list):
                for track in suno_data:
                    if isinstance(track, dict):
                        url = pick_track_url(track)
                        if url:
                            urls.append(url)

        clips = data.get("clips")
        if isinstance(clips, list):
            for track in clips:
                if isinstance(track, dict):
                    url = pick_track_url(track)
                    if url:
                        urls.append(url)

        # Direct single-track fallback
        direct = pick_track_url(data)
        if direct:
            urls.append(direct)

    # Root-level fallbacks
    clips = payload.get("clips") if isinstance(payload, dict) else None
    if isinstance(clips, list):
        for track in clips:
            if isinstance(track, dict):
                url = pick_track_url(track)
                if url:
                    urls.append(url)

    direct = pick_track_url(payload)
    if direct:
        urls.append(direct)

    # Deduplicate while preserving order.
    seen = set()
    result = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def build_music_generation_payload(
    prompt: str,
    instrumental: bool = False,
    callback_url: str | None = None,
    model_key: str | None = None,
    *,
    style: str | None = None,
    title: str | None = None,
    voice_id: str | None = None,
) -> dict[str, Any]:
    clean_style = (style or "").strip()
    clean_title = (title or "").strip()
    clean_voice_id = (voice_id or "").strip()
    custom_mode = bool(clean_voice_id or clean_style or clean_title)

    if custom_mode:
        if instrumental and clean_voice_id:
            raise ValueError("Custom voice can only be used for vocal music")
        if not clean_style:
            raise ValueError("Music style is required in custom mode")
        if not clean_title:
            raise ValueError("Track title is required in custom mode")
    elif len(prompt) > 500:
        raise ValueError("Non-custom Suno prompts are limited to 500 characters")

    body = {
        "prompt": prompt,
        "customMode": custom_mode,
        "instrumental": instrumental,
        "model": normalize_music_model(model_key),
        "callBackUrl": callback_url or default_music_callback_url(),
    }
    if custom_mode:
        body["style"] = clean_style[:1000]
        body["title"] = clean_title[:100]
    if clean_voice_id:
        body["voiceId"] = clean_voice_id
    return body


async def create_music_task(
    prompt: str,
    instrumental: bool = False,
    callback_url: str | None = None,
    model_key: str | None = None,
    *,
    style: str | None = None,
    title: str | None = None,
    voice_id: str | None = None,
) -> str:
    headers = {
        "Authorization": f"Bearer {settings.KIE_AI_KEY}",
        "Content-Type": "application/json",
    }
    body = build_music_generation_payload(
        prompt,
        instrumental,
        callback_url,
        model_key,
        style=style,
        title=title,
        voice_id=voice_id,
    )

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(KIE_URL, json=body, headers=headers)

    data = r.json()
    if data.get("code") != 200:
        raise Exception(f"KIE music error: {data}")

    return data["data"]["taskId"]
