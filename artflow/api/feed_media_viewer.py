"""Stable WebP-only media delivery for the Mini App public feed."""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw

from api.public_files import local_upload_path_from_url, mirror_url, preview_public_image_url

FEED_TILE_MAX_SIZE = 480
FEED_TILE_QUALITY = 72
FEED_VIEW_MAX_SIZE = 1280
FEED_VIEW_QUALITY = 84
FEED_CACHE_CONTROL = "public, max-age=31536000, immutable"
FEED_RETRY_CACHE_CONTROL = "no-store, max-age=0"
FEED_RENDER_CONCURRENCY = 3

logger = logging.getLogger(__name__)
_render_slots = asyncio.Semaphore(FEED_RENDER_CONCURRENCY)


def _is_non_image_media(gen_type: Any) -> bool:
    value = getattr(gen_type, "value", gen_type)
    return str(value or "").lower() in {"video", "music", "audio"}


def _generation_urls(routes: Any, generation: Any) -> list[str]:
    urls = [url for url in routes._generation_result_urls(generation) if url]
    if not urls:
        primary = routes._generation_primary_result_url(generation)
        if primary:
            urls.append(primary)
    return urls[:4]


@lru_cache(maxsize=2)
def _placeholder_webp(kind: str) -> bytes:
    """Return a tiny valid WebP so one failed source never removes a feed card."""
    width, height = ((480, 600) if kind == "tile" else (720, 900))
    image = Image.new("RGB", (width, height), (20, 23, 29))
    draw = ImageDraw.Draw(image)
    cx, cy = width // 2, height // 2
    radius = max(22, width // 14)
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        outline=(92, 105, 120),
        width=max(3, width // 160),
    )
    draw.line(
        (cx - radius // 2, cy + radius // 3, cx, cy - radius // 4, cx + radius // 2, cy + radius // 3),
        fill=(92, 105, 120),
        width=max(3, width // 160),
    )
    buffer = BytesIO()
    image.save(buffer, format="WEBP", quality=58, method=4)
    return buffer.getvalue()


def _image_response(content: bytes, *, cache_control: str, placeholder: bool = False):
    headers = {
        "Cache-Control": cache_control,
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
    }
    if placeholder:
        headers["X-Feed-Preview"] = "placeholder"
    return content, headers


async def _render_webp(
    routes: Any,
    generation: Any,
    *,
    index: int,
    max_size: int,
    quality: int,
):
    urls = _generation_urls(routes, generation)
    if index >= len(urls):
        raise routes.HTTPException(status_code=404, detail="Изображение не найдено")

    source_url = urls[index]
    placeholder_kind = "tile" if max_size <= FEED_TILE_MAX_SIZE else "viewer"

    try:
        # Pillow conversion and disk reads are blocking. Limiting and moving them
        # off the event loop keeps the API responsive when many cards enter the
        # viewport at once.
        async with _render_slots:
            local_source = source_url
            local_path = local_upload_path_from_url(local_source)
            if local_path is None or not local_path.exists() or not local_path.is_file():
                mirrored_url = await asyncio.wait_for(
                    mirror_url(source_url, subdir="feed"),
                    timeout=10,
                )
                local_source = mirrored_url or source_url

            webp_url = await asyncio.to_thread(
                preview_public_image_url,
                local_source,
                max_size=max_size,
                quality=quality,
            )
            webp_path = local_upload_path_from_url(webp_url)
            if webp_path is None or not webp_path.exists() or not webp_path.is_file():
                raise FileNotFoundError("feed WebP was not created")

            content = await asyncio.to_thread(webp_path.read_bytes)
            payload, headers = _image_response(content, cache_control=FEED_CACHE_CONTROL)
            return routes.Response(content=payload, media_type="image/webp", headers=headers)
    except Exception as exc:
        # Do not return a broken image response: the frontend used to hide the
        # whole card after one onError event. A non-cacheable WebP placeholder
        # keeps layout stable and allows the next app opening to retry.
        logger.warning(
            "Feed WebP fallback generation=%s index=%s size=%s: %s",
            getattr(generation, "id", None),
            index,
            max_size,
            exc,
        )
        content = _placeholder_webp(placeholder_kind)
        payload, headers = _image_response(
            content,
            cache_control=FEED_RETRY_CACHE_CONTROL,
            placeholder=True,
        )
        return routes.Response(content=payload, media_type="image/webp", headers=headers)


def install_feed_media_viewer(routes: Any) -> None:
    """Expose only compressed WebP URLs for image posts in the public feed."""
    if getattr(routes, "_feed_media_viewer_installed", False):
        return

    original_feed_card_out = routes._feed_card_out

    def webp_feed_card_out(card: Any, user: Any) -> dict:
        payload = original_feed_card_out(card, user)
        generation = card.generation
        gen_type = getattr(generation, "gen_type", "image")
        if _is_non_image_media(gen_type):
            return payload

        source_urls = _generation_urls(routes, generation)
        preview_urls = [
            f"/api/v1/feed/{generation.id}/preview.webp?index={index}"
            for index in range(len(source_urls))
        ]
        payload["preview_url"] = preview_urls[0] if preview_urls else ""
        payload["preview_urls"] = preview_urls

        # Never expose heavyweight PNG/JPEG originals to the Mini App feed.
        payload["result_url"] = ""
        payload["result_urls"] = []
        return payload

    routes._feed_card_out = webp_feed_card_out

    @routes.router.get("/feed/{generation_id}/preview.webp")
    async def feed_preview_webp(
        generation_id: int,
        index: int = routes.Query(0, ge=0, le=3),
        session=routes.Depends(routes.get_session),
    ):
        result = await session.execute(
            routes.select(routes.Generation).where(
                routes.Generation.id == generation_id,
                routes.Generation.is_public_feed.is_(True),
            )
        )
        generation = result.scalar_one_or_none()
        if generation is None:
            raise routes.HTTPException(status_code=404, detail="Публикация не найдена")
        if _is_non_image_media(getattr(generation, "gen_type", "image")):
            raise routes.HTTPException(status_code=415, detail="Это не изображение")
        return await _render_webp(
            routes,
            generation,
            index=index,
            max_size=FEED_TILE_MAX_SIZE,
            quality=FEED_TILE_QUALITY,
        )

    @routes.router.get("/feed/{generation_id}/display.webp")
    async def feed_display_webp(
        generation_id: int,
        index: int = routes.Query(0, ge=0, le=3),
        session=routes.Depends(routes.get_session),
    ):
        result = await session.execute(
            routes.select(routes.Generation).where(
                routes.Generation.id == generation_id,
                routes.Generation.is_public_feed.is_(True),
            )
        )
        generation = result.scalar_one_or_none()
        if generation is None:
            raise routes.HTTPException(status_code=404, detail="Публикация не найдена")
        if _is_non_image_media(getattr(generation, "gen_type", "image")):
            raise routes.HTTPException(status_code=415, detail="Это не изображение")
        return await _render_webp(
            routes,
            generation,
            index=index,
            max_size=FEED_VIEW_MAX_SIZE,
            quality=FEED_VIEW_QUALITY,
        )

    routes._feed_media_viewer_installed = True
