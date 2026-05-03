# api/aivideoapi_client.py
"""
HTTP-клиент для api.aivideoapi.ai (HappyHorse).
Отдельный провайдер, не CometAPI.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.aivideoapi.ai"
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.AIVIDEOAPI_KEY}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


async def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = get_client()
    for attempt in range(3):
        try:
            resp = await client.post(path, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            logger.warning("aivideoapi HTTP %s (attempt %d)", e.response.status_code, attempt + 1)
        except httpx.RequestError as e:
            logger.warning("aivideoapi request error: %s (attempt %d)", e, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError("aivideoapi: max retries exceeded")


async def get(path: str) -> dict[str, Any]:
    client = get_client()
    for attempt in range(3):
        try:
            resp = await client.get(path)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
        except httpx.RequestError as e:
            logger.warning("aivideoapi get error: %s", e)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError("aivideoapi: max retries exceeded")
