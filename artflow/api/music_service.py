from __future__ import annotations

import httpx
from urllib.parse import urlencode

from core.config import settings

KIE_URL = "https://api.kie.ai/api/v1/generate"

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


async def create_music_task(
    prompt: str,
    instrumental: bool = False,
    callback_url: str | None = None,
    model_key: str | None = None,
) -> str:
    headers = {
        "Authorization": f"Bearer {settings.KIE_AI_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "prompt": prompt,
        "customMode": False,
        "instrumental": instrumental,
        "model": normalize_music_model(model_key),
        "callBackUrl": callback_url or default_music_callback_url(),
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(KIE_URL, json=body, headers=headers)

    data = r.json()
    if data.get("code") != 200:
        raise Exception(f"KIE music error: {data}")

    return data["data"]["taskId"]
