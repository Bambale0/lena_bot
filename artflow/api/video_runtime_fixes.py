"""Targeted production guards for Seedance 2.5 and KIE Veo 3.1.

These guards keep provider-specific transport quirks out of the public product
surface while legacy service code is migrated incrementally.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from api import seedance25_adapter as seedance25
from api.media_gateway import MediaKind, probe_local_media
from api.public_files import ensure_video_reference_aspect_url, local_upload_path_from_url
from api.seedance25_identity import (
    build_identity_transfer_prompt,
    validate_identity_transfer_refs,
)
from core.seedance_repeat_overrides import (
    build_seedance_content_edit_prompt,
    restore_seedance_reference_plan,
)

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


async def seedance25_edit_billing_duration(
    prompt: str,
    reference_video_url: str | list[str] | None,
    *,
    force_edit: bool = False,
) -> int | None:
    refs = seedance25._dedupe(reference_video_url)
    if not refs or (not force_edit and not seedance25.is_explicit_video_edit_prompt(prompt)):
        return None
    if len(refs) != 1:
        raise ValueError("Seedance 2.5 video editing requires exactly one reference video")

    local_path = local_upload_path_from_url(refs[0])
    if local_path is None:
        raise ValueError(
            "Seedance 2.5: для редактирования видео загрузи исходный ролик файлом, "
            "чтобы проверить его длительность и размер до списания"
        )

    probe = await probe_local_media(local_path, MediaKind.VIDEO)
    error = seedance25.validate_reference_video_metadata(
        width=probe.width,
        height=probe.height,
        duration_seconds=probe.duration_seconds,
        min_duration_seconds=4.0,
    )
    if error:
        raise ValueError(error)
    return max(4, min(30, int(math.ceil(float(probe.duration_seconds or 0)))))


async def _validate_seedance_reference_video_url(
    url: str,
    *,
    video_edit: bool = False,
) -> None:
    local_path = local_upload_path_from_url(url)
    if local_path is None:
        return
    probe = await probe_local_media(local_path, MediaKind.VIDEO)
    error = seedance25.validate_reference_video_metadata(
        width=probe.width,
        height=probe.height,
        duration_seconds=probe.duration_seconds,
        min_duration_seconds=4.0 if video_edit else seedance25.MIN_REFERENCE_VIDEO_SECONDS,
    )
    if error:
        raise ValueError(error)


async def _seedance_generate(video_service: Any, prompt: str, args: tuple[Any, ...], kwargs: dict[str, Any]):
    image_url = _arg(args, kwargs, "image_url", 0)
    duration = _arg(args, kwargs, "duration", 4, 5)
    aspect_ratio = _arg(args, kwargs, "aspect_ratio", 5)
    resolution = _arg(args, kwargs, "resolution", 6)

    audio_refs, extra_video_refs, control_options = seedance25._control_payload(
        seedance25._list(kwargs.get("audio_ids"))
    )
    identity_transfer = bool(control_options.get("identity_transfer"))
    raw_user_prompt = str(prompt or "").strip()
    if "duration" in control_options:
        duration = control_options["duration"]

    raw_image_refs = seedance25._dedupe(image_url)
    raw_video_refs = seedance25._dedupe([
        *seedance25._list(kwargs.get("reference_video_url")),
        *extra_video_refs,
    ])

    content_edit = kwargs.get("seedance_content_edit")
    role_plan = None
    if content_edit is not None:
        if not isinstance(content_edit, dict):
            raise ValueError("Invalid Seedance content edit")
        if len(raw_video_refs) != 1:
            raise ValueError("Seedance content edit requires exactly one source video")
        role_plan = restore_seedance_reference_plan(
            seedance25._list(image_url), kwargs.get("seedance_reference_roles"),
            legacy_identity_transfer=identity_transfer,
        )
        raw_image_refs = list(role_plan.image_urls)
        # The typed role plan supersedes legacy tokens before identity wrapping.
        identity_transfer = False
        clean_prompt = build_seedance_content_edit_prompt(role_plan, content_edit)
    elif identity_transfer:
        validate_identity_transfer_refs(images=raw_image_refs, videos=raw_video_refs)
        clean_prompt = build_identity_transfer_prompt(
            raw_user_prompt,
            image_count=len(raw_image_refs),
        )
    else:
        clean_prompt = _clean_prompt(raw_user_prompt, model_name="Seedance 2.5")

    fitted_image_refs = [
        ensure_video_reference_aspect_url(
            ref,
            min_width=seedance25.MIN_REFERENCE_VIDEO_WIDTH,
            min_pixels=seedance25.MIN_REFERENCE_VIDEO_PIXELS,
        )
        or ref
        for ref in raw_image_refs
    ]
    prepared_images = seedance25._dedupe(fitted_image_refs)

    if role_plan is not None and len(prepared_images) != len(role_plan.image_urls):
        raise ValueError("Не удалось подготовить все фото без потери ролей. Загрузи референсы заново.")

    video_edit = content_edit is not None or identity_transfer or (
        bool(raw_video_refs) and seedance25.is_explicit_video_edit_prompt(clean_prompt)
    )
    if video_edit:
        # Neironych edit mode follows source video geometry/duration.
        aspect_ratio = "adaptive"
        duration = seedance25.DURATION_AUTO

    prepared_videos: list[str] = []
    for raw_video_ref in raw_video_refs[: seedance25.MAX_REFERENCE_VIDEOS]:
        await _validate_seedance_reference_video_url(raw_video_ref, video_edit=video_edit)
        if raw_video_ref not in prepared_videos:
            prepared_videos.append(raw_video_ref)

    if content_edit is not None and len(prepared_videos) != 1:
        raise ValueError("Seedance content edit lost its source video before provider submission")

    prepared_audio_refs = seedance25._dedupe(audio_refs)[: seedance25.MAX_REFERENCE_AUDIOS]
    route = seedance25.route_for_inputs(
        images=prepared_images,
        videos=prepared_videos,
        audios=prepared_audio_refs,
    )

    from api import neironych_seedance_runtime
    from api.video_prompt_limits import validate_video_prompt

    validate_video_prompt(seedance25.MODEL_KEY, clean_prompt)
    task_id = await neironych_seedance_runtime.generate_product_video(
        product_model=seedance25.MODEL_KEY,
        prompt=clean_prompt,
        image_urls=prepared_images,
        video_urls=prepared_videos,
        audio_urls=prepared_audio_refs,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        edit=video_edit,
    )
    logger.info(
        "Neironych Seedance 2.5 task route=%s images=%d videos=%d audios=%d task=%s",
        "identity_transfer" if identity_transfer else ("video_edit" if video_edit else route),
        len(prepared_images),
        len(prepared_videos),
        len(prepared_audio_refs),
        task_id,
    )
    return video_service.VideoResult(
        task_id=task_id,
        provider="neironych",
        uses_webhook=False,
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
    aspect_ratio = _arg(args, kwargs, "aspect_ratio", 5)
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
