"""Targeted production guards for Seedance 2.5 and KIE Veo 3.1.

These guards keep provider-specific transport quirks out of the public product
surface while legacy service code is migrated incrementally.
"""
from __future__ import annotations

import logging
from typing import Any

from api import seedance25_adapter as seedance25

logger = logging.getLogger(__name__)

VEO_PUBLIC_CAPS: dict[str, dict[str, Any]] = {
    "veo3": {
        "modes": ["text", "image"],
        # KIE's current Veo create endpoint exposes no duration field. Veo 3.1
        # upstream uses 8 seconds for reference-image generation, so keep one
        # truthful review value instead of the old decorative 5/10/15 picker.
        "duration_options": [8],
        "aspect_ratios": ["16:9", "9:16"],
        "has_resolution": False,
        "resolutions": [],
        "max_refs": 2,
        "billing_mode": "per_second",
        "provider_managed_duration": True,
    },
    "veo3_fast": {
        "modes": ["text", "image"],
        "duration_options": [8],
        "aspect_ratios": ["16:9", "9:16"],
        "has_resolution": False,
        "resolutions": [],
        "max_refs": 3,
        "billing_mode": "per_second",
        "provider_managed_duration": True,
        "supports_material_references": True,
    },
    "veo3_lite": {
        "modes": ["text", "image"],
        "duration_options": [8],
        "aspect_ratios": ["16:9", "9:16"],
        "has_resolution": False,
        "resolutions": [],
        "max_refs": 3,
        "billing_mode": "per_second",
        "provider_managed_duration": True,
        "supports_material_references": True,
    },
}


def _arg(args: tuple[Any, ...], kwargs: dict[str, Any], name: str, index: int, default: Any = None) -> Any:
    return kwargs.get(name, args[index] if len(args) > index else default)


def _clean_prompt(prompt: Any, *, model_name: str) -> str:
    value = str(prompt or "").strip()
    if not value:
        raise ValueError(f"{model_name} prompt is required")
    return value


async def _seedance_generate(video_service: Any, prompt: str, args: tuple[Any, ...], kwargs: dict[str, Any]):
    clean_prompt = _clean_prompt(prompt, model_name="Seedance 2.5")
    image_url = _arg(args, kwargs, "image_url", 0)
    duration = _arg(args, kwargs, "duration", 5, 5)
    aspect_ratio = _arg(args, kwargs, "aspect_ratio", 6)
    resolution = _arg(args, kwargs, "resolution", 7)

    audio_refs, extra_video_refs, control_options = seedance25._control_payload(
        seedance25._list(kwargs.get("audio_ids"))
    )
    if "duration" in control_options:
        duration = control_options["duration"]

    prepared_images = seedance25._dedupe(await video_service._prepare_video_reference_urls(image_url))

    raw_video_refs = seedance25._dedupe([
        *seedance25._list(kwargs.get("reference_video_url")),
        *extra_video_refs,
    ])
    prepared_videos: list[str] = []
    for raw_video_ref in raw_video_refs[: seedance25.MAX_REFERENCE_VIDEOS]:
        prepared_video = await video_service._prepare_reference_video_url(raw_video_ref)
        if prepared_video and prepared_video not in prepared_videos:
            prepared_videos.append(prepared_video)

    prepared_audio_refs: list[str] = []
    for audio_ref in audio_refs[: seedance25.MAX_REFERENCE_AUDIOS]:
        uploaded = await video_service._upload_local_media(audio_ref, upload_path="audio/apix-video-refs")
        if uploaded and uploaded not in prepared_audio_refs:
            prepared_audio_refs.append(uploaded)

    route = seedance25.route_for_inputs(
        images=prepared_images,
        videos=prepared_videos,
        audios=prepared_audio_refs,
    )
    input_payload = seedance25._seedance25_params(
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
    # The provider requires prompt inside input. The previous automatic routing
    # wrapper accidentally discarded it, causing "Prompt is required in this scene".
    input_payload["prompt"] = clean_prompt

    response = await video_service.kieai_client.create_task(
        {"model": seedance25.MODEL_KEY, "input": input_payload},
        callback_url=kwargs.get("callback_url"),
    )
    if not isinstance(response, dict):
        raise RuntimeError(f"KIE.AI video: invalid createTask response for {seedance25.MODEL_KEY}: {response!r}")
    code = response.get("code")
    if code not in (None, 200, "200"):
        raise RuntimeError(
            f"KIE.AI video createTask failed for {seedance25.MODEL_KEY}: {code} {response.get('msg')}"
        )
    data = response.get("data") or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"KIE.AI video: invalid createTask data for {seedance25.MODEL_KEY}: {data!r}")
    task_id = str(data.get("taskId") or response.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError(f"KIE.AI video: empty taskId for {seedance25.MODEL_KEY}: {response!r}")
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


async def _veo_generate(
    video_service: Any,
    model: Any,
    prompt: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
):
    clean_prompt = _clean_prompt(prompt, model_name="Veo 3.1")
    image_url = _arg(args, kwargs, "image_url", 0)
    last_frame_url = _arg(args, kwargs, "last_frame_url", 1)
    aspect_ratio = _arg(args, kwargs, "aspect_ratio", 6)
    generation_type = kwargs.get("veo_generation_type")
    watermark = kwargs.get("watermark")
    callback_url = kwargs.get("callback_url")
    enable_fallback = bool(kwargs.get("enable_fallback", False))
    enable_translation = bool(kwargs.get("enable_translation", False))

    prepared_images = await video_service._prepare_video_reference_urls(image_url)
    prepared_last = await video_service._prepare_video_reference_url(last_frame_url)
    images = video_service._reference_list(prepared_images)
    if prepared_last and prepared_last not in images:
        images.append(prepared_last)

    selected_type = video_service._normalize_veo_generation_type(model, images, generation_type)
    selected_ratio = video_service._normalize_veo_aspect_ratio(selected_type, aspect_ratio)
    video_service._validate_veo_request(
        model,
        selected_type,
        images,
        selected_ratio,
        enable_fallback,
    )

    payload: dict[str, Any] = {
        "prompt": clean_prompt,
        "model": model.value,
        "aspect_ratio": selected_ratio,
        "enableTranslation": enable_translation,
        "enableFallback": enable_fallback,
        "generationType": selected_type.value,
    }
    if images:
        payload["imageUrls"] = images
    if watermark:
        payload["watermark"] = watermark
    if callback_url:
        payload["callBackUrl"] = callback_url

    # Do not send fake duration/resolution parameters: KIE's current
    # /api/v1/veo/generate schema does not expose them. Public caps likewise no
    # longer claim that the user can control those provider-managed fields.
    response = await video_service.kieai_client.create_veo_task(payload)
    if not isinstance(response, dict):
        raise RuntimeError(f"Veo3: API returned non-dict response: {type(response)}")
    code = response.get("code")
    if code not in (None, 200, "200"):
        raise RuntimeError(f"Veo3 createTask failed: {code} {response.get('msg')}")
    data = response.get("data") or {}
    task_id = str(data.get("taskId") or response.get("taskId") or "").strip() if isinstance(data, dict) else ""
    if not task_id:
        raise RuntimeError(f"Veo3: empty taskId in createTask response: {response!r}")
    logger.info("Veo task %s/%s: %s", model.value, selected_type.value, task_id)
    return video_service.VideoResult(task_id=task_id, provider="veo", uses_webhook=bool(callback_url))


def _install_caps(routes: Any | None = None) -> None:
    try:
        from bot.keyboards import models as keyboard_models

        for key, caps in VEO_PUBLIC_CAPS.items():
            keyboard_models.VIDEO_CAPS[key] = dict(caps)
    except Exception:
        pass

    if routes is not None:
        for key, caps in VEO_PUBLIC_CAPS.items():
            routes.VIDEO_CAPS[key] = dict(caps)


def install_video_runtime_fixes(routes: Any | None = None) -> None:
    """Install once after provider adapters have wrapped video_service."""
    from api import video_service

    _install_caps(routes)
    # Current KIE documentation supports material/reference mode on Fast and Lite.
    video_service._VEO_REFERENCE_MODELS = {
        video_service.VideoModel.VEO_3_FAST,
        video_service.VideoModel.VEO_3_LITE,
    }

    if getattr(video_service, "_apix_seedance_veo_runtime_fixes", False):
        return

    original_generate_video = video_service.generate_video

    async def generate_video(model, prompt: str, *args, **kwargs):
        selected_model = model if isinstance(model, video_service.VideoModel) else video_service.VideoModel(str(model))
        if selected_model.value == seedance25.MODEL_KEY:
            return await _seedance_generate(video_service, prompt, args, kwargs)
        if selected_model in video_service._VEO_MODELS:
            try:
                return await _veo_generate(video_service, selected_model, prompt, args, kwargs)
            except Exception as exc:
                raise video_service._exact_model_failure(selected_model, exc) from exc
        return await original_generate_video(model, prompt, *args, **kwargs)

    video_service.generate_video = generate_video
    video_service._apix_seedance_veo_runtime_fixes = True
