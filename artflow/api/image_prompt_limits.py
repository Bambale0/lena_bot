"""Provider contract admission for complete, rendered image prompts."""

from __future__ import annotations

from api.image_errors import ImagePromptTooLong

SEEDREAM_5_PROMPT_MAX_CHARS = 5000
_SEEDREAM_5_MODELS = frozenset({"seedream/5-pro-text-to-image", "seedream/5-pro-image-to-image"})


def validate_image_prompt(model: str, prompt: str) -> None:
    key = str(getattr(model, "value", model))
    if key in _SEEDREAM_5_MODELS and len(str(prompt or "").strip()) > SEEDREAM_5_PROMPT_MAX_CHARS:
        raise ImagePromptTooLong(
            f"Промпт для Seedream 5 Pro должен быть не длиннее {SEEDREAM_5_PROMPT_MAX_CHARS} символов. "
            "Сократите текст или выберите другую модель. Поцелуи не списаны."
        )
