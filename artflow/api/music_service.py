
import httpx
from core.config import settings

KIE_URL = "https://api.kie.ai/api/v1/generate"

async def create_music_task(prompt: str, instrumental: bool = False):
    headers = {
        "Authorization": f"Bearer {settings.KIE_AI_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
        "customMode": False,
        "instrumental": instrumental,
        "model": "V4_5",
        "callBackUrl": f"{settings.WEBHOOK_URL}/webhook/kie/music"
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(KIE_URL, json=payload, headers=headers)

    data = r.json()

    if data.get("code") != 200:
        raise Exception(f"KIE music error: {data}")

    return data["data"]["taskId"]
