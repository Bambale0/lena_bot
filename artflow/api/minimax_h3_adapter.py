"""Runtime integration for all KIE MiniMax H3 video routes.

The KIE Market exposes MiniMax H3 as three separate model keys:

* minimax-h3/text-to-video
* minimax-h3/image-to-video
* minimax-h3/reference-to-video

They share the existing KIE createTask / callback / recordInfo lifecycle, so this
adapter registers the provider contracts and reuses APIX's current video queue,
webhook handling, history and billing instead of adding a second task system.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

T2V_MODEL = "minimax-h3/text-to-video"
I2V_MODEL = "minimax-h3/image-to-video"
REFERENCE_MODEL = "minimax-h3/reference-to-video"
MODEL_KEYS = (T2V_MODEL, I2V_MODEL, REFERENCE_MODEL)

DISPLAY_NAMES = {
    T2V_MODEL: "🎞 MiniMax H3 Text",
    I2V_MODEL: "🎞 MiniMax H3 Image",
    REFERENCE_MODEL: "🎞 MiniMax H3 Reference",
}

DURATIONS = list(range(4, 16))
T2V_ASPECT_RATIOS = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
REFERENCE_ASPECT_RATIOS = ["adaptive", *T2V_ASPECT_RATIOS]
T2V_RESOLUTIONS = ["2K", "768P"]
MAX_REFERENCE_IMAGES = 16
MAX_REFERENCE_VIDEOS = 3
MAX_REFERENCE_AUDIOS = 1
MAX_REFERENCE_VIDEO_SECONDS = 6

logger = logging.getLogger(__name__)

VIDEO_CAPS: dict[str, dict[str, Any]] = {
    T2V_MODEL: {
        "modes": ["text"],
        "duration_options": DURATIONS,
        "aspect_ratios": T2V_ASPECT_RATIOS,
        "has_resolution": True,
        "resolutions": T2V_RESOLUTIONS,
        "billing_mode": "per_second",
    },
    I2V_MODEL: {
        "modes": ["image"],
        "duration_options": DURATIONS,
        "aspect_ratios": [],
        "has_resolution": False,
        "resolutions": [],
        "max_refs": 2,
        "billing_mode": "per_second",
    },
    REFERENCE_MODEL: {
        # Keep image as the transport mode in generic clients. The H3-specific
        # normalizer accepts images, videos and audio together for this key.
        "modes": ["image"],
        "duration_options": DURATIONS,
        "aspect_ratios": REFERENCE_ASPECT_RATIOS,
        "has_resolution": False,
        "resolutions": [],
        "max_refs": MAX_REFERENCE_IMAGES,
        "supports_video_input": True,
        "max_video_refs": MAX_REFERENCE_VIDEOS,
        # Existing Mini App fields are URL lists. For H3 they carry reference
        # audio URLs and extra reference video URLs instead of provider IDs.
        "max_audio_ids": MAX_REFERENCE_AUDIOS,
        "max_character_ids": MAX_REFERENCE_VIDEOS - 1,
        "supports_audio_references": True,
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
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return []


def _duration(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 6
    return max(4, min(15, parsed))


def _choice(value: Any, allowed: list[str], default: str | None = None) -> str | None:
    if not allowed:
        return None
    selected = str(value or default or allowed[0])
    return selected if selected in allowed else (default or allowed[0])


def _t2v_input(*, prompt: str, duration: Any, aspect_ratio: Any, resolution: Any) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "duration": _duration(duration),
        "aspect_ratio": _choice(aspect_ratio, T2V_ASPECT_RATIOS, "16:9"),
        "resolution": _choice(resolution, T2V_RESOLUTIONS, "2K"),
    }


def _i2v_input(*, prompt: str, duration: Any, images: list[str]) -> dict[str, Any]:
    if not images:
        raise ValueError("MiniMax H3 Image-to-Video requires first_frame_url")
    payload: dict[str, Any] = {
        "prompt": prompt,
        "duration": _duration(duration),
        "first_frame_url": images[0],
    }
    if len(images) > 1:
        payload["last_frame_url"] = images[1]
    return payload


def _reference_input(
    *,
    prompt: str,
    duration: Any,
    aspect_ratio: Any,
    images: list[str],
    videos: list[str],
    audios: list[str],
) -> dict[str, Any]:
    if not (images or videos or audios):
        raise ValueError("MiniMax H3 Reference-to-Video requires at least one reference")
    if len(images) > MAX_REFERENCE_IMAGES:
        raise ValueError(f"MiniMax H3 supports at most {MAX_REFERENCE_IMAGES} reference images")
    if len(videos) > MAX_REFERENCE_VIDEOS:
        raise ValueError(f"MiniMax H3 supports at most {MAX_REFERENCE_VIDEOS} reference videos")
    if len(audios) > MAX_REFERENCE_AUDIOS:
        raise ValueError(f"MiniMax H3 supports at most {MAX_REFERENCE_AUDIOS} reference audio file")

    payload: dict[str, Any] = {
        "prompt": prompt,
        "duration": _duration(duration),
        "aspect_ratio": _choice(aspect_ratio, REFERENCE_ASPECT_RATIOS, "adaptive"),
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
        display_name=DISPLAY_NAMES[model_key],
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
        prepared_images = await video_service._prepare_video_reference_urls(image_url)

        raw_videos = _urls(kwargs.get("reference_video_url"))
        raw_videos.extend(_urls(kwargs.get("character_ids")))
        prepared_videos: list[str] = []
        for raw_url in raw_videos[:MAX_REFERENCE_VIDEOS]:
            prepared = await video_service._prepare_reference_video_url(raw_url)
            if prepared and prepared not in prepared_videos:
                prepared_videos.append(prepared)

        prepared_audios: list[str] = []
        for raw_url in _urls(kwargs.get("audio_ids"))[:MAX_REFERENCE_AUDIOS]:
            prepared = await _prepare_audio_reference(video_service, raw_url)
            if prepared:
                prepared_audios.append(prepared)

        duration = kwargs.get("duration", 6)
        aspect_ratio = kwargs.get("aspect_ratio")
        resolution = kwargs.get("resolution")

        if selected.value == T2V_MODEL:
            input_payload = _t2v_input(
                prompt=prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
            )
        elif selected.value == I2V_MODEL:
            input_payload = _i2v_input(prompt=prompt, duration=duration, images=prepared_images[:2])
        else:
            input_payload = _reference_input(
                prompt=prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                images=prepared_images[:MAX_REFERENCE_IMAGES],
                videos=prepared_videos,
                audios=prepared_audios,
            )

        response = await video_service.kieai_client.create_task(
            {"model": selected.value, "input": input_payload},
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

        logger.info("KIE.AI MiniMax H3 task model=%s task=%s", selected.value, task_id)
        return video_service.VideoResult(
            task_id=task_id,
            provider="kieai",
            uses_webhook=bool(kwargs.get("callback_url")),
        )

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

        normalized_duration = _duration(duration)
        images = routes._normalize_public_urls(image_url, *(reference_urls or [])) if (image_url or reference_urls) else []
        videos = routes._normalize_public_urls(video_url, *(character_ids or [])) if (video_url or character_ids) else []
        audios = routes._normalize_public_urls(*(audio_ids or [])) if audio_ids else []

        if model_key == T2V_MODEL:
            if images or videos or audios:
                raise routes.HTTPException(status_code=422, detail="MiniMax H3 Text-to-Video does not accept references")
            return {
                "mode": "text",
                "duration": normalized_duration,
                "aspect_ratio": _choice(aspect_ratio, T2V_ASPECT_RATIOS, "16:9"),
                "resolution": _choice(resolution, T2V_RESOLUTIONS, "2K"),
                "image_url": None,
                "reference_video_url": None,
                "video_start": None,
                "video_end": None,
                "audio_ids": [],
                "character_ids": [],
                "seed": None,
                "grok_mode": "normal",
            }

        if model_key == I2V_MODEL:
            if not images:
                raise routes.HTTPException(status_code=422, detail="MiniMax H3 Image-to-Video requires a first frame")
            if len(images) > 2:
                raise routes.HTTPException(status_code=422, detail="MiniMax H3 Image-to-Video supports first and optional last frame only")
            if videos or audios:
                raise routes.HTTPException(status_code=422, detail="MiniMax H3 Image-to-Video does not accept video/audio references")
            return {
                "mode": "image",
                "duration": normalized_duration,
                "aspect_ratio": None,
                "resolution": None,
                "image_url": images[0] if len(images) == 1 else images[:2],
                "reference_video_url": None,
                "video_start": None,
                "video_end": None,
                "audio_ids": [],
                "character_ids": [],
                "seed": None,
                "grok_mode": "normal",
            }

        if not (images or videos or audios):
            raise routes.HTTPException(status_code=422, detail="MiniMax H3 Reference-to-Video requires at least one reference")
        if len(images) > MAX_REFERENCE_IMAGES:
            raise routes.HTTPException(status_code=422, detail=f"MiniMax H3 supports at most {MAX_REFERENCE_IMAGES} images")
        if len(videos) > MAX_REFERENCE_VIDEOS:
            raise routes.HTTPException(status_code=422, detail=f"MiniMax H3 supports at most {MAX_REFERENCE_VIDEOS} videos")
        if len(audios) > MAX_REFERENCE_AUDIOS:
            raise routes.HTTPException(status_code=422, detail=f"MiniMax H3 supports at most {MAX_REFERENCE_AUDIOS} audio reference")

        return {
            "mode": "image" if images else "video",
            "duration": normalized_duration,
            "aspect_ratio": _choice(aspect_ratio, REFERENCE_ASPECT_RATIOS, "adaptive"),
            "resolution": None,
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

    _install_enum_value(video_service.VideoModel, "MINIMAX_H3_T2V", T2V_MODEL)
    _install_enum_value(video_service.VideoModel, "MINIMAX_H3_I2V", I2V_MODEL)
    _install_enum_value(video_service.VideoModel, "MINIMAX_H3_REFERENCE", REFERENCE_MODEL)

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
        optional_params={"duration": "duration"},
    )
    kie_model_specs.VIDEO_SPECS[REFERENCE_MODEL] = kie_model_specs.KieModelSpec(
        model=REFERENCE_MODEL,
        media_type=kie_model_specs.KieMediaType.VIDEO,
        supported_modes=("image", "video"),
        reference_type=kie_model_specs.KieReferenceType.NONE,
        optional_params={"duration": "duration", "aspect_ratio": "aspect_ratio"},
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
            for model_key in MODEL_KEYS:
                if model_key not in existing:
                    rows.append(_model_cost(model_key))
            return rows

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

    for key, caps in VIDEO_CAPS.items():
        routes.VIDEO_CAPS[key] = dict(caps)
    friendly = getattr(routes, "_FRIENDLY_MODEL_NAMES", None)
    if isinstance(friendly, dict):
        friendly.update({
            T2V_MODEL: "MiniMax H3 Text",
            I2V_MODEL: "MiniMax H3 Image",
            REFERENCE_MODEL: "MiniMax H3 Reference",
        })
    order = getattr(routes, "_VIDEO_MODEL_ORDER", None)
    if isinstance(order, list):
        for key in reversed(MODEL_KEYS):
            if key not in order:
                order.insert(0, key)


def install_minimax_h3_keyboard_support() -> None:
    try:
        from bot.keyboards import models as keyboard_models
    except Exception:
        return

    keyboard_models.VIDEO_CAPS.update({key: dict(caps) for key, caps in VIDEO_CAPS.items()})
    for key, name in DISPLAY_NAMES.items():
        keyboard_models.VIDEO_MODEL_DESC[key] = {
            T2V_MODEL: f"{name} · текст → видео · до 15 сек · 2K",
            I2V_MODEL: f"{name} · первый/последний кадр → видео",
            REFERENCE_MODEL: f"{name} · фото + видео + аудио референсы",
        }[key]

    order = getattr(keyboard_models, "_VIDEO_MODEL_ORDER", [])
    for key in reversed(MODEL_KEYS):
        if key not in order:
            order.insert(0, key)

    groups = getattr(keyboard_models, "_VIDEO_GROUPS", [])
    for group_name, keys in groups:
        if group_name == "fast" and T2V_MODEL not in keys:
            keys.insert(0, T2V_MODEL)
        elif group_name == "i2v" and I2V_MODEL not in keys:
            keys.insert(0, I2V_MODEL)
    if not any(group_name == "reference" for group_name, _keys in groups):
        groups.insert(1, ("reference", [REFERENCE_MODEL]))
    keyboard_models.VIDEO_GROUP_TITLES["reference"] = "🎛️ По референсам"


def install_minimax_h3_wizard_support(video_wizard: Any) -> None:
    """Put H3 into the task-first Telegram wizard recommendations."""
    scenarios = getattr(video_wizard, "SCENARIOS", {})
    mapping = {"text": T2V_MODEL, "image": I2V_MODEL, "video": REFERENCE_MODEL}
    for scenario_name, model_key in mapping.items():
        scenario = scenarios.get(scenario_name)
        if not isinstance(scenario, dict):
            continue
        recommended = list(scenario.get("recommended") or [])
        if model_key not in recommended:
            recommended.insert(0, model_key)
        scenario["recommended"] = recommended[:3]
