"""Unified execution, pricing and polling registry for provider contracts."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from api import (
    advanced_video_service,
    assistant_service,
    image_service,
    kieai_client,
    kling_grok_service,
    midjourney_full_service,
    photo_prompt_service,
    suno_full_service,
    video_service,
)
from api.image_service import ImageModel
from api.provider_contract_catalog import (
    ALL_CONTRACTS,
    MIDJOURNEY_OPERATIONS,
    SUNO_OPERATIONS,
)
from api.video_service import VideoModel
from bot.services.generation_service import (
    get_image_price_for_model,
    get_midjourney_price,
    get_music_price_for_model,
    get_video_price_for_model,
)
from db.models import GenerationType


class PollKind(StrEnum):
    NONE = "none"
    KIE = "kie"
    VEO = "veo"
    MIDJOURNEY = "midjourney"
    SUNO_MUSIC = "suno_music"
    SUNO_LYRICS = "suno_lyrics"
    SUNO_WAV = "suno_wav"
    SUNO_STEMS = "suno_stems"
    SUNO_MIDI = "suno_midi"
    SUNO_VIDEO = "suno_video"
    SUNO_COVER = "suno_cover"
    SUNO_VOICE_VALIDATE = "suno_voice_validate"
    SUNO_VOICE = "suno_voice"


@dataclass(frozen=True)
class OperationStart:
    task_id: str | None
    provider: str
    poll_kind: PollKind
    result_urls: tuple[str, ...] = ()
    output: Any = None
    uses_webhook: bool = False


@dataclass(frozen=True)
class OperationStatus:
    state: str
    result_urls: tuple[str, ...] = ()
    output: Any = None
    error: str | None = None


@dataclass(frozen=True)
class OperationSpec:
    contract_id: str
    generation_type: GenerationType
    model: str
    executor: Callable[..., Awaitable[Any]]
    poll_kind: PollKind
    billable: bool = True
    price_alias: str | None = None
    fixed_params: tuple[tuple[str, Any], ...] = ()

    @property
    def fixed(self) -> dict[str, Any]:
        return dict(self.fixed_params)


_IMAGE_MODELS = {
    contract.contract_id: contract.model
    for contract in ALL_CONTRACTS
    if contract.contract_id.startswith("image.")
}
_PRIMARY_VIDEO_MODELS = {
    contract.contract_id: contract.model
    for contract in ALL_CONTRACTS
    if contract.contract_id.startswith("video.")
    and contract.model in {item.value for item in VideoModel}
}


async def _execute_image(*, model: str, **params: Any) -> Any:
    return await image_service.generate_image(ImageModel(model), **params)


async def _execute_video(*, model: str, **params: Any) -> Any:
    return await video_service.generate_video(VideoModel(model), **params)


async def _execute_photo_prompt(**params: Any) -> Any:
    image_data = params.pop("image_base64", None)
    if not isinstance(image_data, str) or not image_data:
        raise ValueError("image_base64 is required")
    import base64

    try:
        image_bytes = base64.b64decode(image_data, validate=True)
    except Exception as exc:
        raise ValueError("image_base64 is invalid") from exc
    return await photo_prompt_service.generate_prompt_from_photo_result(
        image_bytes,
        str(params.pop("mime_type", "image/jpeg")),
    )


async def _execute_assistant(**params: Any) -> Any:
    messages = params.pop("messages", None)
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    return await assistant_service.generate_assistant_result(messages, **params)


async def _execute_moderation(**params: Any) -> Any:
    return await assistant_service.generate_prompt_moderation_decision(**params)


_ADVANCED_EXECUTORS: dict[str, tuple[Callable[..., Awaitable[Any]], str | None, PollKind]] = {
    "video.wan27.r2v": (advanced_video_service.create_wan_reference_to_video, "wan/2-7-image-to-video", PollKind.KIE),
    "video.wan27.edit": (advanced_video_service.create_wan_video_edit, "wan/2-7-image-to-video", PollKind.KIE),
    "video.happyhorse.r2v": (advanced_video_service.create_happyhorse_reference_to_video, "happyhorse/image-to-video", PollKind.KIE),
    "video.happyhorse.edit": (advanced_video_service.create_happyhorse_video_edit, "happyhorse/image-to-video", PollKind.KIE),
    "video.happyhorse11.t2v": (advanced_video_service.create_happyhorse_text_to_video, "happyhorse/text-to-video", PollKind.KIE),
    "video.happyhorse11.i2v": (advanced_video_service.create_happyhorse_image_to_video, "happyhorse/image-to-video", PollKind.KIE),
    "video.happyhorse11.r2v": (advanced_video_service.create_happyhorse_reference_to_video, "happyhorse/image-to-video", PollKind.KIE),
    "video.grok.upscale": (kling_grok_service.create_grok_upscale, "grok-imagine/image-to-video", PollKind.KIE),
    "video.grok.extend": (kling_grok_service.create_grok_extend, "grok-imagine/image-to-video", PollKind.KIE),
    "video.grok.preview15": (kling_grok_service.create_grok_preview_15, "grok-imagine/image-to-video", PollKind.KIE),
    "video.veo.extend": (video_service.extend_veo_video, "veo3_fast", PollKind.VEO),
    "video.veo.1080": (video_service.get_veo_1080p_url, "veo3_fast", PollKind.NONE),
    "video.veo.4k": (video_service.generate_video_4k, "veo3_fast", PollKind.VEO),
}


_SUNO_POLL_KIND: dict[str, PollKind] = {
    "generate": PollKind.SUNO_MUSIC,
    "extend": PollKind.SUNO_MUSIC,
    "upload-cover": PollKind.SUNO_MUSIC,
    "upload-extend": PollKind.SUNO_MUSIC,
    "add-instrumental": PollKind.SUNO_MUSIC,
    "add-vocals": PollKind.SUNO_MUSIC,
    "replace-section": PollKind.SUNO_MUSIC,
    "persona": PollKind.NONE,
    "mashup": PollKind.SUNO_MUSIC,
    "lyrics": PollKind.SUNO_LYRICS,
    "timestamped-lyrics": PollKind.NONE,
    "style": PollKind.NONE,
    "cover-art": PollKind.SUNO_COVER,
    "wav": PollKind.SUNO_WAV,
    "stems": PollKind.SUNO_STEMS,
    "midi": PollKind.SUNO_MIDI,
    "music-video": PollKind.SUNO_VIDEO,
    "voice-validate": PollKind.SUNO_VOICE_VALIDATE,
    "voice-regenerate": PollKind.SUNO_VOICE_VALIDATE,
    "voice-create": PollKind.SUNO_VOICE,
}


_MJ_BILLABLE = {"imagine", "action", "change", "blend", "describe", "modal", "editor", "video"}


def _build_specs() -> dict[str, OperationSpec]:
    specs: dict[str, OperationSpec] = {}

    for contract_id, model in _IMAGE_MODELS.items():
        specs[contract_id] = OperationSpec(
            contract_id=contract_id,
            generation_type=GenerationType.image,
            model=model,
            executor=_execute_image,
            poll_kind=PollKind.KIE,
            fixed_params=(("model", model),),
        )

    for contract_id, model in _PRIMARY_VIDEO_MODELS.items():
        poll_kind = PollKind.VEO if model in {"veo3", "veo3_fast", "veo3_lite"} else PollKind.KIE
        specs[contract_id] = OperationSpec(
            contract_id=contract_id,
            generation_type=GenerationType.video,
            model=model,
            executor=_execute_video,
            poll_kind=poll_kind,
            fixed_params=(("model", model),),
        )

    for contract_id, (executor, price_alias, poll_kind) in _ADVANCED_EXECUTORS.items():
        model = next(item.model for item in ALL_CONTRACTS if item.contract_id == contract_id)
        fixed: tuple[tuple[str, Any], ...] = ()
        if contract_id.startswith("video.happyhorse11."):
            fixed = (("version_11", True),)
        specs[contract_id] = OperationSpec(
            contract_id=contract_id,
            generation_type=GenerationType.video,
            model=model,
            executor=executor,
            poll_kind=poll_kind,
            price_alias=price_alias,
            fixed_params=fixed,
        )

    for operation, function_name in SUNO_OPERATIONS.items():
        contract_id = f"suno.{operation}"
        specs[contract_id] = OperationSpec(
            contract_id=contract_id,
            generation_type=GenerationType.music,
            model=f"suno/{operation}",
            executor=getattr(suno_full_service, function_name),
            poll_kind=_SUNO_POLL_KIND[operation],
            billable=True,
        )

    for operation, function_name in MIDJOURNEY_OPERATIONS.items():
        contract_id = f"midjourney.{operation}"
        specs[contract_id] = OperationSpec(
            contract_id=contract_id,
            generation_type=(GenerationType.video if operation == "video" else GenerationType.image),
            model=f"midjourney/{operation}",
            executor=getattr(midjourney_full_service, function_name),
            poll_kind=(PollKind.MIDJOURNEY if operation not in {"fetch", "list"} else PollKind.NONE),
            billable=operation in _MJ_BILLABLE,
        )

    specs.update(
        {
            "llm.kie.responses": OperationSpec(
                contract_id="llm.kie.responses",
                generation_type=GenerationType.image,
                model="gpt-responses",
                executor=_execute_assistant,
                poll_kind=PollKind.NONE,
                billable=False,
                fixed_params=(("provider", "kie_responses"),),
            ),
            "llm.kie.claude": OperationSpec(
                contract_id="llm.kie.claude",
                generation_type=GenerationType.image,
                model="claude-sonnet-4-5",
                executor=_execute_assistant,
                poll_kind=PollKind.NONE,
                billable=False,
                fixed_params=(("provider", "kie_claude"),),
            ),
            "llm.comet.chat": OperationSpec(
                contract_id="llm.comet.chat",
                generation_type=GenerationType.image,
                model="openai-compatible-chat",
                executor=_execute_assistant,
                poll_kind=PollKind.NONE,
                billable=False,
                fixed_params=(("provider", "comet_chat"),),
            ),
            "llm.photo-prompt": OperationSpec(
                contract_id="llm.photo-prompt",
                generation_type=GenerationType.image,
                model="photo-prompt-router",
                executor=_execute_photo_prompt,
                poll_kind=PollKind.NONE,
                billable=False,
            ),
            "llm.moderation": OperationSpec(
                contract_id="llm.moderation",
                generation_type=GenerationType.image,
                model="strict-json-moderation",
                executor=_execute_moderation,
                poll_kind=PollKind.NONE,
                billable=False,
            ),
        }
    )
    return specs


OPERATION_SPECS = _build_specs()
PUBLIC_API_CONTRACT_IDS = frozenset(OPERATION_SPECS)


def get_operation_spec(contract_id: str) -> OperationSpec:
    try:
        return OPERATION_SPECS[str(contract_id)]
    except KeyError as exc:
        raise KeyError(f"Unknown provider contract: {contract_id}") from exc


def _coerce_dataclass_params(spec: OperationSpec, params: dict[str, Any]) -> dict[str, Any]:
    result = dict(params)
    if spec.contract_id == "video.kling30":
        if isinstance(result.get("shots"), list):
            result["shots"] = [
                item if isinstance(item, kling_grok_service.KlingShot) else kling_grok_service.KlingShot(**item)
                for item in result["shots"]
            ]
        if isinstance(result.get("elements"), list):
            result["elements"] = [
                item
                if isinstance(item, kling_grok_service.KlingElement)
                else kling_grok_service.KlingElement(
                    name=item["name"],
                    description=item["description"],
                    kind=kling_grok_service.KlingElementKind(item["kind"]),
                    media_urls=tuple(item.get("media_urls") or ()),
                    audio_urls=tuple(item.get("audio_urls") or ()),
                    start_time_ms=item.get("start_time_ms"),
                    end_time_ms=item.get("end_time_ms"),
                )
                for item in result["elements"]
            ]
    if spec.contract_id.startswith("suno.") and isinstance(result.get("tuning"), dict):
        result["tuning"] = suno_full_service.SunoTuning(**result["tuning"])
    return result


def validate_operation_params(spec: OperationSpec, params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise TypeError("params must be an object")
    merged = {**params, **spec.fixed}
    merged = _coerce_dataclass_params(spec, merged)
    signature = inspect.signature(spec.executor)
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if not accepts_kwargs:
        unknown = sorted(set(merged) - set(signature.parameters))
        if unknown:
            raise ValueError(f"Unsupported parameters for {spec.contract_id}: {unknown}")
    return merged


async def resolve_operation_price(
    session: AsyncSession,
    spec: OperationSpec,
    params: dict[str, Any],
) -> int:
    if not spec.billable:
        return 0

    if spec.contract_id.startswith("midjourney."):
        return await get_midjourney_price(spec.contract_id.split(".", 1)[1], session=session)

    if spec.generation_type == GenerationType.image:
        return await get_image_price_for_model(
            spec.price_alias or spec.model,
            quality=str(params.get("quality") or params.get("resolution") or "") or None,
            count=int(params.get("n") or params.get("count") or 1),
            session=session,
        )

    if spec.generation_type == GenerationType.video:
        return await get_video_price_for_model(
            spec.price_alias or spec.model,
            duration=int(params.get("duration") or params.get("extend_times") or 1),
            resolution=str(params.get("resolution") or params.get("mode") or "") or None,
            has_video_input=bool(
                params.get("reference_video_url")
                or params.get("reference_video_urls")
                or params.get("video_url")
                or params.get("first_clip_url")
            ),
            session=session,
        )

    if spec.generation_type == GenerationType.music:
        model = str(params.get("model") or "suno/v5.0")
        model_aliases = {
            "V4_5": "suno/v4.5",
            "V5": "suno/v5.0",
            "V5_5": "suno/v5.5",
        }
        return await get_music_price_for_model(model_aliases.get(model, model), session=session)

    return 0


def _urls_from_any(value: Any) -> tuple[str, ...]:
    urls: list[str] = []
    if isinstance(value, str):
        if value.startswith("http"):
            urls.append(value)
        elif value.startswith(("{", "[")):
            try:
                urls.extend(_urls_from_any(json.loads(value)))
            except json.JSONDecodeError:
                pass
    elif isinstance(value, dict):
        for key in (
            "resultUrls", "result_urls", "urls", "audioUrls", "audio_urls",
            "videoUrls", "video_urls", "imageUrls", "image_urls",
        ):
            urls.extend(_urls_from_any(value.get(key)))
        for key in (
            "resultUrl", "result_url", "url", "audioUrl", "audio_url",
            "videoUrl", "video_url", "imageUrl", "image_url",
        ):
            urls.extend(_urls_from_any(value.get(key)))
        for nested in value.values():
            urls.extend(_urls_from_any(nested))
    elif isinstance(value, (list, tuple)):
        for item in value:
            urls.extend(_urls_from_any(item))
    return tuple(dict.fromkeys(urls))


async def execute_operation(spec: OperationSpec, params: dict[str, Any]) -> OperationStart:
    validated = validate_operation_params(spec, params)
    result = await spec.executor(**validated)

    if isinstance(result, image_service.ImageResult):
        urls = tuple(result.result_urls or ([result.url] if result.url else []))
        return OperationStart(result.task_id, "comet" if not result.is_async else "kie", spec.poll_kind if result.is_async else PollKind.NONE, urls, result)
    if isinstance(result, video_service.VideoResult):
        return OperationStart(result.task_id, result.provider, spec.poll_kind, uses_webhook=result.uses_webhook)
    if isinstance(result, (advanced_video_service.MarketVideoTask, kling_grok_service.ProviderVideoTask)):
        return OperationStart(result.task_id, "kie", spec.poll_kind, uses_webhook=result.uses_webhook)
    if isinstance(result, suno_full_service.SunoTask):
        return OperationStart(result.task_id, "kie", spec.poll_kind)
    if isinstance(result, str):
        if result.startswith("http"):
            return OperationStart(None, "provider", PollKind.NONE, (result,), result)
        if spec.contract_id.startswith("midjourney.") and spec.contract_id not in {"midjourney.fetch", "midjourney.list"}:
            return OperationStart(result, "comet", spec.poll_kind)
        return OperationStart(None, "provider", PollKind.NONE, output=result)

    task_id = getattr(result, "task_id", None)
    if task_id:
        return OperationStart(str(task_id), "provider", spec.poll_kind, output=result)
    return OperationStart(None, "provider", PollKind.NONE, _urls_from_any(result), result)


_SUNO_POLLERS: dict[PollKind, Callable[[str], Awaitable[dict[str, Any]]]] = {
    PollKind.SUNO_MUSIC: suno_full_service.get_music_task,
    PollKind.SUNO_LYRICS: suno_full_service.get_lyrics_task,
    PollKind.SUNO_WAV: suno_full_service.get_wav_task,
    PollKind.SUNO_STEMS: suno_full_service.get_stem_task,
    PollKind.SUNO_MIDI: suno_full_service.get_midi_task,
    PollKind.SUNO_VIDEO: suno_full_service.get_music_video_task,
    PollKind.SUNO_COVER: suno_full_service.get_cover_art_task,
    PollKind.SUNO_VOICE_VALIDATE: suno_full_service.get_voice_validation,
    PollKind.SUNO_VOICE: suno_full_service.get_custom_voice,
}


def _state_from_payload(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    raw = str(data.get("state") or data.get("status") or data.get("callbackType") or "").lower()
    if raw in {"success", "complete", "completed", "ready"}:
        return "completed"
    if raw in {"fail", "failed", "error", "cancel", "cancelled"}:
        return "failed"
    return "processing"


async def poll_operation(spec: OperationSpec, task_id: str) -> OperationStatus:
    if spec.poll_kind == PollKind.NONE:
        return OperationStatus("completed")
    if spec.poll_kind == PollKind.KIE:
        payload = await kieai_client.get_task_status(task_id)
        state = _state_from_payload(payload)
        error = None
        if state == "failed":
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            error = str(data.get("failMsg") or data.get("msg") or "Provider task failed")
        return OperationStatus(state, _urls_from_any(payload), payload, error)
    if spec.poll_kind == PollKind.VEO:
        url = await video_service.poll_veo_status(task_id)
        return OperationStatus("completed", (url,), url) if url else OperationStatus("processing")
    if spec.poll_kind == PollKind.MIDJOURNEY:
        task = await midjourney_full_service.fetch_task(task_id)
        if task.status == midjourney_full_service.MidjourneyTaskStatus.SUCCESS:
            urls = tuple(url for url in (task.image_url, task.video_url) if url)
            return OperationStatus("completed", urls, task)
        if task.status in {
            midjourney_full_service.MidjourneyTaskStatus.FAILURE,
            midjourney_full_service.MidjourneyTaskStatus.CANCEL,
        }:
            return OperationStatus("failed", error=task.fail_reason or task.status.value)
        return OperationStatus("processing", output=task)
    if spec.poll_kind in _SUNO_POLLERS:
        payload = await _SUNO_POLLERS[spec.poll_kind](task_id)
        state = _state_from_payload(payload)
        error = None
        if state == "failed":
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            error = str(data.get("errorMessage") or data.get("error") or data.get("msg") or "Suno task failed")
        return OperationStatus(state, _urls_from_any(payload), payload, error)
    raise ValueError(f"Unsupported poll kind: {spec.poll_kind}")
