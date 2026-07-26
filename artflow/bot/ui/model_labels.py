from __future__ import annotations


_MODEL_LABELS: dict[str, str] = {
    # Images
    "seedream/5-pro-text-to-image": "🔥 HOT · Seedream 5 Pro",
    "seedream/5-pro-image-to-image": "🔥 HOT · Seedream 5 Pro Edit",
    "seedream/4.5-text-to-image": "🌸 Seedream 4.5",
    "seedream/4.5-edit": "🌸 Seedream 4.5 Edit",
    "grok-imagine/text-to-image": "⚡ Grok Imagine",
    "grok-imagine/image-to-image": "⚡ Grok Imagine Edit",
    "wan/2-7-image": "🌊 WAN 2.7 Image",
    "wan/2-7-image-pro": "🌊 WAN 2.7 Image Pro",
    "google/nano-banana": "🍌 Nano Banana",
    "nano-banana-2": "🍌 Nano Banana 2",
    "nano-banana-2-lite": "⚡ Nano Banana 2 Lite",
    "nano-banana-pro": "🍌 Nano Banana Pro",
    "qwen/text-to-image": "🟣 Qwen Image",
    "qwen/image-to-image": "🟣 Qwen Image Edit",
    "qwen/image-edit": "🟣 Qwen Image Edit Pro",
    "qwen2/text-to-image": "🟣 Qwen 2 Image",
    "qwen2/image-edit": "🟣 Qwen 2 Image Edit",
    "gpt-image-2-text-to-image": "🤖 GPT Image 2",
    "gpt-image-2-image-to-image": "🤖 GPT Image 2 Edit",
    # Video
    "kling-2.6/text-to-video": "🎬 Kling 2.6 Text to Video",
    "kling-2.6/image-to-video": "🎬 Kling 2.6 Image to Video",
    "kling-2.6/motion-control": "🎥 Kling 2.6 Motion Control",
    "kling-3.0/video": "🎬 Kling 3.0",
    "kling-3.0/motion-control": "🎥 Kling 3.0 Motion Control",
    "kling/v3-turbo-text-to-video": "⚡ Kling V3 Turbo Text to Video",
    "kling/v3-turbo-image-to-video": "⚡ Kling V3 Turbo Image to Video",
    "wan/2-7-text-to-video": "🌊 WAN 2.7 Text to Video",
    "wan/2-7-image-to-video": "🌊 WAN 2.7 Image to Video",
    "bytedance/seedance-2": "🌱 Seedance 2",
    "bytedance/seedance-2-fast": "⚡ Seedance 2 Fast",
    "bytedance/seedance-2-mini": "🚀 Seedance 2 Mini",
    "grok-imagine/text-to-video": "🆕 NEW · Grok Imagine Video 1.5",
    "grok-imagine/image-to-video": "🆕 NEW · Grok Imagine Video 1.5 · Image to Video",
    "happyhorse/text-to-video": "🐎 HappyHorse Text to Video",
    "happyhorse/image-to-video": "🐎 HappyHorse Image to Video",
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


def model_display_name(model_key: str, fallback: str | None = None) -> str:
    """Return one consistent user-facing model label across bot screens."""
    key = str(model_key or "").strip()
    if key in _MODEL_LABELS:
        return _MODEL_LABELS[key]
    if fallback and fallback.strip():
        return fallback.strip()
    return key.replace("-", " ").replace("/", " · ").title()
