"""Keep private author text outside models processing a reader's input.

This is an input-isolation boundary, not a prompt-injection detector. Images,
video and other references can contain instructions just like user text can.
Callers must verify and actually submit applicable public source media before
setting ``has_source_media``; a URL supplied by the reader is not proof of it.
"""
from __future__ import annotations

import hashlib
import json


class FeedRemixUnavailable(ValueError):
    """A personalized repeat cannot be grounded in applicable public media."""


_LEGACY_SOURCE_FIRST_PROMPT = (
    "Edit the supplied public source media. Preserve its visible composition, "
    "style and scene except for the requested changes. "
    "The source is the first image or the source video. "
    "Use additional references for the user's appearance or object."
)
_USER_FIRST_SOURCE_LAST_PROMPT = (
    "Edit the supplied public source media. Preserve its visible composition, "
    "style and scene except for the requested changes. "
    "The source is the final image or the source video. "
    "Use preceding image references for the user's appearance or object."
)
FEED_REMIX_CONTEXT_VERSION = 2
FEED_IMAGE_REMIX_CONTEXT_VERSION = 3
FEED_IMAGE_RECIPE_CONTEXT_VERSION = 4

_IMAGE_RECIPE_SCENE_PREFIX = (
    "Create one new image using the supplied reference image(s) for the subject. "
    "Use the following creator recipe for the scene, clothing, props, pose and lighting.\n\n"
    "Creator scene recipe:\n"
)
_IMAGE_RECIPE_IDENTITY_MARKER = "\n\nReference identity priority: "
_IMAGE_RECIPE_IDENTITY_PRIORITY = (
    _IMAGE_RECIPE_IDENTITY_MARKER + "The supplied image(s) are the sole source of the person's face "
    "and defining appearance, or of the referenced object's defining appearance. "
    "For a person, preserve the reference's face shape, eyes, nose, lips, skin tone, hairline, "
    "hair texture and hair color unless the reader explicitly requests a change. "
    "If a reference is a collage of one person, use its largest "
    "clear frontal face as the identity anchor and other views to confirm that same person; "
    "do not output the collage layout. Do not reproduce the creator's person from the scene recipe. "
    "Reference identity takes priority over conflicting descriptions of appearance or color in the "
    "creator recipe, including a monochrome scene instruction; preserve the other scene details. "
    "The reader's explicit changes take priority over both the reference and creator recipe where requested. "
    "Return one coherent image of the referenced subject, never the original creator's subject."
)

_IMAGE_IDENTITY_ROLES = (
    "All images preceding the final image are the user's identity references. "
    "Use ALL of them as the EXCLUSIVE source of the user's face and identity. "
    "The final image is public scene reference only: use its style, theme, setting and lighting. "
    "Do not copy, retain, average or blend the author's face or identity from the final image. "
    "The user's identity takes priority over resemblance to the source scene."
)
_IMAGE_VARIATION_PROMPT = (
    "Create a new image inspired by the public scene. "
    "Use a new pose, framing and composition unless the user's requested changes specify otherwise. "
    + _IMAGE_IDENTITY_ROLES
)
_IMAGE_SCENE_VARIATION_PROMPT = (
    "Create a new image inspired by the final public scene image: its style, theme, setting and lighting. "
    "Use a new pose, framing and composition unless the user's requested changes specify otherwise. "
    "No separate user identity references are supplied."
)
_IMAGE_EDIT_PROMPT = (
    "Edit the public scene image. Preserve its composition except for the requested changes. "
    + _IMAGE_IDENTITY_ROLES
)
_IMAGE_SCENE_EDIT_PROMPT = (
    "Edit the final public scene image. Preserve its composition and subjects except for the requested changes. "
    "No separate user identity references are supplied."
)
# A feed identity repeat is an edit of the author's *scene*, not a
# freeform variation.  Legacy v3 headers remain registered below so that
# authenticated previous repeats can still be replayed and migrated safely.
_IMAGE_FACE_REPLACEMENT_PROMPT = (
    "Edit the final public scene image, not a new scene. "
    "The final image is public scene reference only for composition, pose, clothing, "
    "background, lighting, props and camera framing; preserve the scene composition "
    "and those non-identity details unless the user's change request explicitly modifies them. "
    "All images preceding the final image are the user's identity references. "
    "Use the first user reference as the EXCLUSIVE source of the user's face and identity, "
    "and any other user references only as additional views of that same person. "
    "If the user reference is a collage or multiple views of one person, use the largest clear "
    "frontal face as the identity anchor and the other views to confirm their appearance; "
    "never output the collage layout. "
    "Edit the main subject: replace the source subject's face and facial identity with the "
    "user's face shape, eyes, eyebrows, nose, lips, jawline, skin tone and distinctive facial features. "
    "Use the user's visible hair color while adapting its styling to the source pose. "
    "Do not copy, retain, average or blend the author's face or identity from the final image. "
    "The user's identity takes priority over resemblance to the source scene. "
    "Return one coherent edited photo, not a split screen, photo grid or the original author."
)

_IMAGE_HEADERS = {
    "variation": _IMAGE_VARIATION_PROMPT,
    "scene_variation": _IMAGE_SCENE_VARIATION_PROMPT,
    "identity_edit": _IMAGE_EDIT_PROMPT,
    "face_replacement": _IMAGE_FACE_REPLACEMENT_PROMPT,
    "scene_first": _LEGACY_SOURCE_FIRST_PROMPT,
    "scene_edit": _IMAGE_SCENE_EDIT_PROMPT,
}


def owned_generation_prompt_is_visible(generation, user_id: int) -> bool:
    """Affirmative recipe permission; malformed metadata never grants access."""
    import json

    if (generation is None or getattr(generation, "user_id", None) != user_id
            or getattr(generation, "source_feed_gen_id", None)):
        return False
    params = getattr(generation, "input_params", None)
    if params is None:
        return True
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (TypeError, ValueError):
            return False
    return isinstance(params, dict) and not params.get("hidden_prompt")


def _feed_source_input_params(source) -> dict | None:
    raw = getattr(source, "input_params", None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    return raw if isinstance(raw, dict) else None


def feed_image_original_recipe_allowed(
    source, *, user_id: int, model_key: str, enabled: bool,
) -> bool:
    """Replay the creator's published image recipe; never copy creator media.

    The original prompt is only used server-side. Derived/legacy-unverifiable
    public items continue through the isolated scene-edit fallback.
    """
    if not enabled or source is None:
        return False
    if (not getattr(source, "is_public_feed", False)
            or getattr(source, "source_feed_gen_id", None)
            or getattr(source, "user_id", None) == user_id):
        return False
    kind = getattr(getattr(source, "gen_type", None), "value", getattr(source, "gen_type", None))
    if kind != "image":
        return False
    # This branch deliberately covers only the installed image request family.
    # Midjourney and video have separate contracts.
    if not isinstance(model_key, str) or not model_key:
        return False
    params = _feed_source_input_params(source)
    if params is None or not isinstance(params.get("reference_images"), list):
        return False
    return bool(str(getattr(source, "prompt", "") or "").strip())


def feed_image_recipe_source_parameters(source) -> dict:
    """Return recipe metadata without exposing the original media references."""
    params = _feed_source_input_params(source) or {}
    original_refs = params.get("reference_images")
    return {
        "required_images": len(original_refs) if isinstance(original_refs, list) else 0,
        "aspect_ratio": params.get("img_ratio") if isinstance(params.get("img_ratio"), str) else None,
        "quality": params.get("img_quality") if isinstance(params.get("img_quality"), str) else None,
        "original_urls": [str(url) for url in original_refs if isinstance(url, str)]
        if isinstance(original_refs, list) else [],
    }


def build_feed_image_recipe_prompt(
    source_prompt: str, identity_instruction: str, change_request: str = "",
    *, previous_instruction: str | None = None,
) -> str:
    """Keep the creator's recipe while assigning facial identity to reader media."""
    prompt = str(source_prompt or "").strip()
    if prompt.startswith(_IMAGE_RECIPE_SCENE_PREFIX) and _IMAGE_RECIPE_IDENTITY_MARKER in prompt:
        prompt = prompt[len(_IMAGE_RECIPE_SCENE_PREFIX):].rsplit(_IMAGE_RECIPE_IDENTITY_MARKER, 1)[0]
    if previous_instruction:
        old_suffix = f"\n\n{previous_instruction.strip()}"
        if prompt.endswith(old_suffix):
            prompt = prompt[:-len(old_suffix)]
    change = str(change_request or "").strip()
    if change:
        prompt = f"{prompt}\n\nИзменения, которые запросил пользователь для повтора: {change}"
    return f"{prompt}\n\n{identity_instruction.strip()}"


def feed_image_recipe_context(
    source_generation_id: int, prompt: str, identity_instruction: str | None = None,
) -> dict:
    """Store an authenticated provenance digest; never duplicate secret text."""
    return {
        "version": FEED_IMAGE_RECIPE_CONTEXT_VERSION,
        "source_generation_id": source_generation_id,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        **({"identity_instruction": identity_instruction} if identity_instruction else {}),
    }


def build_feed_image_prompt(
    change_request: str = "", *, has_user_references: bool, has_source_media: bool,
    fixed_composition: bool = False, scene_first: bool = False,
) -> str:
    """Image-only semantic roles; the provider has no pixel-level identity guarantee."""
    if not has_source_media:
        raise FeedRemixUnavailable("Для повтора нужно доступное исходное фото из ленты.")
    if has_user_references:
        # Restore the recorded pre-October-13 Nexus image edit contract.
        # The author scene is the base (first image); user photos follow.
        # This is independent of the existing video reference semantics.
        header = _LEGACY_SOURCE_FIRST_PROMPT if scene_first else _IMAGE_FACE_REPLACEMENT_PROMPT
    elif fixed_composition:
        header = _IMAGE_SCENE_EDIT_PROMPT
    else:
        header = _IMAGE_SCENE_VARIATION_PROMPT
    change = str(change_request or "").strip()
    return f"{header}\n\n{change}" if change else header


def build_owned_feed_image_prompt(source_prompt: str, change_request: str, *, has_user_references: bool) -> str:
    """Only callers with affirmative server-authenticated recipe permission may use this."""
    prompt = str(source_prompt or "").strip()
    if has_user_references:
        prompt += (
            "\n\nAll supplied images are the user's identity references. "
            "Use ALL of them as the EXCLUSIVE source of face and identity. "
            "The user's identity takes priority over any person described in the scenario."
        )
    change = str(change_request or "").strip()
    return f"{prompt}\n\n{change}" if change else prompt



def order_feed_image_references(
    source_url: str | None,
    requested_refs: list[str],
    *, source_urls: list[str] | None = None, source_first: bool = False,
) -> list[str]:
    """Order verified scene and identity refs for the installed provider contract.

    Nexus personalized photo repeat edits the first image (public scene) using
    additional user references. Video and other routes retain their ordering.
    """
    source = str(source_url or "").strip()
    known_sources = set(source_urls or []) | {source}
    user_refs = [
        str(url).strip()
        for url in requested_refs
        if str(url or "").strip() and str(url).strip() not in known_sources
    ]
    ordered = [source, *user_refs] if source_first else [*user_refs, source]
    return list(dict.fromkeys(url for url in ordered if url))


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
    prompt = _USER_FIRST_SOURCE_LAST_PROMPT
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
    return {
        "version": FEED_REMIX_CONTEXT_VERSION,
        "source_generation_id": source_generation_id,
        "prompt": safe_prompt,
    }


def feed_image_remix_context(
    source_generation_id: int, safe_prompt: str, *, source_image_url: str | None = None,
    scene_generation_id: int | None = None,
) -> dict:
    for family, header in _IMAGE_HEADERS.items():
        if safe_prompt == header or safe_prompt.startswith(header + "\n\n"):
            return {
                "version": FEED_IMAGE_REMIX_CONTEXT_VERSION,
                "source_generation_id": source_generation_id,
                "prompt": safe_prompt,
                "header_family": family,
                **({
                    "source_image_url": source_image_url,
                    "scene_generation_id": scene_generation_id or source_generation_id,
                } if source_image_url else {}),
            }
    return feed_remix_context(source_generation_id, safe_prompt)


def _migrate_trusted_feed_prompt(version: int, prompt: str) -> str:
    """Align authenticated v1 prompts with the v2 user-first reference order."""
    if version != 1:
        return prompt
    if prompt == _LEGACY_SOURCE_FIRST_PROMPT:
        return _USER_FIRST_SOURCE_LAST_PROMPT
    legacy_prefix = f"{_LEGACY_SOURCE_FIRST_PROMPT}\n"
    if prompt.startswith(legacy_prefix):
        return f"{_USER_FIRST_SOURCE_LAST_PROMPT}\n{prompt[len(legacy_prefix):]}"
    return prompt


def _trusted_feed_context(generation, *, user_id: int, source_generation_id: int) -> dict | None:
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
    version = context.get("version")
    if (
        type(version) is not int
        or version not in (
            1, FEED_REMIX_CONTEXT_VERSION, FEED_IMAGE_REMIX_CONTEXT_VERSION,
            FEED_IMAGE_RECIPE_CONTEXT_VERSION,
        )
        or type(context.get("source_generation_id")) is not int
        or context.get("source_generation_id") != source_generation_id
    ):
        return None
    if version == FEED_IMAGE_RECIPE_CONTEXT_VERSION:
        persisted_prompt = getattr(generation, "prompt", None)
        if (not isinstance(persisted_prompt, str) or not persisted_prompt.strip()
                or not isinstance(context.get("prompt_sha256"), str)
                or context["prompt_sha256"] != hashlib.sha256(persisted_prompt.encode("utf-8")).hexdigest()):
            return None
        return context
    if not isinstance(prompt, str) or not prompt.strip() or prompt != getattr(generation, "prompt", None):
        return None
    if version == FEED_IMAGE_REMIX_CONTEXT_VERSION:
        family = context.get("header_family")
        header = _IMAGE_HEADERS.get(family) if isinstance(family, str) else None
        if header is None or not (prompt == header or prompt.startswith(header + "\n\n")):
            return None
        if "source_image_url" in context and (
            not isinstance(context["source_image_url"], str) or not context["source_image_url"].strip()
            or type(context.get("scene_generation_id")) is not int
            or context["scene_generation_id"] <= 0
        ):
            return None
    return context


def trusted_feed_prompt(generation, *, user_id: int, source_generation_id: int) -> str | None:
    """Existing video context behavior; image v3 must not enter the video path."""
    context = _trusted_feed_context(generation, user_id=user_id, source_generation_id=source_generation_id)
    if context is None or context["version"] not in (1, FEED_REMIX_CONTEXT_VERSION):
        return None
    return _migrate_trusted_feed_prompt(context["version"], context["prompt"])


def trusted_feed_image_prompt(
    generation, *, user_id: int, source_generation_id: int,
    has_user_references: bool, fixed_composition: bool = False,
    scene_first: bool = False,
) -> str | None:
    """Replace only a complete known machine header; preserve suffix bytes exactly."""
    context = _trusted_feed_context(generation, user_id=user_id, source_generation_id=source_generation_id)
    if context is None:
        return None
    # A recipe must never be reconstructed through the normal public-scene
    # route, including after the rollout flag is switched off.
    if context["version"] == FEED_IMAGE_RECIPE_CONTEXT_VERSION:
        return None
    prompt = context["prompt"]
    known_headers = (
        [_IMAGE_HEADERS[context["header_family"]]]
        if context["version"] == FEED_IMAGE_REMIX_CONTEXT_VERSION
        else [_LEGACY_SOURCE_FIRST_PROMPT, _USER_FIRST_SOURCE_LAST_PROMPT]
    )
    for header in known_headers:
        if prompt == header or prompt.startswith(header + "\n\n"):
            current_header = build_feed_image_prompt(
                has_user_references=has_user_references, has_source_media=True,
                fixed_composition=fixed_composition, scene_first=scene_first,
            )
            return current_header + prompt[len(header):]
    return prompt


def trusted_feed_image_recipe_prompt(
    generation, *, user_id: int, source_generation_id: int,
) -> str | None:
    """Accept only server-bound creator recipe continuation for its owner."""
    context = _trusted_feed_context(
        generation, user_id=user_id, source_generation_id=source_generation_id,
    )
    if context is None or context["version"] != FEED_IMAGE_RECIPE_CONTEXT_VERSION:
        return None
    return generation.prompt


def trusted_feed_image_recipe_instruction(
    generation, *, user_id: int, source_generation_id: int,
) -> str | None:
    """Return only the admin text bound to an authenticated saved recipe."""
    context = _trusted_feed_context(
        generation, user_id=user_id, source_generation_id=source_generation_id,
    )
    if context is None or context["version"] != FEED_IMAGE_RECIPE_CONTEXT_VERSION:
        return None
    instruction = context.get("identity_instruction")
    prompt = getattr(generation, "prompt", None)
    if (not isinstance(instruction, str) or not instruction.strip()
            or not isinstance(prompt, str) or not prompt.endswith(f"\n\n{instruction}")):
        return None
    return instruction


def trusted_feed_image_scene(
    generation, *, user_id: int, source_generation_id: int,
) -> tuple[int, str] | None:
    """Read scene provenance; callers must authenticate and validate that scene row."""
    context = _trusted_feed_context(generation, user_id=user_id, source_generation_id=source_generation_id)
    if context is None or context["version"] != FEED_IMAGE_REMIX_CONTEXT_VERSION or "source_image_url" not in context:
        return None
    return context["scene_generation_id"], context["source_image_url"]


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
