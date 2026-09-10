from __future__ import annotations

SEEDANCE_20_PROMPT_MAX_CHARS = 20_000
SEEDANCE_25_PROMPT_MAX_CHARS = 30_000
TELEGRAM_TEXT_MESSAGE_MAX_CHARS = 4096

_SEEDANCE_20_MODELS = frozenset({
    "bytedance/seedance-2",
    "bytedance/seedance-2-fast",
    "bytedance/seedance-2-mini",
})
_SEEDANCE_25_MODELS = frozenset({"bytedance/seedance-2-5"})


def seedance_prompt_max_chars(model: str) -> int | None:
    key = str(model or "").strip()
    if key in _SEEDANCE_20_MODELS:
        return SEEDANCE_20_PROMPT_MAX_CHARS
    if key in _SEEDANCE_25_MODELS:
        return SEEDANCE_25_PROMPT_MAX_CHARS
    return None


def validate_seedance_prompt(model: str, prompt: str) -> str:
    value = str(prompt or "")
    limit = seedance_prompt_max_chars(model)
    if limit is not None and len(value) > limit:
        raise ValueError(f"Prompt for {model} must be at most {limit} characters")
    return value


def append_telegram_seedance_prompt_chunk(
    model: str,
    previous: str,
    chunk: str,
) -> tuple[str, bool]:
    """Rebuild a long prompt split by Telegram into 4096-char messages.

    Returns (combined_prompt, awaiting_more). Chunks are concatenated verbatim so
    an automatic Telegram split does not mutate the original prompt.
    """
    combined = f"{previous or ''}{chunk or ''}"
    validate_seedance_prompt(model, combined)
    return combined, len(chunk or "") >= TELEGRAM_TEXT_MESSAGE_MAX_CHARS
