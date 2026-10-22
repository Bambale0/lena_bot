"""Measured Kling 4 checkout and bounded staging; DB tariffs are authoritative."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from decimal import Decimal

from api import kieai_client
from api.kling4_contract import Kling4Input, build_kling4_payload, media_roles
from api.media_gateway import MediaKind, probe_local_media
from api.public_files import UPLOAD_ROOT, local_upload_path_from_url
from core.model_pricing import pricing_variant_key
from db import repository as repo


@dataclass(frozen=True)
class Kling4Quote:
    credits: float
    rate: float
    billable_seconds: int
    reference_seconds: float
    reference_count: int
    tariff_key: str


def tariff_key(model: str, resolution: str, has_video: bool) -> str:
    key = pricing_variant_key(model, resolution=resolution)
    return key + ("__video_input=true" if has_video else "")


async def validate_media(data: Kling4Input, *, user_id: int | None = None) -> list[float]:
    lengths = []
    all_video_lengths = []
    for url, kind, element in media_roles(data):
        path = local_upload_path_from_url(url)
        if path is None or not path.is_file():
            raise ValueError("Сначала загрузи материалы в APIX: проверим их до оплаты")
        if user_id is not None and not path.resolve().is_relative_to(
            (UPLOAD_ROOT / "kling4" / str(user_id)).resolve()
        ):
            raise ValueError(
                "Материал не принадлежит этому аккаунту. Загрузи его через форму Kling 4"
            )
        probe = await probe_local_media(path, MediaKind(kind))
        if kind == "image":
            width, height = probe.width or 0, probe.height or 0
            # Product decoding budget is deliberately stricter than KIE's 65536px.
            if not (
                300 <= width <= 65536
                and 300 <= height <= 65536
                and width * height <= 40_000_000
                and 0.4 <= width / height <= 2.5
            ):
                raise ValueError(
                    "Изображение: стороны от 300 px, пропорции 0.4–2.5; лимит APIX 40 Мп"
                )
        if kind in {"video", "audio"}:
            seconds = float(probe.duration_seconds or 0)
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Не удалось прочитать длительность материала")
            if kind == "audio" and not 5 <= seconds <= 30:
                raise ValueError(
                    "Голосовой референс: 5–30 секунд отчётливой речи (проверено на KIE)"
                )
            if kind == "video":
                if not ((3 <= seconds <= 8) if element else (2 <= seconds <= 30)):
                    raise ValueError("Видео: 2–30 сек; видео персонажа: 3–8 сек")
                if element and min(probe.width or 0, probe.height or 0) < 700:
                    raise ValueError("Видео персонажа: короткая сторона от 700 px")
                all_video_lengths.append(seconds)
                if not element:
                    lengths.append(seconds)
    if sum(all_video_lengths) > 30:
        raise ValueError("Общая длительность входных видео не должна превышать 30 сек")
    return lengths


async def get_kling4_quote(
    session, model: str, prompt: str, data: Kling4Input, *, user_id: int | None = None
) -> Kling4Quote:
    build_kling4_payload(model, prompt, data)
    async with asyncio.timeout(45):
        lengths = await validate_media(data, user_id=user_id)
    has_video = bool(data.video_urls)
    # Live KIE tasks confirm elements do not enter the video-input tariff.
    # Both element-only and mixed input were measured on 2026-10-22.
    key = tariff_key(model, data.resolution, has_video)
    row = await repo.get_model_cost(session, key)
    if not row or not bool(getattr(row, "is_active", True)):
        raise ValueError("Тариф Kling 4 отключён или не настроен администратором")
    rate = Decimal(str(row.credits))
    if not rate.is_finite() or rate <= 0:
        raise ValueError("Некорректный тариф Kling 4")
    seconds_in = sum(lengths) if has_video else 0
    # Conservative whole-second quote; retain measured fractional input in history.
    billed = (
        data.duration + math.ceil(max(seconds_in, data.duration)) if has_video else data.duration
    )
    return Kling4Quote(float(rate * billed), float(rate), billed, seconds_in, len(lengths), key)


async def stage_kling4_payload(model: str, prompt: str, data: Kling4Input) -> dict:
    payload = build_kling4_payload(model, prompt, data)
    # Upload each source once while preserving distinct roles and frame order.
    staged = {}
    async with asyncio.timeout(90):
        for url, kind, _element in media_roles(data):
            if url in staged:
                continue
            path = local_upload_path_from_url(url)
            if path is None or not path.is_file():
                raise ValueError("Исходный материал недоступен; загрузи его снова")
            import mimetypes

            staged[url] = await kieai_client.upload_file_stream(
                path.read_bytes(),
                filename=path.name,
                content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                upload_path=f"{kind}s/apix-kling4",
            )
            if not staged[url] or not str(staged[url]).startswith("https://"):
                raise ValueError("KIE не подтвердил загрузку материала")

    def replace(value):
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        return staged.get(value, value) if isinstance(value, str) else value

    # Only media fields are replaced. A prompt containing a URL remains verbatim.
    payload["input"] = {
        key: value if key == "prompt" else replace(value) for key, value in payload["input"].items()
    }
    return payload
