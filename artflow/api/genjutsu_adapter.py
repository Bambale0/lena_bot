"""Higgsfield Genjutsu integration for APIX.

Two public products share one provider transport:
- Motion Transfer keeps source motion/camera/timing while applying image refs.
- Object Swap replaces selected subjects/objects while preserving the clip.

The adapter deliberately uses authenticated status polling instead of trusting
provider webhooks: Higgsfield's current public V2 SDK transports a webhook URL
but does not document a verifiable callback signature.
"""
from __future__ import annotations

import logging
import math
from typing import Any
from urllib.parse import urlsplit

from api import higgsfield_client
from api.public_files import local_upload_path_from_url, mirror_url
from core.config import settings

MOTION_MODEL = "higgsfield/genjutsu/motion-transfer"
OBJECT_MODEL = "higgsfield/genjutsu/object-swap"
MODEL_KEYS = (MOTION_MODEL, OBJECT_MODEL)

DISPLAY_NAMES = {
    MOTION_MODEL: "🥷 Genjutsu · Перенос движения",
    OBJECT_MODEL: "🥷 Genjutsu · Замена объекта",
}

MAX_REFERENCE_IMAGES = 8
MIN_DURATION_SECONDS = 4
MAX_DURATION_SECONDS = 30
RESOLUTIONS = ["480p", "720p"]

VIDEO_CAPS: dict[str, Any] = {
    "modes": ["image"],
    "duration_options": [],
    "has_resolution": True,
    "resolutions": RESOLUTIONS,
    "resolution_labels": {"480p": "480p", "720p": "720p"},
    "max_refs": MAX_REFERENCE_IMAGES,
    "supports_video_input": True,
    "requires_video_input": True,
    "requires_reference_images": True,
    "duration_from_source": True,
    "billing_mode": "per_second",
}

logger = logging.getLogger(__name__)


def is_genjutsu_configured() -> bool:
    """Return whether server-side Higgsfield credentials are usable."""
    value = str(settings.HIGGSFIELD_CREDENTIALS or "").strip()
    key_id, sep, key_secret = value.partition(":")
    return bool(sep and key_id.strip() and key_secret.strip())


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
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return list(
        dict.fromkeys(
            str(item).strip()
            for item in values
            if str(item or "").strip()
        )
    )


def _validate_public_url(url: str, *, field: str) -> str:
    value = str(url or "").strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field} must be a public HTTP(S) URL")
    return value


def _resolution(value: Any) -> str:
    selected = str(value or "480p")
    if selected not in RESOLUTIONS:
        raise ValueError(f"Genjutsu resolution must be one of {', '.join(RESOLUTIONS)}")
    return selected


def _endpoint(model_key: str) -> str:
    if model_key == MOTION_MODEL:
        return str(settings.HIGGSFIELD_GENJUTSU_MOTION_ENDPOINT).strip()
    if model_key == OBJECT_MODEL:
        return str(settings.HIGGSFIELD_GENJUTSU_OBJECT_ENDPOINT).strip()
    raise ValueError(f"Unknown Genjutsu model: {model_key}")


def validate_inputs(
    *,
    image_urls: Any,
    video_url: str | None,
    resolution: str | None,
) -> tuple[list[str], str, str]:
    images = [_validate_public_url(url, field="reference image") for url in _urls(image_urls)]
    if not images:
        raise ValueError("Genjutsu requires at least one reference image")
    if len(images) > MAX_REFERENCE_IMAGES:
        raise ValueError(
            f"Genjutsu supports at most {MAX_REFERENCE_IMAGES} reference images"
        )
    source_video = _validate_public_url(str(video_url or ""), field="source video")
    return images, source_video, _resolution(resolution)


async def resolve_source_duration_seconds(video_url: str | None) -> int:
    """Return authoritative billing duration from an APIX-owned uploaded video."""
    value = _validate_public_url(str(video_url or ""), field="source video")
    local_path = local_upload_path_from_url(value)
    if local_path is None:
        raise ValueError(
            "Genjutsu source video must be uploaded to APIX so its duration can be verified"
        )

    from api.media_gateway import MediaKind, probe_local_media

    probe = await probe_local_media(local_path, MediaKind.VIDEO)
    duration = probe.duration_seconds
    if duration is None or not math.isfinite(duration):
        raise ValueError("Could not determine Genjutsu source video duration")
    if duration < MIN_DURATION_SECONDS or duration > MAX_DURATION_SECONDS:
        raise ValueError(
            f"Genjutsu source video must be {MIN_DURATION_SECONDS}-{MAX_DURATION_SECONDS} seconds"
        )
    return int(math.ceil(duration))


async def create_genjutsu_task(
    *,
    model_key: str,
    prompt: str,
    image_urls: Any,
    video_url: str | None,
    resolution: str | None,
) -> str:
    images, source_video, selected_resolution = validate_inputs(
        image_urls=image_urls,
        video_url=video_url,
        resolution=resolution,
    )
    payload = {
        "video_url": source_video,
        "image_urls": images,
        "resolution": selected_resolution,
    }
    if clean_prompt := str(prompt or "").strip():
        payload["prompt"] = clean_prompt

    request_id = await higgsfield_client.submit(_endpoint(model_key), payload)
    logger.info(
        "Genjutsu submitted model=%s request_id=%s refs=%d resolution=%s",
        model_key,
        request_id,
        len(images),
        selected_resolution,
    )
    return request_id


async def create_motion_transfer(
    *,
    prompt: str,
    video_url: str,
    image_urls: list[str],
    resolution: str = "480p",
):
    from api.video_service import VideoResult

    request_id = await create_genjutsu_task(
        model_key=MOTION_MODEL,
        prompt=prompt,
        image_urls=image_urls,
        video_url=video_url,
        resolution=resolution,
    )
    return VideoResult(task_id=request_id, provider="higgsfield", uses_webhook=False)


async def create_object_swap(
    *,
    prompt: str,
    video_url: str,
    image_urls: list[str],
    resolution: str = "480p",
):
    from api.video_service import VideoResult

    request_id = await create_genjutsu_task(
        model_key=OBJECT_MODEL,
        prompt=prompt,
        image_urls=image_urls,
        video_url=video_url,
        resolution=resolution,
    )
    return VideoResult(task_id=request_id, provider="higgsfield", uses_webhook=False)


async def poll_genjutsu_video(request_id: str) -> str | None:
    url = await higgsfield_client.poll_video_status(request_id)
    if not url:
        return None
    mirrored = await mirror_url(url, subdir="provider-results")
    if mirrored != url:
        logger.info("Genjutsu result mirrored request_id=%s", request_id)
    else:
        logger.warning(
            "Genjutsu result could not be mirrored request_id=%s; keeping provider URL",
            request_id,
        )
    return mirrored


def _install_generate_wrapper(video_service: Any) -> None:
    if getattr(video_service, "_genjutsu_generate_wrapper_installed", False):
        return
    original = video_service.generate_video

    async def generate_video(model, prompt: str, *args, **kwargs):
        selected = (
            model if isinstance(model, video_service.VideoModel)
            else video_service.VideoModel(str(model))
        )
        if selected.value not in MODEL_KEYS:
            return await original(model, prompt, *args, **kwargs)

        image_url = kwargs.get("image_url")
        if args:
            image_url = args[0]

        request_id = await create_genjutsu_task(
            model_key=selected.value,
            prompt=prompt,
            image_urls=image_url,
            video_url=kwargs.get("reference_video_url"),
            resolution=kwargs.get("resolution"),
        )
        return video_service.VideoResult(
            task_id=request_id,
            provider="higgsfield",
            uses_webhook=False,
        )

    video_service.generate_video = generate_video
    video_service._genjutsu_generate_wrapper_installed = True


def install_genjutsu_provider_support() -> None:
    from api import video_service

    _install_enum_value(video_service.VideoModel, "GENJUTSU_MOTION", MOTION_MODEL)
    _install_enum_value(video_service.VideoModel, "GENJUTSU_OBJECT", OBJECT_MODEL)
    _install_generate_wrapper(video_service)
    video_service.POLL_FN_MAP["higgsfield"] = poll_genjutsu_video


def _install_miniapp_normalizer(routes: Any) -> None:
    if getattr(routes, "_genjutsu_normalizer_installed", False):
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

        images = routes._normalize_public_urls(image_url, *(reference_urls or []))
        videos = routes._normalize_public_urls(video_url) if video_url else []
        if not images:
            raise routes.HTTPException(
                status_code=422,
                detail="Genjutsu requires at least one reference image",
            )
        if len(images) > MAX_REFERENCE_IMAGES:
            raise routes.HTTPException(
                status_code=422,
                detail=f"Genjutsu supports at most {MAX_REFERENCE_IMAGES} reference images",
            )
        if len(videos) != 1:
            raise routes.HTTPException(
                status_code=422,
                detail="Genjutsu requires one uploaded source video",
            )
        if video_start not in (None, 0, 0.0) or video_end is not None:
            raise routes.HTTPException(
                status_code=422,
                detail="Genjutsu uses the complete source video and does not support trimming",
            )

        try:
            selected_resolution = _resolution(resolution)
        except ValueError as exc:
            raise routes.HTTPException(status_code=422, detail=str(exc)) from exc

        provisional_duration = max(
            MIN_DURATION_SECONDS,
            min(MAX_DURATION_SECONDS, int(duration or MIN_DURATION_SECONDS)),
        )
        return {
            "mode": "image",
            "duration": provisional_duration,
            "aspect_ratio": None,
            "resolution": selected_resolution,
            "image_url": images[0] if len(images) == 1 else images,
            "reference_video_url": videos[0],
            "video_start": None,
            "video_end": None,
            "audio_ids": [],
            "character_ids": [],
            "seed": None,
            "grok_mode": "normal",
        }

    routes._normalize_video_request = normalize_video_request
    routes._genjutsu_normalizer_installed = True


def genjutsu_stale_timeout(routes: Any):
    """Return the stale guard used for Genjutsu generations.

    Long Genjutsu renders outlive the shared video poll budget, so the shared
    stale guard must never refund a task that is still inside the provider
    polling window.
    """
    generic = routes.STALE_GENERATION_TIMEOUT
    configured = routes.timedelta(
        seconds=max(60, int(settings.HIGGSFIELD_STALE_TIMEOUT_SECONDS))
    )
    return max(generic, configured)


def _install_miniapp_reconciler(routes: Any) -> None:
    if getattr(routes, "_genjutsu_reconciler_installed", False):
        return
    original = routes._reconcile_generation_status

    async def reconcile_generation_status(session, gen):
        if not gen or str(getattr(gen, "model", "")) not in MODEL_KEYS:
            return await original(session, gen)
        if gen.status not in {
            routes.GenerationStatus.pending,
            routes.GenerationStatus.processing,
        }:
            return gen

        stored_task_id = str(getattr(gen, "task_id", "") or "").strip()
        task_id = routes.provider_task_id(stored_task_id)
        if not task_id:
            return await original(session, gen)

        try:
            result_url = await poll_genjutsu_video(task_id)
        except Exception as exc:
            routes.logger.warning(
                "Genjutsu reconcile failed gen=%s task=%s: %s",
                gen.id,
                task_id,
                exc,
            )
            await routes.repo.fail_generation_and_refund(
                session,
                gen.id,
                str(exc),
                refund_note="reconcile:higgsfield",
            )
            return await routes.repo.get_generation_by_id(session, gen.id)

        if result_url:
            await routes.repo.finish_generation(session, gen.id, result_url)
            return await routes.repo.get_generation_by_id(session, gen.id)

        now = routes.datetime.now(routes.timezone.utc)
        created_at = gen.created_at or now
        if now - created_at >= genjutsu_stale_timeout(routes):
            await routes.repo.fail_generation_and_refund(
                session,
                gen.id,
                "Genjutsu generation timed out before completion",
                refund_note="reconcile:higgsfield_timeout",
            )
            return await routes.repo.get_generation_by_id(session, gen.id)
        return gen

    routes._reconcile_generation_status = reconcile_generation_status
    routes._genjutsu_reconciler_installed = True


def install_genjutsu_miniapp(routes: Any) -> None:
    install_genjutsu_provider_support()
    _install_miniapp_normalizer(routes)
    _install_miniapp_reconciler(routes)

    if not is_genjutsu_configured():
        logger.info("Genjutsu user surfaces disabled: HIGGSFIELD_CREDENTIALS not configured")
        for model_key in MODEL_KEYS:
            routes.VIDEO_CAPS.pop(model_key, None)
        order = getattr(routes, "_VIDEO_MODEL_ORDER", None)
        if isinstance(order, list):
            order[:] = [item for item in order if item not in MODEL_KEYS]
        return

    for model_key in MODEL_KEYS:
        routes.VIDEO_CAPS[model_key] = dict(VIDEO_CAPS)
        friendly = getattr(routes, "_FRIENDLY_MODEL_NAMES", None)
        if isinstance(friendly, dict):
            friendly[model_key] = DISPLAY_NAMES[model_key]

    order = getattr(routes, "_VIDEO_MODEL_ORDER", None)
    if isinstance(order, list):
        for model_key in MODEL_KEYS:
            if model_key not in order:
                order.append(model_key)


def install_genjutsu_keyboard_support() -> None:
    try:
        from bot.keyboards import models as keyboard_models
    except Exception:
        return

    if not is_genjutsu_configured():
        logger.info("Genjutsu Telegram surface disabled: HIGGSFIELD_CREDENTIALS not configured")
        for model_key in MODEL_KEYS:
            keyboard_models.VIDEO_CAPS.pop(model_key, None)
            keyboard_models.VIDEO_MODEL_DESC.pop(model_key, None)
        order = getattr(keyboard_models, "_VIDEO_MODEL_ORDER", None)
        if isinstance(order, list):
            order[:] = [item for item in order if item not in MODEL_KEYS]
        groups = getattr(keyboard_models, "_VIDEO_GROUPS", None)
        if isinstance(groups, list):
            groups[:] = [item for item in groups if item[0] != "genjutsu"]
        titles = getattr(keyboard_models, "VIDEO_GROUP_TITLES", None)
        if isinstance(titles, dict):
            titles.pop("genjutsu", None)
        return

    for model_key in MODEL_KEYS:
        keyboard_models.VIDEO_CAPS[model_key] = dict(VIDEO_CAPS)
        keyboard_models.VIDEO_MODEL_DESC[model_key] = (
            f"{DISPLAY_NAMES[model_key]} · исходное видео + до "
            f"{MAX_REFERENCE_IMAGES} референсов · {MIN_DURATION_SECONDS}–{MAX_DURATION_SECONDS} сек · 480p/720p"
        )

    order = getattr(keyboard_models, "_VIDEO_MODEL_ORDER", None)
    if isinstance(order, list):
        for model_key in reversed(MODEL_KEYS):
            if model_key not in order:
                order.insert(0, model_key)

    groups = getattr(keyboard_models, "_VIDEO_GROUPS", None)
    titles = getattr(keyboard_models, "VIDEO_GROUP_TITLES", None)
    if isinstance(groups, list):
        group = next((item for item in groups if item[0] == "genjutsu"), None)
        if group is None:
            groups.append(("genjutsu", list(MODEL_KEYS)))
        else:
            group[1][:] = list(MODEL_KEYS)
    if isinstance(titles, dict):
        titles["genjutsu"] = "🥷 Genjutsu"
