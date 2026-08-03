from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import (
    local_upload_path_from_url,
    mirror_url,
    preview_public_image_url,
    public_url_is_available,
)
from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import FeedCard
from core.config import settings
from db import repository as repo
from db.session import get_session

router = APIRouter(tags=["web"])


COMPACT_FEED_KEYS = {
    "id",
    "type",
    "author",
    "likes",
    "remix_count",
    "shares",
    "aspect_ratio",
    "result_url",
    "result_urls",
    "preview_url",
    "preview_urls",
}


def _local_available_media(urls: list[str]) -> list[str]:
    return [url for url in urls if public_url_is_available(url)]


def _feed_payload(card, *, require_local: bool = True) -> dict | None:
    payload = FeedCard.from_feed_card(card).model_dump()
    result_urls = [url for url in payload.get("result_urls", []) if url]
    if payload.get("result_url") and payload["result_url"] not in result_urls:
        result_urls.insert(0, payload["result_url"])

    local_urls = _local_available_media(result_urls)
    if not local_urls:
        if require_local:
            return None
        local_urls = [url for url in result_urls if public_url_is_available(url)]
        if not local_urls:
            return None

    payload["result_urls"] = local_urls
    payload["result_url"] = local_urls[0]
    payload["preview_urls"] = [preview_public_image_url(url, max_size=384, quality=70) or url for url in local_urls]
    payload["preview_url"] = payload["preview_urls"][0] if payload["preview_urls"] else local_urls[0]
    payload["prompt"] = ""
    payload["prompt_visibility"] = "hidden"
    return payload


def _compact_feed_payload(payload: dict) -> dict:
    return {key: payload[key] for key in COMPACT_FEED_KEYS if key in payload}


def _generation_result_urls(generation) -> list[str]:
    urls: list[str] = []
    raw_urls = getattr(generation, "result_urls", None)
    if isinstance(raw_urls, str) and raw_urls.strip():
        try:
            parsed = json.loads(raw_urls)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, list):
            urls.extend(str(item).strip() for item in parsed if str(item or "").strip())
    elif isinstance(raw_urls, list):
        urls.extend(str(item).strip() for item in raw_urls if str(item or "").strip())

    primary = str(getattr(generation, "result_url", "") or "").strip()
    if primary and primary not in urls:
        urls.insert(0, primary)
    return list(dict.fromkeys(urls))


def _public_feed_link(generation_id: int) -> str:
    base = str(getattr(settings, "WEB_PUBLIC_URL", "") or "").strip().rstrip("/")
    return f"{base}/app?feed={int(generation_id)}" if base else ""


def _generation_value(value) -> str:
    return str(getattr(value, "value", value) or "").lower()


async def _feed_payloads(session: AsyncSession, source: str, limit: int, *, compact: bool = False) -> list[dict]:
    repo_limit = max(limit * 4, limit, 120)
    if source in {"top", "top_day"}:
        cards = await repo.get_top_day_generations(session, limit=repo_limit)
    else:
        cards = await repo.get_feed_generations(session, limit=repo_limit)
    payloads: list[dict] = []
    for card in cards:
        payload = _feed_payload(card)
        if payload is None:
            continue
        payloads.append(_compact_feed_payload(payload) if compact else payload)
        if len(payloads) >= limit:
            break
    if not payloads:
        for card in cards:
            payload = _feed_payload(card, require_local=False)
            if payload is None:
                continue
            payloads.append(_compact_feed_payload(payload) if compact else payload)
            if len(payloads) >= limit:
                break
    return payloads


@router.get("/feed")
async def feed(
    source: str = Query(default="feed", pattern="^(feed|recent|top|top_day)$"),
    limit: int = Query(default=10000, ge=1),
    compact: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return ok(await _feed_payloads(session, source, limit, compact=compact))


@router.get("/feed/top")
async def feed_top(
    limit: int = Query(default=10000, ge=1),
    compact: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return ok(await _feed_payloads(session, "top_day", limit, compact=compact))


@router.get("/feed/{generation_id}")
async def feed_item(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    card = await repo.get_feed_generation_card(session, generation_id, require_media=False)
    if card is None:
        return error_response(404, "Generation not found")
    payload = _feed_payload(card, require_local=False)
    if payload is None:
        return error_response(404, "Generation not found")
    return ok(payload)


@router.post("/feed/{generation_id}/like")
async def feed_like(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")
    if await repo.get_public_feed_generation(session, generation_id) is None:
        return error_response(404, "Generation not found")
    generation = await repo.like_feed_generation(session, generation_id)
    if generation is None:
        return error_response(404, "Generation not found")
    return ok({"id": generation.id, "likes": generation.likes_count})


@router.post("/feed/{generation_id}/share")
async def feed_share(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")
    if await repo.get_public_feed_generation(session, generation_id) is None:
        return error_response(404, "Generation not found")
    generation = await repo.increment_feed_share(session, generation_id)
    if generation is None:
        return error_response(404, "Generation not found")
    return ok({"id": generation.id, "shares": generation.shares_count})


@router.post("/feed/generations/{generation_id}/publish")
async def publish_own_generation_to_feed(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    """Publish any own ready image/video generation without exposing its prompt.

    This endpoint deliberately does not reject hidden-prompt generations or feed
    remixes. The public feed payload always hides prompts, so users can publish
    their own finished media while trend/remix source prompts stay protected.
    """
    if user is None:
        return error_response(401, "Authentication required")

    generation = await repo.get_generation_by_id(session, generation_id)
    if generation is None or getattr(generation, "user_id", None) != getattr(user, "id", None):
        return error_response(404, "Generation not found")

    gen_type = _generation_value(getattr(generation, "gen_type", ""))
    if gen_type not in {"image", "video"}:
        return error_response(422, "Only image and video works can be published")

    if _generation_value(getattr(generation, "status", "")) not in {"done", "completed"}:
        return error_response(422, "Generation is not ready yet")

    original_urls = _generation_result_urls(generation)
    if not original_urls:
        return error_response(422, "Generation has no result media")

    clean_urls: list[str] = []
    for url in original_urls:
        mirrored = await mirror_url(url, subdir="feed")
        clean_urls.append(mirrored or url)

    generation.is_public_feed = True
    generation.result_url = clean_urls[0]
    generation.result_urls = json.dumps(clean_urls, ensure_ascii=False)
    await session.commit()
    await session.refresh(generation)

    return ok({
        "id": generation.id,
        "is_public_feed": True,
        "link": _public_feed_link(generation.id),
    })
