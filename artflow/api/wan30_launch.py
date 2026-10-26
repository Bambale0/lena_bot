"""Shared Wan3 input normalization and server-measured quote for APIX surfaces."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from api.media_gateway import MediaKind, probe_local_media
from api.public_files import local_upload_path_from_url
from api.wan30_contract import (
    WAN30_MODELS,
    Wan30Request,
    validate_wan30_request,
    wan30_max_billable_seconds,
)
from core.model_pricing import pricing_variant_key
from db import repository as repo


async def _duration_for_owned_media(url: str, kind: MediaKind) -> float:
    """Never price client-asserted video duration or SSRF-fetch arbitrary URLs."""
    path = local_upload_path_from_url(url)
    if not path or not path.is_file():
        raise ValueError("Загрузи исходное видео/аудио в APIX — так можно точно посчитать цену.")
    probe = await probe_local_media(path, kind)
    duration = probe.duration_seconds
    if (
        duration is None or not math.isfinite(duration)
        or duration <= 0 or duration > 30
    ):
        raise ValueError("Не удалось определить длительность исходного файла.")
    return round(float(duration), 3)


def _clean_urls(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError("References must be a list of URLs")
    return tuple(str(item).strip() for item in value if str(item or "").strip())


async def create_wan30_request(
    *,
    model: str,
    prompt: str,
    mode: str,
    image_urls: str | list[str] | None = None,
    video_url: str | None = None,
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str | None = None,
    options: dict[str, Any] | None = None,
) -> Wan30Request:
    if model not in WAN30_MODELS:
        raise ValueError("Unsupported Wan video model")
    if mode not in {"text", "image", "video"}:
        raise ValueError("Выбери «Текст», «Фото» или «Видео».")
    opts = dict(options or {})
    # The modern composer sends the first photo as both image_url and the
    # first element of reference_urls for backward compatibility. Do not
    # accidentally interpret one uploaded photo as first+last frames.
    photos = tuple(dict.fromkeys(_clean_urls(image_urls)))
    extra_photos = _clean_urls(opts.get("reference_image_urls"))
    videos = _clean_urls(opts.get("reference_video_urls"))
    audios = _clean_urls(opts.get("reference_audio_urls"))
    files = _clean_urls(opts.get("reference_file_urls"))
    links = _clean_urls(opts.get("reference_link_urls"))
    if video_url:
        videos = (str(video_url).strip(),) + videos
    # Photo editors can echo the main input in the advanced reference list.
    # Count/probe each actual video/audio once, in original user order.
    videos = tuple(dict.fromkeys(videos))
    audios = tuple(dict.fromkeys(audios))
    explicit_first = str(opts.get("first_frame_url") or "").strip() or None
    explicit_last = str(opts.get("last_frame_url") or "").strip() or None
    if explicit_first:
        # A resumed Telegram UI can echo explicit frames in its generic
        # photo preview. Do not re-add them as conflicting references.
        photos = tuple(u for u in photos if u not in {explicit_first, explicit_last})

    first = explicit_first
    last = explicit_last
    if mode == "image" and not (videos or audios or extra_photos or files or links or first):
        if len(photos) == 1:
            first = photos[0]
            photos = ()
        elif len(photos) == 2:
            first, last = photos
            photos = ()
    elif mode == "image" and not (photos or extra_photos or first):
        raise ValueError("Добавь хотя бы одно фото.")

    if mode == "video" and not videos:
        raise ValueError("Загрузи исходное видео для редактирования.")

    all_images = tuple(dict.fromkeys(photos + extra_photos))
    video_lengths = tuple(
        [await _duration_for_owned_media(url, MediaKind.VIDEO) for url in videos]
    )
    audio_lengths = tuple(
        [await _duration_for_owned_media(url, MediaKind.AUDIO) for url in audios]
    )
    actual_mode = (
        "edit" if mode == "video" else
        "first_last" if first and last else
        "first" if first else
        "reference" if all_images or videos or audios else
        "file" if files else "link" if links else "text"
    )
    # Restored server-owned recipes retain reference/edit/frame semantics.
    # This internal option is not accepted as a public API field; validation
    # below still rejects incompatible/missing media.
    actual_mode = opts.get("source_mode") or actual_mode
    task = Wan30Request(
        model=model, prompt=prompt,
        mode=actual_mode,
        first_frame_url=first, last_frame_url=last,
        reference_image_urls=all_images,
        reference_video_urls=videos, reference_audio_urls=audios,
        reference_file_urls=files, reference_link_urls=links,
        reference_video_durations=video_lengths,
        reference_audio_durations=audio_lengths,
        duration=duration,
        resolution=str(resolution or "720p"),
        aspect_ratio=str(aspect_ratio or "adaptive"),
        audio=opts.get("audio", True),
        seed=opts.get("seed"),
        nsfw_checker=opts.get("nsfw_checker", True),
    )
    validate_wan30_request(task)
    return task


@dataclass(frozen=True)
class Wan30Quote:
    request: Wan30Request
    billable_seconds: int
    rate: float
    credits: float
    resolution: str

    def stored_params(self) -> dict[str, Any]:
        normalized = asdict(self.request)
        for field, value in normalized.items():
            if isinstance(value, tuple):
                normalized[field] = list(value)
        return {
            # Preserve the original validated, independently measured inputs.
            # A later repeat must NEVER infer media or payment from supplier GET.
            "wan30_request": normalized,
            "wan30_billing": {
                "reserved_billable_seconds": self.billable_seconds,
                "input_video_seconds": sum(self.request.reference_video_durations),
                "output_seconds": self.request.duration,
                "rate": self.rate,
                "reserved_credits": self.credits,
                "mode": self.request.mode,
                # Edit output length is provider-chosen; fixed selected seconds
                # remain a reserved maximum, not a final charge.
                "settled": self.request.duration != -1 and self.request.mode != "edit",
            },
        }


async def get_wan30_quote(session, request: Wan30Request) -> Wan30Quote:
    # The exact active quality row is mandatory. Never fallback to a cheaper
    # base price after admin deactivates a quality.
    key = pricing_variant_key(request.model, resolution=request.resolution.lower())
    price = await repo.get_model_cost(session, key)
    base = await repo.get_model_cost(session, request.model)
    if (
        not price or not price.is_active
        or not base or not base.is_active
        or float(price.credits) <= 0
    ):
        raise ValueError("Тариф Wan для выбранного качества недоступен.")
    seconds = math.ceil(wan30_max_billable_seconds(request))
    cost = round(seconds * float(price.credits), 6)
    return Wan30Quote(request=request, billable_seconds=seconds,rate=float(price.credits),
                     credits=cost,resolution=request.resolution.lower())
