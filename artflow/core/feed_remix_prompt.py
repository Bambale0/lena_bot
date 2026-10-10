"""Keep private author text outside models processing a reader's input.

This is an input-isolation boundary, not a prompt-injection detector. Images,
video and other references can contain instructions just like user text can.
Callers must verify and actually submit applicable public source media before
setting ``has_source_media``; a URL supplied by the reader is not proof of it.
"""
from __future__ import annotations


class FeedRemixUnavailable(ValueError):
    """A personalized repeat cannot be grounded in applicable public media."""


def build_feed_remix_prompt(
    source_prompt: str,
    change_request: str = "",
    *,
    has_user_references: bool = False,
    has_source_media: bool = False,
) -> str:
    change = str(change_request or "").strip()
    if not change and not has_user_references:
        return str(source_prompt or "").strip()
    if not has_source_media:
        raise FeedRemixUnavailable(
            "Для изменения этого поста нужна модель, которая поддерживает его исходное фото или видео."
        )

    # Never include source_prompt in this branch, including as a quoted string,
    # hidden system instruction, translated summary, or delimiter-wrapped text.
    prompt = (
        "Edit the supplied public source media. Preserve its visible composition, "
        "style and scene except for the requested changes. "
        "The source is the first image or the source video. "
        "Use additional references for the user's appearance or object."
    )
    return f"{prompt}\n\n{change}" if change else prompt


def original_feed_video_inputs(source) -> dict | None:
    """Return a stored creator input snapshot or None for unknown provenance."""
    import json

    params = getattr(source, "input_params", None)
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (ValueError, TypeError):
            return None
    if not isinstance(params, dict):
        return None
    if "reference_video_url" not in params and "reference_video_urls" not in params:
        return None
    return params


def original_feed_video_references(source) -> list[str] | None:
    """Read *author input* video refs, never the public rendered MP4.

    None is unknown provenance. [] is a verified image/text-to-video source.
    """
    params = original_feed_video_inputs(source)
    if params is None:
        return None
    urls: list[str] = []
    for key in ("reference_video_url", "reference_video_urls"):
        raw = params.get(key)
        candidates = raw if isinstance(raw, list) else [raw]
        urls.extend(value.strip() for value in candidates if isinstance(value, str) and value.strip())

    # Seedance can store additional original video inputs in control tokens.
    for value in params.get("audio_ids") or []:
        if isinstance(value, str) and value.startswith("__apix_seedance25:video_ref="):
            url = value.partition("=")[2].strip()
            if url:
                urls.append(url)
    return list(dict.fromkeys(urls))


FEED_REMIX_CONTEXT_KEY = "feed_remix_context"


def feed_remix_context(source_generation_id: int, safe_prompt: str) -> dict:
    """Call only after the prompt has been rebuilt without protected author text."""
    return {"version": 1, "source_generation_id": source_generation_id, "prompt": safe_prompt}


def trusted_feed_prompt(generation, *, user_id: int, source_generation_id: int) -> str | None:
    """Read server-written provenance bound to this owner, lineage and prompt."""
    import json

    if (
        generation is None
        or getattr(generation, "user_id", None) != user_id
        or getattr(generation, "source_feed_gen_id", None) != source_generation_id
    ):
        return None
    params = getattr(generation, "input_params", None)
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (ValueError, TypeError):
            return None
    context = params.get(FEED_REMIX_CONTEXT_KEY) if isinstance(params, dict) else None
    if not isinstance(context, dict):
        return None
    prompt = context.get("prompt")
    if (
        context.get("version") != 1
        or context.get("source_generation_id") != source_generation_id
        or not isinstance(prompt, str) or not prompt.strip()
        or prompt != getattr(generation, "prompt", None)
    ):
        return None
    return prompt


def legacy_feed_edit_unavailable() -> FeedRemixUnavailable:
    return FeedRemixUnavailable(
        "Не удалось безопасно восстановить изменения старого повтора. "
        "Открой исходный пост и укажи изменения заново; поцелуи не списаны."
    )


def generation_prompt_is_protected(generation) -> bool:
    """Recognize durable feed lineage and hidden-library generation metadata."""
    if getattr(generation, "source_feed_gen_id", None):
        return True
    return generation_has_hidden_prompt_metadata(generation)


def generation_has_hidden_prompt_metadata(generation) -> bool:
    import json

    params = getattr(generation, "input_params", None)
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (ValueError, TypeError):
            return False
    return bool(isinstance(params, dict) and params.get("hidden_prompt"))


def generation_public_error(generation) -> str | None:
    """Provider diagnostics may echo the submitted private prompt."""
    error = getattr(generation, "error_msg", None)
    if error and generation_prompt_is_protected(generation):
        return "Не удалось завершить генерацию. Проверьте статус задачи или обратитесь в поддержку."
    return error


def supports_feed_source_media(caps: dict, source_type: str | None) -> bool:
    """Treat input-routed multimodal models by capability, not legacy mode labels."""
    modes = caps.get("modes", [])
    multimodal = bool(caps.get("auto_route_by_inputs") and "multimodal" in modes)
    if source_type == "image":
        return "image" in modes or (multimodal and int(caps.get("max_refs", 0) or 0) > 0)
    if source_type == "video":
        return bool(caps.get("supports_video_input")) and ("video" in modes or multimodal)
    return False


def feed_video_edit_prompt(safe_prompt: str) -> str:
    """Give an isolated public-video edit the existing provider edit intent.

    This does not establish prompt provenance. Call only after author text was
    excluded or the stored safe prompt was authenticated by trusted_feed_prompt.
    Generic user images retain their ordinary reference role; dedicated identity
    and clothing controls are not inferred from their mere presence.
    """
    prefix = "Edit the video @Video1. Preserve its duration, framing and scene continuity."
    return safe_prompt if safe_prompt.startswith("Edit the video @Video1.") else f"{prefix}\n\n{safe_prompt}"
