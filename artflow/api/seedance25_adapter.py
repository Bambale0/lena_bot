"""Runtime support for KIE Bytedance Seedance 2.5.

Seedance 2.5 uses the same KIE Market createTask / recordInfo flow as the
existing video models, but its input contract is richer than the older
Seedance 2.x variants. The model supports three mutually exclusive scenarios:

* text-to-video;
* image-to-video with first frame or first+last frames;
* multimodal reference-to-video with image/video/audio references.

This module registers the model and patches the existing video stack so APIX can
ship the full Seedance 2.5 contract without adding a second provider service.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

MODEL_KEY = "bytedance/seedance-2-5"
DISPLAY_NAME = "🌱 Seedance 2.5"

DURATION_AUTO = -1
DURATIONS = [DURATION_AUTO, *range(4, 31)]
ASPECT_RATIOS = ["adaptive", "16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]
RESOLUTIONS = ["480p", "720p"]
OUTPUT_FORMATS = ["mp4", "mov"]
CREDITS_PER_SECOND = {"480p": 7.0, "720p": 10.0}
AUTO_DURATION_BILLING_SECONDS = 30

logger = logging.getLogger(__name__)

VIDEO_CAPS: dict[str, Any] = {
    "modes": ["text", "image", "first_last", "reference", "multimodal", "video"],
    "duration_options": DURATIONS,
    "aspect_ratios": ASPECT_RATIOS,
    "has_resolution": True,
    "resolutions": RESOLUTIONS,
    "max_refs": 30,
    "max_reference_images": 30,
    "max_reference_videos": 10,
    "max_reference_audios": 10,
    "supports_video_input": True,
    "supports_audio_references": True,
    "supports_audio_generation": True,
    "supports_return_last_frame": True,
    "supports_output_format": True,
    "supports_web_search": True,
    "output_formats": OUTPUT_FORMATS,
    "billing_mode": "per_second",
    "auto_duration_billing_seconds": AUTO_DURATION_BILLING_SECONDS,
}


def _install_enum_value(enum_cls: Any, name: str, value: str) -> Any:
    """Register a runtime enum value so existing `VideoModel(value)` code works."""
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
        return [value] if value else []
    return [str(item) for item in value if item]


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


def _seedance25_params(params: dict[str, Any]) -> dict[str, Any]:
    """Build the official Seedance 2.5 `input` payload.

    First/last-frame inputs are mutually exclusive with multimodal reference
    inputs. The caller passes `mode` so this builder can select exactly one
    scenario and avoid provider-side 422s.
    """
    mode = str(params.get("mode") or "text").lower()
    image_refs = _list(params.get("reference_image_urls") or params.get("reference_urls"))[:30]
    video_refs = _list(params.get("reference_video_urls") or params.get("reference_video_url"))[:10]
    audio_refs = _list(params.get("reference_audio_urls") or params.get("reference_audio_url"))[:10]

    first_frame = str(params.get("first_frame_url") or "").strip()
    last_frame = str(params.get("last_frame_url") or "").strip()

    out: dict[str, Any] = {
        "resolution": _choice(params.get("resolution"), RESOLUTIONS, "720p"),
        "aspect_ratio": _choice(params.get("aspect_ratio"), ASPECT_RATIOS, "adaptive"),
        "duration": _duration(params.get("duration")),
        "output_format": _choice(params.get("output_format"), OUTPUT_FORMATS, "mp4"),
        "return_last_frame": _bool(params.get("return_last_frame"), False),
        "generate_audio": _bool(params.get("generate_audio"), True),
    }

    if params.get("web_search") is not None:
        out["web_search"] = _bool(params.get("web_search"), False)
    if params.get("nsfw_checker") is not None:
        out["nsfw_checker"] = _bool(params.get("nsfw_checker"), False)

    wants_multimodal = mode in {"reference", "multimodal", "video", "audio"} or bool(video_refs or audio_refs)
    if wants_multimodal:
        if image_refs:
            out["reference_image_urls"] = image_refs
        if video_refs:
            out["reference_video_urls"] = video_refs
        if audio_refs:
            out["reference_audio_urls"] = audio_refs
        return out

    if not first_frame and image_refs:
        first_frame = image_refs[0]
    if not last_frame and len(image_refs) >= 2:
        last_frame = image_refs[1]

    if first_frame:
        out["first_frame_url"] = first_frame
    if last_frame:
        out["last_frame_url"] = last_frame
    return out


def _model_cost(*, resolution: str | None = None):
    from db.models import GenerationType

    selected_resolution = resolution if resolution in CREDITS_PER_SECOND else "720p"
    credits = CREDITS_PER_SECOND[selected_resolution]
    return SimpleNamespace(
        model_key=MODEL_KEY,
        display_name=DISPLAY_NAME,
        gen_type=GenerationType.video,
        credits=float(credits),
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
        reference_video_url = kwargs.get("reference_video_url")
        audio_refs = _list(kwargs.get("audio_ids"))
        mode = str(kwargs.get("grok_mode") or "").lower()
        if mode not in {"text", "image", "first_last", "reference", "multimodal", "video", "audio"}:
            if reference_video_url or audio_refs:
                mode = "multimodal"
            elif image_url:
                mode = "image"
            else:
                mode = "text"

        prepared_images = await video_service._prepare_video_reference_urls(image_url)
        prepared_videos = []
        if reference_video_url:
            prepared_video = await video_service._prepare_reference_video_url(reference_video_url)
            if prepared_video:
                prepared_videos.append(prepared_video)
        prepared_audio_refs = []
        for audio_ref in audio_refs[:10]:
            uploaded = await video_service._upload_local_media(audio_ref, upload_path="audio/apix-video-refs")
            if uploaded:
                prepared_audio_refs.append(uploaded)

        input_payload = _seedance25_params(
            {
                "mode": mode,
                "reference_urls": prepared_images,
                "reference_video_urls": prepared_videos,
                "reference_audio_urls": prepared_audio_refs,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                # Full provider defaults. Dedicated UI/API fields can override
                # these later without changing the provider builder.
                "return_last_frame": kwargs.get("return_last_frame", False),
                "generate_audio": kwargs.get("generate_audio", True),
                "output_format": kwargs.get("output_format", "mp4"),
                "web_search": kwargs.get("web_search"),
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
        logger.info("KIE.AI video task %s: %s", MODEL_KEY, task_id)
        return video_service.VideoResult(task_id=task_id, provider="kieai", uses_webhook=bool(kwargs.get("callback_url")))

    video_service.generate_video = generate_video
    video_service._seedance25_generate_wrapper_installed = True


def _install_seedance25_miniapp_normalizer(routes: Any) -> None:
    if getattr(routes, "_seedance25_normalizer_installed", False):
        return

    original_normalize_video_request = routes._normalize_video_request

    def normalize_video_request(*, model_key: str, mode: str, duration: int, aspect_ratio: str | None, resolution: str | None, image_url: str | None, reference_urls: list[str] | None, video_url: str | None = None, video_start: float | None = None, video_end: float | None = None, audio_ids: list[str] | None = None, character_ids: list[str] | None = None, seed: int | None = None, grok_mode: str | None = None) -> dict[str, Any]:
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

        selected_mode = str(mode or "text").lower()
        if selected_mode not in VIDEO_CAPS["modes"]:
            selected_mode = "image" if (image_url or reference_urls) else "text"
        image_refs = routes._normalize_public_urls(image_url, *(reference_urls or [])) if (image_url or reference_urls) else []
        video_refs = routes._normalize_public_urls(video_url) if video_url else []
        audio_refs = [str(item) for item in (audio_ids or []) if str(item or "").strip()]
        if len(image_refs) > 30:
            raise routes.HTTPException(status_code=422, detail="Seedance 2.5 supports at most 30 reference images")
        if len(video_refs) > 10:
            raise routes.HTTPException(status_code=422, detail="Seedance 2.5 supports at most 10 reference videos")
        if len(audio_refs) > 10:
            raise routes.HTTPException(status_code=422, detail="Seedance 2.5 supports at most 10 reference audio files")

        normalized_duration = _duration(duration)
        normalized_resolution = _choice(resolution, RESOLUTIONS, "720p")
        normalized_aspect_ratio = _choice(aspect_ratio, ASPECT_RATIOS, "adaptive")

        if selected_mode in {"image", "first_last"}:
            if not image_refs:
                raise routes.HTTPException(status_code=422, detail="Seedance 2.5 image mode requires first_frame_url")
            if len(image_refs) > 2:
                raise routes.HTTPException(status_code=422, detail="Seedance 2.5 first/last-frame mode supports one or two images")
            if video_refs or audio_refs:
                raise routes.HTTPException(status_code=422, detail="Seedance 2.5 first/last-frame mode cannot be mixed with video/audio references")
            normalized_image: str | list[str] | None = image_refs[0] if len(image_refs) == 1 else image_refs[:2]
        elif selected_mode in {"reference", "multimodal", "video", "audio"}:
            if not (image_refs or video_refs or audio_refs):
                raise routes.HTTPException(status_code=422, detail="Seedance 2.5 multimodal mode requires at least one reference")
            normalized_image = image_refs or None
            selected_mode = "multimodal"
        else:
            if image_refs or video_refs or audio_refs:
                selected_mode = "multimodal" if (video_refs or audio_refs) else "image"
                normalized_image = image_refs[0] if len(image_refs) == 1 else image_refs
            else:
                normalized_image = None

        return {
            "mode": selected_mode,
            "duration": normalized_duration,
            "billing_duration": _billing_duration(normalized_duration),
            "aspect_ratio": normalized_aspect_ratio,
            "resolution": normalized_resolution,
            "image_url": normalized_image,
            "reference_video_url": video_refs[0] if video_refs else None,
            "video_start": None,
            "video_end": None,
            # Reuse existing route plumbing: the Seedance wrapper interprets
            # audio_ids as reference_audio_urls only for MODEL_KEY.
            "audio_ids": audio_refs,
            "character_ids": [],
            "seed": None,
            # Reuse grok_mode as an internal mode carrier; the Seedance wrapper
            # strips it before provider submission.
            "grok_mode": selected_mode,
        }

    routes._normalize_video_request = normalize_video_request
    routes._seedance25_normalizer_installed = True


def install_seedance25_provider_support() -> None:
    """Install model enum/spec/repository support used by backend generation."""
    from api import kie_model_specs, video_service
    from db import repository

    _install_enum_value(video_service.VideoModel, "SEEDANCE_25", MODEL_KEY)
    kie_model_specs.VIDEO_SPECS[MODEL_KEY] = kie_model_specs.KieModelSpec(
        model=MODEL_KEY,
        media_type=kie_model_specs.KieMediaType.VIDEO,
        supported_modes=("text", "image", "first_last", "reference", "multimodal", "video"),
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
    """Expose model capabilities in Mini App routes after miniapp_routes loads."""
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
    """Keep Telegram bot keyboard capability registry in sync when imported."""
    try:
        from bot.keyboards import models as keyboard_models
    except Exception:
        return
    keyboard_models.VIDEO_CAPS[MODEL_KEY] = dict(VIDEO_CAPS)
