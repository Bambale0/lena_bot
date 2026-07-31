"""Lightweight media delivery for the Mini App public feed."""
from __future__ import annotations

from typing import Any

FEED_TILE_MAX_SIZE = 480
FEED_TILE_QUALITY = 72
FEED_VIEW_MAX_SIZE = 1280
FEED_VIEW_QUALITY = 84


def _is_non_image_media(gen_type: Any) -> bool:
    value = getattr(gen_type, "value", gen_type)
    return str(value or "").lower() in {"video", "music", "audio"}


def install_feed_media_viewer(routes: Any) -> None:
    """Install small feed thumbnails and an on-demand compressed viewer route."""
    if getattr(routes, "_feed_media_viewer_installed", False):
        return

    preview_public_image_url = routes.preview_public_image_url

    def feed_tile_url(url: str | None, gen_type: Any) -> str | None:
        if not url or _is_non_image_media(gen_type):
            return url
        return preview_public_image_url(
            url,
            max_size=FEED_TILE_MAX_SIZE,
            quality=FEED_TILE_QUALITY,
        ) or url

    routes._preview_media_url = feed_tile_url

    @routes.router.get("/feed/{generation_id}/display")
    async def compressed_feed_display(
        generation_id: int,
        index: int = routes.Query(0, ge=0, le=3),
        _user=routes.Depends(routes.get_miniapp_user),
        session=routes.Depends(routes.get_session),
    ) -> dict[str, str]:
        result = await session.execute(
            routes.select(routes.Generation).where(
                routes.Generation.id == generation_id,
                routes.Generation.is_public_feed.is_(True),
            )
        )
        generation = result.scalar_one_or_none()
        if generation is None:
            raise routes.HTTPException(status_code=404, detail="Публикация не найдена")

        urls = routes._generation_result_urls(generation)
        if not urls:
            primary = routes._generation_primary_result_url(generation)
            urls = [primary] if primary else []
        if index >= len(urls):
            raise routes.HTTPException(status_code=404, detail="Изображение не найдено")

        source_url = urls[index]
        gen_type = getattr(generation, "gen_type", "image")
        if _is_non_image_media(gen_type):
            return {"url": source_url}

        display_url = preview_public_image_url(
            source_url,
            max_size=FEED_VIEW_MAX_SIZE,
            quality=FEED_VIEW_QUALITY,
        ) or feed_tile_url(source_url, gen_type) or source_url
        return {"url": display_url}

    routes._feed_media_viewer_installed = True
