"""Isolated Nano Banana Pro lab adapter; public image routing is unchanged."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from api import neironych_image_adapter

MODEL = "nano-banana-pro"
# Reviewed subset of the partner image contract, shared by UI and validation.
RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "21:9")
QUALITIES = ("1K", "2K", "4K")
MAX_REFERENCES = 4


def build_payload(*, prompt: str, image_urls: list[str] | None = None,
                  aspect_ratio: str = "1:1", quality: str = "2K") -> dict[str, Any]:
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("Введите промпт.")
    if aspect_ratio not in RATIOS:
        raise ValueError("Выберите доступный формат.")
    if quality not in QUALITIES:
        raise ValueError("Выберите качество 1K, 2K или 4K.")
    refs = list(dict.fromkeys(image_urls or []))
    if len(refs) > MAX_REFERENCES:
        raise ValueError(f"Можно добавить до {MAX_REFERENCES} референсов.")
    for ref in refs:
        parsed = urlparse(ref)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Референс должен быть публичной HTTPS-ссылкой.")
    payload: dict[str, Any] = {
        "model": MODEL, "prompt": prompt, "n": 1, "aspect_ratio": aspect_ratio,
        "resolution": quality.lower(), "response_format": "b64_json",
    }
    if refs:
        payload["images"] = [{"image_url": ref} for ref in refs]
    return payload


async def generate_image(*, request_id: str, **params: Any) -> str:
    return await neironych_image_adapter._generate_image(
        build_payload(**params), request_id=request_id, subdir="nano-banana-pro-lab",
    )

