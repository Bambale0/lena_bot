"""Runtime support for KIE Bytedance Seedance 2.5.

Seedance 2.5 is exposed as one public multimodal model. The user never chooses
text/image/first-last/reference provider scenarios manually. APIX derives the
provider payload from the media that is actually present:

* no references -> text-to-video;
* exactly one image and no video/audio -> image-to-video using first_frame_url;
* two or more images, or any video/audio reference -> multimodal reference mode.

This intentionally removes the previous two-image first+last-frame behaviour:
for APIX, two images are ordinary Seedance 2.5 reference images.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

MODEL_KEY = "bytedance/seedance-2-5"
DISPLAY_NAME = "🌱 Seedance 2.5"

DURATION_AUTO = -1
DURATIONS = [4, 5, 10, 15, 30]
ASPECT_RATIOS = ["adaptive", "16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]
RESOLUTIONS = ["480p", "720p"]
OUTPUT_FORMATS = ["mp4", "mov"]
CREDITS_PER_SECOND = {"480p": 7.0, "720p": 10.0}
AUTO_DURATION_BILLING_SECONDS = 30
CONTROL_PREFIX = "__apix_seedance25:"

MAX_REFERENCE_IMAGES = 30
MAX_REFERENCE_VIDEOS = 10
MAX_REFERENCE_AUDIOS = 10

logger = logging.getLogger(__name__)

VIDEO_CAPS: dict[str, Any] = {
    "modes": ["text", "image", "multimodal"],
    "auto_route_by_inputs": True,
    "duration_options": DURATIONS,
    "aspect_ratios": ASPECT_RATIOS,
    "has_resolution": True,
    "resolutions": RESOLUTIONS,
    "max_refs": MAX_REFERENCE_IMAGES,
    "max_reference_images": MAX_REFERENCE_IMAGES,
    "max_reference_videos": MAX_REFERENCE_VIDEOS,
    "max_reference_audios": MAX_REFERENCE_AUDIOS,
    "supports_video_input": True,
    "supports_audio_references": True,
    "supports_audio_generation": True,
    "supports_return_last_frame": True,
    "supports_output_format": True,
    "supports_web_search": True,
    "supports_auto_duration": True,
    "output_formats": OUTPUT_FORMATS,
    "billing_mode": "per_second",
    "auto_duration_billing_seconds": AUTO_DURATION_BILLING_SECONDS,
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


def _list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return []


def _dedupe(values: Any) -> list[str]:
    return list(dict.fromkeys(_list(values)))


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _choice(value: Any, allowed: list[str], default: str) -> str:
    selected = str(value or default)
    return selected if selected in allowed else default


def _duration(value: Any) -> int:
    if value in {"auto", "AUTO", DURATION_AUTO, str(DURATION_AUTO)}:
        return DURATION_AUTO
    try:
        duration = int(value or 5)
    except (TypeError, ValueError):
        duration = 5
    return max(4, min(30, duration))


def route_for_inputs(*, images: list[str], videos: list[str], audios: list[str]) -> str:
    """Return APIX's automatic Seedance scenario from real inputs only."""
    if not images and not videos and not audios:
        return "text"
    if len(images) == 1 and not videos and not audios:
        return "image"
    return "multimodal"


def _control_payload(raw_values: list[str]) -> tuple[list[str], list[str], dict[str, Any]]:
    """Split reference URLs from namespaced UI control tokens.

    Plain values in `audio_ids` are treated as Seedance audio reference URLs.
    Namespaced `video_ref` values are URL transport for additional video refs.
    The legacy `scenario` token is accepted but deliberately ignored by routing.
    """
    audio_refs: list[str] = []
    video_refs: list[str] = []
    options: dict[str, Any] = {}
    for raw in raw_values:
        value = str(raw or "").strip()
        if not value:
            continue
        if not value.startswith(CONTROL_PREFIX):
            audio_refs.append(value)
            continue
        payload = value[len(CONTROL_PREFIX):]
        key, _, data = payload.partition("=")
        key = key.strip()
        data = data.strip()
        if key == "audio_ref" and data:
            audio_refs.append(data)
        elif key == "video_ref" and data:
            video_refs.append(data)
        elif key == "duration" and data:
            options["duration"] = _duration(data)
        elif key == "output_format" and data:
            options["output_format"] = data
        elif key == "generate_audio":
            options["generate_audio"] = _bool(data, True)
        elif key == "return_last_frame":
            options["return_last_frame"] = _bool(data, False)
        elif key == "web_search":
            options["web_search"] = _bool(data, False)
        # `scenario` is intentionally ignored: route_for_inputs is authoritative.
    return _dedupe(audio_refs)[:MAX_REFERENCE_AUDIOS], _dedupe(video_refs)[:MAX_REFERENCE_VIDEOS], options


def _seedance25_params(params: dict[str, Any]) -> dict[str, Any]:
    """Build a Seedance 2.5 payload from inputs, never from a UI mode switch."""
    image_refs = _dedupe(params.get("reference_image_urls") or params.get("reference_urls"))
    video_refs = _dedupe(params.get("reference_video_urls") or params.get("reference_video_url"))
    audio_refs = _dedupe(params.get("reference_audio_urls") or params.get("reference_audio_url"))

    # Backward compatibility for callers that still send frame fields. Under the
    # new APIX product rule, two frame images become multimodal references.
    first_frame = str(params.get("first_frame_url") or "").strip()
    last_frame = str(params.get("last_frame_url") or "").strip()
    if first_frame:
        image_refs = _dedupe([first_frame, *image_refs])
    if last_frame:
        image_refs = _dedupe([*image_refs, last_frame])

    image_refs = image_refs[:MAX_REFERENCE_IMAGES]
    video_refs = video_refs[:MAX_REFERENCE_VIDEOS]
    audio_refs = audio_refs[:MAX_REFERENCE_AUDIOS]
    route = route_for_inputs(images=image_refs, videos=video_refs, audios=audio_refs)

    aspect_ratio = _choice(params.get("aspect_ratio"), ASPECT_RATIOS, "adaptive")
    # A single image is the first frame; its own frame ratio is authoritative.
    if route == "image":
        aspect_ratio = "adaptive"

    out: dict[str, Any] = {
        "resolution": _choice(params.get("resolution"), RESOLUTIONS, "720p"),
        "aspect_ratio": aspect_ratio,
        "duration": _duration(params.get("duration")),
        "output_format": _choice(params.get("output_format"), OUTPUT_FORMATS, "mp4"),
        "return_last_frame": _bool(params.get("return_last_frame"), False),
        "generate_audio": _bool(params.get("generate_audio"), True),
    }

    if params.get("web_search") is not None:
        out["web_search"] = _bool(params.get("web_search"), False)
    if params.get("nsfw_checker") is not None:
        out["nsfw_checker"] = _bool(params.get("nsfw_checker"), False)

    if route == "image":
        out["first_frame_url"] = image_refs[0]
        return out

    if route == "multimodal":
        if image_refs:
            out["reference_image_urls"] = image_refs
        if video_refs:
            out["reference_video_urls"] = video_refs
        if audio_refs:
            out["reference_audio_urls"] = audio_refs
    return out


def _model_cost(*, resolution: str | None = None):
    from db.models import GenerationType

    selected_resolution = resolution if resolution in CREDITS_PER_SECOND else "720p"
    return SimpleNamespace(
        model_key=MODEL_KEY,
        display_name=DISPLAY_NAME,
        gen_type=GenerationType.video,
        credits=float(CREDITS_PER_SECOND[selected_resolution]),
        is_active=True,
    )


def _billing_duration(duration: Any) -> int:
    normalized = _duration(duration)
    return AUTO_DURATION_BILLING_SECONDS if normalized == DURATION_AUTO else normalized


def _as_video_model(value: Any, video_service: Any) -> Any:
    return value if isinstance(value, video_service.VideoModel) else video_service.VideoModel(str(value))


def _install_seedance25_generate_wrapper(video_service: Any) -> None:
    if getattr(video_service, "_seedance25_generate_wrapper_installed", False):
        return

    original_generate_video = video_service.generate_video

    async def generate_video(model, prompt: str, *args, **kwargs):
        selected_model = _as_video_model(model, video_service)
        if selected_model.value != MODEL_KEY:
            return await original_generate_video(model, prompt, *args, **kwargs)

        image_url = kwargs.get("image_url")
        if args:
            image_url = args[0]
        duration = kwargs.get("duration", 5)
        aspect_ratio = kwargs.get("aspect_ratio")
        resolution = kwargs.get("resolution")

        audio_refs, extra_video_refs, control_options = _control_payload(_list(kwargs.get("audio_ids")))
        if "duration" in control_options:
            duration = control_options["duration"]

        prepared_images = _dedupe(await video_service._prepare_video_reference_urls(image_url))

        raw_video_refs = _dedupe([
            *_list(kwargs.get("reference_video_url")),
            *extra_video_refs,
        ])
        prepared_videos: list[str] = []
        for raw_video_ref in raw_video_refs[:MAX_REFERENCE_VIDEOS]:
            prepared_video = await video_service._prepare_reference_video_url(raw_video_ref)
            if prepared_video and prepared_video not in prepared_videos:
                prepared_videos.append(prepared_video)

        prepared_audio_refs: list[str] = []
        for audio_ref in audio_refs[:MAX_REFERENCE_AUDIOS]:
            uploaded = await video_service._upload_local_media(audio_ref, upload_path="audio/apix-video-refs")
            if uploaded and uploaded not in prepared_audio_refs:
                prepared_audio_refs.append(uploaded)

        route = route_for_inputs(
            images=prepared_images,
            videos=prepared_videos,
            audios=prepared_audio_refs,
        )
        input_payload = _seedance25_params(
            {
                "reference_image_urls": prepared_images,
                "reference_video_urls": prepared_videos,
                "reference_audio_urls": prepared_audio_refs,
                "duration": duration,
                "aspect_ratio": "adaptive" if route == "image" else aspect_ratio,
                "resolution": resolution,
                "return_last_frame": control_options.get("return_last_frame", kwargs.get("return_last_frame", False)),
                "generate_audio": control_options.get("generate_audio", kwargs.get("generate_audio", True)),
                "output_format": control_options.get("output_format", kwargs.get("output_format", "mp4")),
                "web_search": control_options.get("web_search", kwargs.get("web_search")),
                "nsfw_checker": kwargs.get("nsfw_checker"),
            }
        )

        resp = await video_service.kieai_client.create_task(
            {"model": MODEL_KEY, "input": input_payload},
            callback_url=kwargs.get("callback_url"),
        )
        if not isinstance(resp, dict):
            raise RuntimeError(f"KIE.AI video: invalid createTask response for {MODEL_KEY}: {resp!r}")
        code = resp.get("code")
        if code not in (None, 200, "200"):
            raise RuntimeError(f"KIE.AI video createTask failed for {MODEL_KEY}: {code} {resp.get('msg')}")
        data = resp.get("data") or {}
        if not isinstance(data, dict):
            raise RuntimeError(f"KIE.AI video: invalid createTask data for {MODEL_KEY}: {data!r}")
        task_id = str(data.get("taskId") or resp.get("taskId") or "").strip()
        if not task_id:
            raise RuntimeError(f"KIE.AI video: empty taskId for {MODEL_KEY}: {resp!r}")
        logger.info(
            "KIE.AI Seedance 2.5 task route=%s images=%d videos=%d audios=%d task=%s",
            route,
            len(prepared_images),
            len(prepared_videos),
            len(prepared_audio_refs),
            task_id,
        )
        return video_service.VideoResult(
            task_id=task_id,
            provider="kieai",
            uses_webhook=bool(kwargs.get("callback_url")),
        )

    video_service.generate_video = generate_video
    video_service._seedance25_generate_wrapper_installed = True


def _install_seedance25_miniapp_normalizer(routes: Any) -> None:
    if getattr(routes, "_seedance25_normalizer_installed", False):
        return

    original_normalize_video_request = routes._normalize_video_request

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
        if model_key != MODEL_KEY:
            return original_normalize_video_request(
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

        parsed_audio_refs, extra_video_refs, control_options = _control_payload(
            [str(item) for item in (audio_ids or []) if str(item or "").strip()]
        )
        image_refs = (
            _dedupe(routes._normalize_public_urls(image_url, *(reference_urls or [])))
            if (image_url or reference_urls)
            else []
        )
        video_refs = (
            _dedupe(routes._normalize_public_urls(video_url, *extra_video_refs))
            if (video_url or extra_video_refs)
            else []
        )
        audio_refs = _dedupe(parsed_audio_refs)

        if len(image_refs) > MAX_REFERENCE_IMAGES:
            raise routes.HTTPException(status_code=422, detail=f"Seedance 2.5 supports at most {MAX_REFERENCE_IMAGES} reference images")
        if len(video_refs) > MAX_REFERENCE_VIDEOS:
            raise routes.HTTPException(status_code=422, detail=f"Seedance 2.5 supports at most {MAX_REFERENCE_VIDEOS} reference videos")
        if len(audio_refs) > MAX_REFERENCE_AUDIOS:
            raise routes.HTTPException(status_code=422, detail=f"Seedance 2.5 supports at most {MAX_REFERENCE_AUDIOS} reference audio files")

        route = route_for_inputs(images=image_refs, videos=video_refs, audios=audio_refs)
        normalized_duration = _duration(control_options.get("duration", duration))
        billing_duration = _billing_duration(normalized_duration)
        normalized_resolution = _choice(resolution, RESOLUTIONS, "720p")
        normalized_aspect_ratio = _choice(aspect_ratio, ASPECT_RATIOS, "adaptive")
        if route == "image":
            normalized_aspect_ratio = "adaptive"

        if route == "text":
            normalized_image: str | list[str] | None = None
        elif route == "image":
            normalized_image = image_refs[0]
        else:
            normalized_image = image_refs or None

        control_tokens = [item for item in (audio_ids or []) if str(item).startswith(CONTROL_PREFIX)]
        return {
            "mode": route,
            "duration": billing_duration,
            "provider_duration": normalized_duration,
            "billing_duration": billing_duration,
            "aspect_ratio": normalized_aspect_ratio,
            "resolution": normalized_resolution,
            "image_url": normalized_image,
            "reference_video_url": video_refs or None,
            "video_start": None,
            "video_end": None,
            "audio_ids": [*audio_refs, *control_tokens],
            "character_ids": [],
            "seed": None,
            "grok_mode": route,
        }

    routes._normalize_video_request = normalize_video_request
    routes._seedance25_normalizer_installed = True


def install_seedance25_provider_support() -> None:
    from api import kie_model_specs, video_service
    from db import repository

    _install_enum_value(video_service.VideoModel, "SEEDANCE_25", MODEL_KEY)
    kie_model_specs.VIDEO_SPECS[MODEL_KEY] = kie_model_specs.KieModelSpec(
        model=MODEL_KEY,
        media_type=kie_model_specs.KieMediaType.VIDEO,
        supported_modes=("text", "image", "multimodal"),
        reference_type=kie_model_specs.KieReferenceType.NONE,
        param_builder=_seedance25_params,
    )
    kie_model_specs.MODEL_SPECS[MODEL_KEY] = kie_model_specs.VIDEO_SPECS[MODEL_KEY]
    _install_seedance25_generate_wrapper(video_service)

    if not getattr(repository, "_seedance25_adapter_installed", False):
        original_get_all = repository.get_all_model_costs
        original_get_one = repository.get_model_cost
        original_resolve_video = repository.resolve_video_model_cost

        async def get_all_model_costs(session, *args, **kwargs):
            rows = list(await original_get_all(session, *args, **kwargs))
            if not any(getattr(row, "model_key", None) == MODEL_KEY for row in rows):
                rows.append(_model_cost())
            return rows

        async def get_model_cost(session, model_key: str, *args, **kwargs):
            row = await original_get_one(session, model_key, *args, **kwargs)
            if row is None and model_key == MODEL_KEY:
                return _model_cost()
            return row

        async def resolve_video_model_cost(session, model_key: str, *args, **kwargs):
            row = await original_resolve_video(session, model_key, *args, **kwargs)
            if row is None and model_key == MODEL_KEY:
                return _model_cost(resolution=kwargs.get("resolution"))
            return row

        repository.get_all_model_costs = get_all_model_costs
        repository.get_model_cost = get_model_cost
        repository.resolve_video_model_cost = resolve_video_model_cost
        repository._seedance25_adapter_installed = True

    video_service._seedance25_adapter_installed = True


def install_seedance25_miniapp(routes: Any) -> None:
    install_seedance25_provider_support()
    _install_seedance25_miniapp_normalizer(routes)
    routes.VIDEO_CAPS[MODEL_KEY] = dict(VIDEO_CAPS)
    order = getattr(routes, "_VIDEO_MODEL_ORDER", [])
    if MODEL_KEY not in order:
        try:
            insert_at = order.index("bytedance/seedance-2")
        except ValueError:
            insert_at = len(order)
        order.insert(insert_at, MODEL_KEY)


def install_seedance25_keyboard_support() -> None:
    try:
        from bot.keyboards import models as keyboard_models
    except Exception:
        return
    keyboard_models.VIDEO_CAPS[MODEL_KEY] = dict(VIDEO_CAPS)
