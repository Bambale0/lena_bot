from __future__ import annotations

from collections.abc import Iterable
from typing import Any


_MODEL_LABELS: dict[str, str] = {
    "seedream/5-pro-text-to-image": "🔥 HOT · Seedream 5 Pro",
    "seedream/5-pro-image-to-image": "🔥 HOT · Seedream 5 Pro",
    "seedream/4.5-text-to-image": "🌸 Seedream 4.5",
    "seedream/4.5-edit": "🌸 Seedream 4.5",
    "grok-imagine/text-to-image": "⚡ Grok Imagine",
    "grok-imagine/image-to-image": "⚡ Grok Imagine",
    "wan/2-7-image": "🌊 WAN 2.7 Image",
    "wan/2-7-image-pro": "🌊 WAN 2.7 Image Pro",
    "google/nano-banana": "🍌 Nano Banana",
    "nano-banana-2": "🍌 Nano Banana 2",
    "nano-banana-2-lite": "⚡ Nano Banana 2 Lite",
    "nano-banana-pro": "🍌 Nano Banana Pro",
    "nano-banana-pro-vip": "🍌 Нана Банано Про ВИП",
    "qwen/text-to-image": "🟣 Qwen Image",
    "qwen/image-to-image": "🟣 Qwen Image",
    "qwen/image-edit": "🟣 Qwen Image Edit Pro",
    "qwen2/text-to-image": "🟣 Qwen 2 Image",
    "qwen2/image-edit": "🟣 Qwen 2 Image",
    "gpt-image-2-text-to-image": "🤖 GPT Image 2",
    "gpt-image-2-image-to-image": "🤖 GPT Image 2",
    "gpt-image-2-vip": "🤖 ГПТ 2 ВИП",
    "kling-2.6/text-to-video": "🎬 Kling 2.6",
    "kling-2.6/image-to-video": "🎬 Kling 2.6",
    "kling-2.6/motion-control": "🎥 Kling 2.6 Motion Control",
    "kling-3.0/video": "🎬 Kling 3.0",
    "kling-3.0/motion-control": "🎥 Kling 3.0 Motion Control",
    "kling/v3-turbo-text-to-video": "⚡ Kling V3 Turbo",
    "kling/v3-turbo-image-to-video": "⚡ Kling V3 Turbo",
    "wan/2-7-text-to-video": "🌊 WAN 2.7 Video",
    "wan/2-7-image-to-video": "🌊 WAN 2.7 Video",
    "bytedance/seedance-2": "🌱 Seedance 2",
    "bytedance/seedance-2-fast": "⚡ Seedance 2 Fast",
    "bytedance/seedance-2-mini": "🚀 Seedance 2 Mini",
    "bytedance/seedance-2-5": "🌱 Seedance 2.5",
    "minimax-h3/text-to-video": "🎞 MiniMax H3",
    "minimax-h3/image-to-video": "🎞 MiniMax H3",
    "minimax-h3/reference-to-video": "🎞 MiniMax H3",
    "grok-imagine/text-to-video": "⚡ Grok Imagine Video",
    "grok-imagine/image-to-video": "⚡ Grok Imagine Video",
    "grok-imagine-video-1-5-preview": "🆕 NEW · Grok Imagine Video 1.5",
    "happyhorse/text-to-video": "🐎 HappyHorse Video",
    "happyhorse/image-to-video": "🐎 HappyHorse Video",
    "gemini-omni-video": "✨ Gemini Omni Video",
    "veo3_fast": "🎞 Veo 3 Fast",
    "veo3": "🎞 Veo 3",
    "veo3_lite": "🎞 Veo 3 Lite",
    "suno/v5.5": "🎵 Suno 5.5",
    "suno/v5.0": "🎵 Suno 5.0",
    "suno/v4.5": "🎵 Suno 4.5",
    "midjourney-imagine": "🖌 Midjourney Imagine",
    "midjourney-action": "🖌 Midjourney Action",
    "midjourney-blend": "🖼 Midjourney Blend",
    "midjourney-describe": "🔍 Midjourney Describe",
    "midjourney-video": "🎞 Midjourney Video",
}

_CANONICAL_MODEL_KEYS: dict[str, str] = {
    "seedream/5-pro-image-to-image": "seedream/5-pro-text-to-image",
    "seedream/4.5-edit": "seedream/4.5-text-to-image",
    "grok-imagine/image-to-image": "grok-imagine/text-to-image",
    "qwen/image-to-image": "qwen/text-to-image",
    "qwen2/image-edit": "qwen2/text-to-image",
    "gpt-image-2-image-to-image": "gpt-image-2-text-to-image",
    "kling-2.6/image-to-video": "kling-2.6/text-to-video",
    "kling/v3-turbo-image-to-video": "kling/v3-turbo-text-to-video",
    "wan/2-7-image-to-video": "wan/2-7-text-to-video",
    "minimax-h3/image-to-video": "minimax-h3/text-to-video",
    "minimax-h3/reference-to-video": "minimax-h3/text-to-video",
    "grok-imagine/image-to-video": "grok-imagine/text-to-video",
    "happyhorse/image-to-video": "happyhorse/text-to-video",
}


def model_display_name(model_key: str, fallback: str | None = None) -> str:
    key = str(model_key or "").strip()
    if key in _MODEL_LABELS:
        return _MODEL_LABELS[key]
    if fallback and fallback.strip():
        return fallback.strip()
    return key.replace("-", " ").replace("/", " · ").title()


def canonical_model_key(model_key: str) -> str:
    key = str(model_key or "").strip()
    return _CANONICAL_MODEL_KEYS.get(key, key)


def is_internal_variant(model_key: str) -> bool:
    key = str(model_key or "").strip()
    return canonical_model_key(key) != key


def apply_model_labels(items: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for item in items:
        key = str(getattr(item, "model_key", None) or (item.get("model_key") if isinstance(item, dict) else ""))
        fallback = item.get("display_name") if isinstance(item, dict) else getattr(item, "display_name", None)
        label = model_display_name(key, fallback)
        if isinstance(item, dict):
            clone = dict(item)
            clone["display_name"] = label
            result.append(clone)
        else:
            try:
                item.display_name = label
            except Exception:
                pass
            result.append(item)
    return result


def public_model_items(items: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for item in apply_model_labels(items):
        key = str(getattr(item, "model_key", None) or (item.get("model_key") if isinstance(item, dict) else ""))
        family = canonical_model_key(key)
        if family in seen:
            continue
        seen.add(family)
        result.append(item)
    return result


def install_miniapp_model_labels(module: Any) -> None:
    module._FRIENDLY_MODEL_NAMES = dict(_MODEL_LABELS)
    module._friendly_model_name = model_display_name


def install_repository_model_labels(repo_module: Any) -> None:
    """Normalize names returned to every UI without changing keys or prices."""
    original = repo_module.get_all_model_costs
    if getattr(original, "__apix_public_labels__", False):
        return

    async def get_all_model_costs(*args: Any, **kwargs: Any):
        rows = await original(*args, **kwargs)
        return apply_model_labels(rows)

    get_all_model_costs.__apix_public_labels__ = True
    repo_module.get_all_model_costs = get_all_model_costs


def all_known_model_keys() -> set[str]:
    return set(_MODEL_LABELS)
