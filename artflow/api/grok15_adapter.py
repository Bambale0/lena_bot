"""KIE Grok Imagine Video 1.5 Preview adapter.

Grok Imagine Video (legacy provider routes) and Grok Imagine Video 1.5 are
separate products. Only the dedicated 1.5 runtime key is normalized to the
preview provider contract.
"""
from __future__ import annotations

from typing import Any

GROK_15_PROVIDER_MODEL = "grok-imagine-video-1-5-preview"
GROK_15_MODELS = {GROK_15_PROVIDER_MODEL}
GROK_15_ASPECT_RATIOS = {"auto", "1:1", "16:9", "9:16", "3:2", "2:3"}
GROK_15_RESOLUTIONS = {"480p", "720p"}


def _url_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return []


def normalize_grok15_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize only dedicated Grok 1.5 requests to the official contract."""
    model = str(payload.get("model") or "")
    if model not in GROK_15_MODELS:
        return payload

    source = payload.get("input")
    source = dict(source) if isinstance(source, dict) else {}

    image_urls = _url_list(source.get("image_urls"))
    if not image_urls:
        image_urls = _url_list(source.get("image_url"))
    image_urls = image_urls[:7]

    try:
        duration = int(source.get("duration") or 8)
    except (TypeError, ValueError):
        duration = 8
    duration = max(1, min(15, duration))

    aspect_ratio = str(source.get("aspect_ratio") or ("auto" if image_urls else "16:9"))
    if aspect_ratio not in GROK_15_ASPECT_RATIOS:
        aspect_ratio = "auto" if image_urls else "16:9"

    resolution = str(source.get("resolution") or "480p")
    if resolution not in GROK_15_RESOLUTIONS:
        resolution = "480p"

    normalized_input: dict[str, Any] = {
        "prompt": str(source.get("prompt") or "").strip(),
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration": duration,
        "nsfw_checker": bool(source.get("nsfw_checker", False)),
    }
    if image_urls:
        normalized_input["image_urls"] = image_urls

    result = dict(payload)
    result["model"] = GROK_15_PROVIDER_MODEL
    result["input"] = normalized_input
    return result


def install_grok15_adapter(kieai_client_module: Any) -> None:
    """Wrap create_task once so bot, Mini App and API share Grok 1.5 rules."""
    current = kieai_client_module.create_task
    if getattr(current, "__grok15_adapter__", False):
        return

    async def create_task(
        payload: dict[str, Any],
        callback_url: str | None = None,
    ) -> dict[str, Any]:
        return await current(normalize_grok15_payload(payload), callback_url=callback_url)

    create_task.__grok15_adapter__ = True  # type: ignore[attr-defined]
    kieai_client_module.create_task = create_task
