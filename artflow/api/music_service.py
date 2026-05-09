from __future__ import annotations

import httpx
from core.config import settings

KIE_URL = "https://api.kie.ai/api/v1/generate"

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


def extract_music_urls(payload: dict) -> list[str]:
    """Извлекает аудио-URL из колбека KIE Suno (clips[].audio_url)."""
    urls: list[str] = []
    data = payload.get("data") or {}
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except Exception:
            data = {}

    clips = data.get("clips") or payload.get("clips") or []
    for clip in clips:
        if isinstance(clip, dict):
            url = clip.get("audio_url") or clip.get("audioUrl")
            if url:
                urls.append(url)

    # fallback: прямые поля
    for key in ("audio_url", "audioUrl"):
        v = data.get(key) or payload.get(key)
        if v and v not in urls:
            urls.append(v)

    return urls


async def create_music_task(
    prompt: str,
    instrumental: bool = False,
    callback_url: str | None = None,
) -> str:
    headers = {
        "Authorization": f"Bearer {settings.KIE_AI_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "prompt": prompt,
        "customMode": False,
        "instrumental": instrumental,
        "model": "V4_5",
        "callBackUrl": callback_url or f"{settings.WEBHOOK_URL}/webhook/kie/music",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(KIE_URL, json=body, headers=headers)

    data = r.json()
    if data.get("code") != 200:
        raise Exception(f"KIE music error: {data}")

    return data["data"]["taskId"]
