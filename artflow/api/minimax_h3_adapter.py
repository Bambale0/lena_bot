"""MiniMax H3 family integration.

APIX exposes ONE public MiniMax H3 model while keeping KIE's three transport
routes internal. The provider route is selected from the media that is actually
present, matching the public model-family pattern already used by Kling/WAN/Grok:

* no media -> minimax-h3/text-to-video
* one/two images only -> minimax-h3/image-to-video (first / first+last frame)
* video/audio refs or >2 images -> minimax-h3/reference-to-video

The capability surface follows the official MiniMax H3 V2 specification:
4..15 seconds, 768P/2K, native audio, six concrete aspect ratios plus adaptive
for reference mode, <=9 reference images, <=3 videos and <=3 audio clips, with
<=12 mixed reference files total.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

PUBLIC_MODEL = "minimax-h3/text-to-video"
T2V_MODEL = PUBLIC_MODEL
I2V_MODEL = "minimax-h3/image-to-video"
REFERENCE_MODEL = "minimax-h3/reference-to-video"
MODEL_KEYS = (T2V_MODEL, I2V_MODEL, REFERENCE_MODEL)
INTERNAL_MODELS = (I2V_MODEL, REFERENCE_MODEL)

PUBLIC_DISPLAY_NAME = "🎞 MiniMax H3"
DISPLAY_NAMES = {key: PUBLIC_DISPLAY_NAME for key in MODEL_KEYS}

DURATIONS = list(range(4, 16))
T2V_ASPECT_RATIOS = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
REFERENCE_ASPECT_RATIOS = ["adaptive", *T2V_ASPECT_RATIOS]
RESOLUTIONS = ["2K", "768P"]
MAX_REFERENCE_IMAGES = 9
MAX_REFERENCE_VIDEOS = 3
MAX_REFERENCE_AUDIOS = 3
MAX_REFERENCE_FILES = 12
MIN_REFERENCE_MEDIA_SECONDS = 2
MAX_REFERENCE_MEDIA_SECONDS = 15
MAX_REFERENCE_VIDEO_SECONDS = MAX_REFERENCE_MEDIA_SECONDS  # compatibility alias
MAX_REFERENCE_TOTAL_SECONDS = 15

logger = logging.getLogger(__name__)

# One user-facing capability contract. `mode` is a collection hint only; actual
# provider routing is inferred again on the backend from supplied media.
PUBLIC_CAPS: dict[str, Any] = {
    "modes": ["text", "image", "video"],
    "duration_options": DURATIONS,
    "aspect_ratios": REFERENCE_ASPECT_RATIOS,
    "aspect_ratio_modes": ["text", "image", "video"],
    "has_resolution": True,
    "resolutions": RESOLUTIONS,
    "resolution_labels": {"768P": "768P", "2K": "2K · максимум"},
    "max_refs": MAX_REFERENCE_IMAGES,
    "supports_video_input": True,
    "max_reference_videos": MAX_REFERENCE_VIDEOS,
    "max_reference_audios": MAX_REFERENCE_AUDIOS,
    "max_reference_files": MAX_REFERENCE_FILES,
    "native_audio": True,
    "auto_route_by_inputs": True,
    "billing_mode": "per_second",
}

# Internal routes are intentionally not presented as separate products.
VIDEO_CAPS: dict[str, dict[str, Any]] = {
    T2V_MODEL: dict(PUBLIC_CAPS),
    I2V_MODEL: {
        "modes": ["image"],
        "duration_options": DURATIONS,
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": RESOLUTIONS,
        "billing_mode": "per_second",
    },
    REFERENCE_MODEL: {
        "modes": ["image", "video"],
        "duration_options": DURATIONS,
        "aspect_ratios": REFERENCE_ASPECT_RATIOS,
        "has_resolution": True,
        "resolutions": RESOLUTIONS,
        "max_refs": MAX_REFERENCE_IMAGES,
        "supports_video_input": True,
        "max_reference_videos": MAX_REFERENCE_VIDEOS,
        "max_reference_audios": MAX_REFERENCE_AUDIOS,
        "billing_mode": "per_second",
    },
}


def _install_enum_value(enum_cls: Any, name: str, value: str) -> Any:
    if value in getattr(enum_cls, "_value2member_map_", {}):
        return enum_cls(value)
    member = str.__new__(enum_cls, value)
    member._name_ = name
    member._value_ = value
    enum_cls._member_names_.append(name)
    enum_cls._member_map_[name] = member
    enum_cls._value2member_map_[value] = member
    return member


def _urls(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))


def _duration(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 6
    return max(4, min(15, parsed))


def _resolution(value: Any) -> str:
    raw = str(value or "2K").upper()
    aliases = {"768P": "768P", "768": "768P", "2K": "2K", "1440P": "2K"}
    return aliases.get(raw, "2K")


def _choice(value: Any, allowed: list[str], default: str) -> str:
    selected = str(value or default)
    return selected if selected in allowed else default


def route_for_inputs(*, images: list[str], videos: list[str], audios: list[str]) -> str:
    """Choose the provider route from actual input media, never a UI mode button."""
    if videos or audios or len(images) > 2:
        return REFERENCE_MODEL
    if images:
        return I2V_MODEL
    return T2V_MODEL


def validate_reference_set(*, images: list[str], videos: list[str], audios: list[str]) -> None:
    if len(images) > MAX_REFERENCE_IMAGES:
        raise ValueError(f"MiniMax H3 supports at most {MAX_REFERENCE_IMAGES} reference images")
    if len(videos) > MAX_REFERENCE_VIDEOS:
        raise ValueError(f"MiniMax H3 supports at most {MAX_REFERENCE_VIDEOS} reference videos")
    if len(audios) > MAX_REFERENCE_AUDIOS:
        raise ValueError(f"MiniMax H3 supports at most {MAX_REFERENCE_AUDIOS} reference audio clips")
    if len(images) + len(videos) + len(audios) > MAX_REFERENCE_FILES:
        raise ValueError(f"MiniMax H3 supports at most {MAX_REFERENCE_FILES} mixed reference files")
    if audios and not (images or videos):
        raise ValueError("MiniMax H3 audio reference must be accompanied by an image or video reference")


def _t2v_input(*, prompt: str, duration: Any, aspect_ratio: Any, resolution: Any) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "duration": _duration(duration),
        "aspect_ratio": _choice(aspect_ratio, T2V_ASPECT_RATIOS, "16:9"),
        "resolution": _resolution(resolution),
    }


def _i2v_input(*, prompt: str, duration: Any, resolution: Any, images: list[str]) -> dict[str, Any]:
    if not images:
        raise ValueError("MiniMax H3 Image-to-Video requires a first frame")
    if len(images) > 2:
        raise ValueError("MiniMax H3 first/last-frame mode accepts at most two images")
    payload: dict[str, Any] = {
        "prompt": prompt,
        "duration": _duration(duration),
        "resolution": _resolution(resolution),
        "first_frame_url": images[0],
    }
    if len(images) == 2:
        payload["last_frame_url"] = images[1]
    return payload


def _reference_input(
    *,
    prompt: str,
    duration: Any,
    aspect_ratio: Any,
    resolution: Any,
    images: list[str],
    videos: list[str],
    audios: list[str],
) -> dict[str, Any]:
    validate_reference_set(images=images, videos=videos, audios=audios)
    if not (images or videos):
        raise ValueError("MiniMax H3 Reference-to-Video requires an image or video reference")
    payload: dict[str, Any] = {
        "prompt": prompt,
        "duration": _duration(duration),
        "aspect_ratio": _choice(aspect_ratio, REFERENCE_ASPECT_RATIOS, "adaptive"),
        "resolution": _resolution(resolution),
    }
    if images:
        payload["reference_image_urls"] = images
    if videos:
        payload["reference_video_urls"] = videos
    if audios:
        payload["reference_audio_urls"] = audios
    return payload


def _model_cost(model_key: str, *, resolution: str | None = None):
    from api.minimax_h3_pricing import credits_per_second
    from db.models import GenerationType

    return SimpleNamespace(
        model_key=model_key,
        display_name=PUBLIC_DISPLAY_NAME,
        gen_type=GenerationType.video,
        credits=float(credits_per_second(model_key, resolution=resolution)),
        is_active=True,
    )


async def _prepare_audio_reference(video_service: Any, url: str) -> str:
    local = await video_service._upload_local_media(url, upload_path="audio/minimax-h3-refs")
    return str(local or url)


def _install_generate_wrapper(video_service: Any) -> None:
    if getattr(video_service, "_minimax_h3_generate_wrapper_installed", False):
        return
    original_generate_video = video_service.generate_video

    async def generate_video(model, prompt: str, *args, **kwargs):
        selected = model if isinstance(model, video_service.VideoModel) else video_service.VideoModel(str(model))
        if selected.value not in MODEL_KEYS:
            return await original_generate_video(model, prompt, *args, **kwargs)

        image_url = kwargs.get("image_url")
        if args:
            image_url = args[0]
        images = _dedupe(await video_service._prepare_video_reference_urls(image_url))

        raw_videos = _urls(kwargs.get("reference_video_url"))
        # Compatibility transport for existing Mini App/web payloads. These are
        # URL values only for H3; Gemini Omni ID semantics never reach this path.
        raw_videos.extend(_urls(kwargs.get("character_ids")))
        videos: list[str] = []
        for raw_url in _dedupe(raw_videos)[:MAX_REFERENCE_VIDEOS]:
            prepared = await video_service._prepare_reference_video_url(raw_url)
            if prepared and prepared not in videos:
                videos.append(prepared)

        audios: list[str] = []
        for raw_url in _dedupe(_urls(kwargs.get("audio_ids")))[:MAX_REFERENCE_AUDIOS]:
            prepared = await _prepare_audio_reference(video_service, raw_url)
            if prepared and prepared not in audios:
                audios.append(prepared)

        validate_reference_set(images=images, videos=videos, audios=audios)
        provider_model = route_for_inputs(images=images, videos=videos, audios=audios)
        duration = kwargs.get("duration", 6)
        aspect_ratio = kwargs.get("aspect_ratio")
        resolution = kwargs.get("resolution")

        if provider_model == T2V_MODEL:
            input_payload = _t2v_input(
                prompt=prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
            )
        elif provider_model == I2V_MODEL:
            input_payload = _i2v_input(
                prompt=prompt,
                duration=duration,
                resolution=resolution,
                images=images,
            )
        else:
            input_payload = _reference_input(
                prompt=prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                images=images,
                videos=videos,
                audios=audios,
            )

        response = await video_service.kieai_client.create_task(
            {"model": provider_model, "input": input_payload},
            callback_url=kwargs.get("callback_url"),
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"KIE.AI MiniMax H3 returned invalid createTask response: {response!r}")
        if response.get("code") not in (None, 200, "200"):
            raise RuntimeError(
                f"KIE.AI MiniMax H3 createTask failed: {response.get('code')} {response.get('msg')}"
            )
        data = response.get("data") or {}
        task_id = str(data.get("taskId") if isinstance(data, dict) else "").strip()
        if not task_id:
            task_id = str(response.get("taskId") or "").strip()
        if not task_id:
            raise RuntimeError(f"KIE.AI MiniMax H3 returned empty taskId: {response!r}")

        logger.info(
            "KIE.AI MiniMax H3 auto-route public=%s provider=%s images=%d videos=%d audios=%d quality=%s task=%s",
            selected.value,
            provider_model,
            len(images),
            len(videos),
            len(audios),
            _resolution(resolution),
            task_id,
        )
        return video_service.VideoResult(task_id=task_id, provider="kieai", uses_webhook=bool(kwargs.get("callback_url")))

    video_service.generate_video = generate_video
    video_service._minimax_h3_generate_wrapper_installed = True


def _install_miniapp_normalizer(routes: Any) -> None:
    if getattr(routes, "_minimax_h3_normalizer_installed", False):
        return
    original = routes._normalize_video_request

    def normalize_video_request(
        *,
        model_key: str,
        mode: str,
        duration: int,
        aspect_ratio: str | None,
        resolution: str | None,
        image_url: str | None,
        reference_urls: list[str] | None,
        video_url: str | None = None,
        video_start: float | None = None,
        video_end: float | None = None,
        audio_ids: list[str] | None = None,
        character_ids: list[str] | None = None,
        seed: int | None = None,
        grok_mode: str | None = None,
    ) -> dict[str, Any]:
        if model_key not in MODEL_KEYS:
            return original(
                model_key=model_key,
                mode=mode,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                image_url=image_url,
                reference_urls=reference_urls,
                video_url=video_url,
                video_start=video_start,
                video_end=video_end,
                audio_ids=audio_ids,
                character_ids=character_ids,
                seed=seed,
                grok_mode=grok_mode,
            )

        images = _dedupe(routes._normalize_public_urls(image_url, *(reference_urls or []))) if (image_url or reference_urls) else []
        videos = _dedupe(routes._normalize_public_urls(video_url, *(character_ids or []))) if (video_url or character_ids) else []
        audios = _dedupe(routes._normalize_public_urls(*(audio_ids or []))) if audio_ids else []
        try:
            validate_reference_set(images=images, videos=videos, audios=audios)
        except ValueError as exc:
            raise routes.HTTPException(status_code=422, detail=str(exc)) from exc

        provider_model = route_for_inputs(images=images, videos=videos, audios=audios)
        normalized_ratio: str | None
        if provider_model == T2V_MODEL:
            normalized_ratio = _choice(aspect_ratio, T2V_ASPECT_RATIOS, "16:9")
        elif provider_model == I2V_MODEL:
            # H3 follows the input frame ratio in first/last-frame mode.
            normalized_ratio = None
        else:
            normalized_ratio = _choice(aspect_ratio, REFERENCE_ASPECT_RATIOS, "adaptive")

        return {
            "mode": "text" if provider_model == T2V_MODEL else ("image" if provider_model == I2V_MODEL else "video"),
            "provider_model": provider_model,
            "duration": _duration(duration),
            "aspect_ratio": normalized_ratio,
            "resolution": _resolution(resolution),
            "image_url": images or None,
            "reference_video_url": videos or None,
            "video_start": None,
            "video_end": None,
            "audio_ids": audios,
            "character_ids": [],
            "seed": None,
            "grok_mode": "normal",
        }

    routes._normalize_video_request = normalize_video_request
    routes._minimax_h3_normalizer_installed = True


def install_minimax_h3_provider_support() -> None:
    from api import kie_model_specs, video_service
    from db import repository

    _install_enum_value(video_service.VideoModel, "MINIMAX_H3", T2V_MODEL)
    _install_enum_value(video_service.VideoModel, "MINIMAX_H3_I2V_INTERNAL", I2V_MODEL)
    _install_enum_value(video_service.VideoModel, "MINIMAX_H3_REFERENCE_INTERNAL", REFERENCE_MODEL)

    kie_model_specs.VIDEO_SPECS[T2V_MODEL] = kie_model_specs.KieModelSpec(
        model=T2V_MODEL,
        media_type=kie_model_specs.KieMediaType.VIDEO,
        supported_modes=("text",),
        optional_params={"duration": "duration", "aspect_ratio": "aspect_ratio", "resolution": "resolution"},
    )
    kie_model_specs.VIDEO_SPECS[I2V_MODEL] = kie_model_specs.KieModelSpec(
        model=I2V_MODEL,
        media_type=kie_model_specs.KieMediaType.VIDEO,
        supported_modes=("image",),
        reference_type=kie_model_specs.KieReferenceType.FIRST_LAST,
        reference_field="first_frame_url",
        optional_params={"duration": "duration", "resolution": "resolution"},
    )
    kie_model_specs.VIDEO_SPECS[REFERENCE_MODEL] = kie_model_specs.KieModelSpec(
        model=REFERENCE_MODEL,
        media_type=kie_model_specs.KieMediaType.VIDEO,
        supported_modes=("image", "video"),
        reference_type=kie_model_specs.KieReferenceType.NONE,
        optional_params={"duration": "duration", "aspect_ratio": "aspect_ratio", "resolution": "resolution"},
    )
    kie_model_specs.MODEL_SPECS.update({key: kie_model_specs.VIDEO_SPECS[key] for key in MODEL_KEYS})
    _install_generate_wrapper(video_service)

    if not getattr(repository, "_minimax_h3_adapter_installed", False):
        original_all = repository.get_all_model_costs
        original_one = repository.get_model_cost
        original_video_cost = repository.resolve_video_model_cost

        async def get_all_model_costs(session, *args, **kwargs):
            rows = list(await original_all(session, *args, **kwargs))
            existing = {getattr(row, "model_key", None) for row in rows}
            if T2V_MODEL not in existing:
                rows.append(_model_cost(T2V_MODEL))
            # Internal KIE endpoints are implementation details, not products.
            return [row for row in rows if getattr(row, "model_key", None) not in INTERNAL_MODELS]

        async def get_model_cost(session, model_key: str, *args, **kwargs):
            row = await original_one(session, model_key, *args, **kwargs)
            if row is None and model_key in MODEL_KEYS:
                return _model_cost(model_key)
            return row

        async def resolve_video_model_cost(session, model_key: str, *args, **kwargs):
            row = await original_video_cost(session, model_key, *args, **kwargs)
            if row is None and model_key in MODEL_KEYS:
                return _model_cost(model_key, resolution=kwargs.get("resolution"))
            return row

        repository.get_all_model_costs = get_all_model_costs
        repository.get_model_cost = get_model_cost
        repository.resolve_video_model_cost = resolve_video_model_cost
        repository._minimax_h3_adapter_installed = True


def install_minimax_h3_miniapp(routes: Any) -> None:
    install_minimax_h3_provider_support()
    _install_miniapp_normalizer(routes)

    routes.VIDEO_CAPS[PUBLIC_MODEL] = dict(PUBLIC_CAPS)
    # Internal routes remain accepted for old saved jobs/API calls but are not
    # inserted into the public order or user-facing catalog.
    friendly = getattr(routes, "_FRIENDLY_MODEL_NAMES", None)
    if isinstance(friendly, dict):
        friendly.update({key: PUBLIC_DISPLAY_NAME for key in MODEL_KEYS})
    order = getattr(routes, "_VIDEO_MODEL_ORDER", None)
    if isinstance(order, list):
        order[:] = [key for key in order if key not in INTERNAL_MODELS]
        if PUBLIC_MODEL not in order:
            order.insert(0, PUBLIC_MODEL)


def install_minimax_h3_keyboard_support() -> None:
    try:
        from bot.keyboards import models as keyboard_models
    except Exception:
        return

    keyboard_models.VIDEO_CAPS[PUBLIC_MODEL] = dict(PUBLIC_CAPS)
    keyboard_models.VIDEO_MODEL_DESC[PUBLIC_MODEL] = (
        f"{PUBLIC_DISPLAY_NAME} · авто T2V/I2V/Reference · 4–15 сек · 768P/2K · native audio"
    )

    order = getattr(keyboard_models, "_VIDEO_MODEL_ORDER", [])
    order[:] = [key for key in order if key not in INTERNAL_MODELS]
    if PUBLIC_MODEL not in order:
        order.insert(0, PUBLIC_MODEL)

    groups = getattr(keyboard_models, "_VIDEO_GROUPS", [])
    for group_name, keys in groups:
        keys[:] = [key for key in keys if key not in INTERNAL_MODELS]
        if group_name in {"fast", "i2v"} and PUBLIC_MODEL not in keys:
            keys.insert(0, PUBLIC_MODEL)
    # Remove the H3-only technical Reference group introduced by the old integration.
    groups[:] = [
        (name, keys)
        for name, keys in groups
        if not (name == "reference" and all(key in MODEL_KEYS for key in keys))
    ]


def install_minimax_h3_wizard_support(video_wizard: Any) -> None:
    """Recommend the same public H3 family for every compatible scenario."""
    scenarios = getattr(video_wizard, "SCENARIOS", {})
    for scenario_name in ("text", "image", "video"):
        scenario = scenarios.get(scenario_name)
        if not isinstance(scenario, dict):
            continue
        recommended = [key for key in list(scenario.get("recommended") or []) if key not in INTERNAL_MODELS]
        if PUBLIC_MODEL not in recommended:
            recommended.insert(0, PUBLIC_MODEL)
        scenario["recommended"] = recommended[:3]
