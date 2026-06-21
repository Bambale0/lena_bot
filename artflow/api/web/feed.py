from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import (
    local_upload_path_from_url,
    preview_public_image_url,
    public_url_is_available,
)
from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import FeedCard
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
    return [
        url
        for url in urls
        if local_upload_path_from_url(url) is not None and public_url_is_available(url)
    ]


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


async def _feed_payloads(session: AsyncSession, source: str, limit: int, *, compact: bool = False) -> list[dict]:
    repo_limit = min(max(limit * 4, limit, 120), 1000)
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
    limit: int = Query(default=40, ge=1, le=300),
    compact: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return ok(await _feed_payloads(session, source, limit, compact=compact))


@router.get("/feed/top")
async def feed_top(
    limit: int = Query(default=40, ge=1, le=300),
    compact: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return ok(await _feed_payloads(session, "top_day", limit, compact=compact))


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
