# api/comet_client.py
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.COMET_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.COMET_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


async def _request_with_retry(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict | None = None,
    retries: int = 3,
    backoff: float = 1.5,
) -> dict[str, Any]:
    client = get_client()
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client.request(method, path, json=json, data=data, files=files)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("CometAPI HTTP %s: %s (attempt %d)", e.response.status_code, path, attempt + 1)
            if e.response.status_code < 500:
                raise
            last_exc = e
        except httpx.RequestError as e:
            logger.warning("CometAPI request error: %s (attempt %d)", e, attempt + 1)
            last_exc = e
        await asyncio.sleep(backoff ** attempt)
    raise last_exc  # type: ignore[misc]


async def post(path: str, json: dict[str, Any]) -> dict[str, Any]:
    return await _request_with_retry("POST", path, json=json)


async def get(path: str) -> dict[str, Any]:
    return await _request_with_retry("GET", path)


async def post_multipart(
    path: str, data: dict[str, Any], files: dict
) -> dict[str, Any]:
    return await _request_with_retry("POST", path, data=data, files=files)
