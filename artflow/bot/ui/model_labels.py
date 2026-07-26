from __future__ import annotations


_MODEL_LABELS: dict[str, str] = {
    # Images: provider text/edit variants intentionally share one public name.
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
    "qwen/text-to-image": "🟣 Qwen Image",
    "qwen/image-to-image": "🟣 Qwen Image",
    "qwen/image-edit": "🟣 Qwen Image",
    "qwen2/text-to-image": "🟣 Qwen 2 Image",
    "qwen2/image-edit": "🟣 Qwen 2 Image",
    "gpt-image-2-text-to-image": "🤖 GPT Image 2",
    "gpt-image-2-image-to-image": "🤖 GPT Image 2",
    # Video: text/image provider routes intentionally share one public name.
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
    "grok-imagine/text-to-video": "🆕 NEW · Grok Imagine Video 1.5",
    "grok-imagine/image-to-video": "🆕 NEW · Grok Imagine Video 1.5",
    "happyhorse/text-to-video": "🐎 HappyHorse Video",
    "happyhorse/image-to-video": "🐎 HappyHorse Video",
    "gemini-omni-video": "✨ Gemini Omni Video",
    "veo3_fast": "🎞 Veo 3 Fast",
    "veo3": "🎞 Veo 3",
    "veo3_lite": "🎞 Veo 3 Lite",
    # Other
    "suno/v5.5": "🎵 Suno 5.5",
    "suno/v4.5": "🎵 Suno 4.5",
    "midjourney-imagine": "🖌 Midjourney Imagine",
    "midjourney-action": "🖌 Midjourney Action",
    "midjourney-blend": "🖼 Midjourney Blend",
    "midjourney-describe": "🔍 Midjourney Describe",
    "midjourney-video": "🎞 Midjourney Video",
}

# One public model family can have several provider endpoints.
_MODEL_VARIANTS: dict[str, dict[str, str]] = {
    "seedream-5-pro": {
        "text": "seedream/5-pro-text-to-image",
        "image": "seedream/5-pro-image-to-image",
    },
    "seedream-4.5": {
        "text": "seedream/4.5-text-to-image",
        "image": "seedream/4.5-edit",
    },
    "grok-image": {
        "text": "grok-imagine/text-to-image",
        "image": "grok-imagine/image-to-image",
    },
    "gpt-image-2": {
        "text": "gpt-image-2-text-to-image",
        "image": "gpt-image-2-image-to-image",
    },
    "grok-video-1.5": {
        "text": "grok-imagine/text-to-video",
        "image": "grok-imagine/image-to-video",
    },
    "kling-v3-turbo": {
        "text": "kling/v3-turbo-text-to-video",
        "image": "kling/v3-turbo-image-to-video",
    },
}

_VARIANT_TO_FAMILY = {
    variant: family
    for family, variants in _MODEL_VARIANTS.items()
    for variant in variants.values()
}


def model_display_name(model_key: str, fallback: str | None = None) -> str:
    """Return one consistent public model name without exposing provider routes."""
    key = str(model_key or "").strip()
    if key in _MODEL_LABELS:
        return _MODEL_LABELS[key]
    if fallback and fallback.strip():
        return fallback.strip()
    return key.replace("-", " ").replace("/", " · ").title()


def model_family_key(model_key: str) -> str:
    """Return a stable public family key for a provider model variant."""
    key = str(model_key or "").strip()
    return _VARIANT_TO_FAMILY.get(key, key)


def resolve_model_variant(model_or_family: str, *, has_image: bool = False) -> str:
    """Choose the provider endpoint automatically from the user's input materials."""
    key = str(model_or_family or "").strip()
    family = _VARIANT_TO_FAMILY.get(key, key)
    variants = _MODEL_VARIANTS.get(family)
    if not variants:
        return key
    route = "image" if has_image and "image" in variants else "text"
    return variants.get(route) or next(iter(variants.values()))
