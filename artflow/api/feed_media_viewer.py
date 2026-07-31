"""WebP-only media delivery for the Mini App public feed."""
from __future__ import annotations

from typing import Any

from api.public_files import local_upload_path_from_url, mirror_url, preview_public_image_url

FEED_TILE_MAX_SIZE = 480
FEED_TILE_QUALITY = 72
FEED_VIEW_MAX_SIZE = 1280
FEED_VIEW_QUALITY = 84
FEED_CACHE_CONTROL = "public, max-age=31536000, immutable"


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
    mirrored_url = await mirror_url(source_url, subdir="feed")
    local_source = mirrored_url or source_url
    webp_url = preview_public_image_url(
        local_source,
        max_size=max_size,
        quality=quality,
    )
    webp_path = local_upload_path_from_url(webp_url)

    if webp_path is None or not webp_path.exists() or not webp_path.is_file():
        raise routes.HTTPException(status_code=502, detail="Не удалось подготовить изображение")

    return routes.Response(
        content=webp_path.read_bytes(),
        media_type="image/webp",
        headers={
            "Cache-Control": FEED_CACHE_CONTROL,
            "Content-Disposition": "inline",
        },
    )


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
