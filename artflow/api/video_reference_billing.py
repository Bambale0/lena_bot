"""Measure owned video references before quoting or charging a video task."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from api.media_gateway import MediaKind, probe_local_media
from api.public_files import local_upload_path_from_url


@dataclass(frozen=True)
class VideoSeconds:
    output: int
    references: int
    billable: int
    reference_count: int


def reference_video_urls(normalized: dict[str, Any]) -> list[str]:
    raw = normalized.get("reference_video_url")
    values = list(raw) if isinstance(raw, list) else [raw] if raw else []
    for item in normalized.get("audio_ids") or []:
        if isinstance(item, str) and item.startswith("__apix_seedance25:video_ref="):
            values.append(item.partition("=")[2])
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


async def measured_video_seconds(normalized: dict[str, Any], *, per_second: bool) -> VideoSeconds:
    output = int(normalized["duration"])
    if output <= 0:
        raise ValueError("Output video duration must be positive before pricing")
    urls = reference_video_urls(normalized)
    if not urls:
        return VideoSeconds(output=output, references=0, billable=output, reference_count=len(urls))

    duration = 0.0
    for url in urls:
        path = local_upload_path_from_url(url)
        if path is None:
            raise ValueError("Загрузи видеореференс файлом, чтобы проверить его длительность до оплаты")
        probe = await probe_local_media(path, MediaKind.VIDEO)
        seconds = float(probe.duration_seconds or 0)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Не удалось определить длительность видеореференса")
        duration += seconds
    references = math.ceil(duration)
    return VideoSeconds(
        output=output,
        references=references,
        billable=output + references if per_second else output,
        reference_count=len(urls),
    )
