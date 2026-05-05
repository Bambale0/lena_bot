# api/kieai_client.py
"""
HTTP-клиент для api.kie.ai — единый провайдер всех моделей (кроме Midjourney).

Эндпоинты:
  POST /api/v1/jobs/createTask          — создать задачу (все модели кроме Veo)
  GET  /api/v1/jobs/recordInfo?taskId=  — статус задачи (все модели кроме Veo)
  POST /api/v1/veo/generate             — создать Veo-задачу
  GET  /api/v1/veo/video/{videoId}      — статус Veo-задачи
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.kie.ai"
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.KIE_AI_KEY}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


async def _retry_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = get_client()
    for attempt in range(3):
        try:
            resp = await client.post(path, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            logger.warning("kie.ai POST %s HTTP %s (attempt %d)", path, e.response.status_code, attempt + 1)
        except httpx.RequestError as e:
            logger.warning("kie.ai POST %s error: %s (attempt %d)", path, e, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError(f"kie.ai: max retries exceeded for POST {path}")


async def _retry_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    client = get_client()
    for attempt in range(3):
        try:
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            logger.warning("kie.ai GET %s HTTP %s (attempt %d)", path, e.response.status_code, attempt + 1)
        except httpx.RequestError as e:
            logger.warning("kie.ai GET %s error: %s (attempt %d)", path, e, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError(f"kie.ai: max retries exceeded for GET {path}")


# ── Public API ────────────────────────────────────────────────────────────────

async def create_task(payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/v1/jobs/createTask — для всех моделей кроме Veo."""
    return await _retry_post("/api/v1/jobs/createTask", payload)


async def get_task_status(task_id: str) -> dict[str, Any]:
    """GET /api/v1/jobs/recordInfo?taskId= — универсальный статус."""
    return await _retry_get("/api/v1/jobs/recordInfo", params={"taskId": task_id})


async def create_veo_task(payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/v1/veo/generate — только для Veo 3."""
    return await _retry_post("/api/v1/veo/generate", payload)


async def get_veo_status(video_id: str) -> dict[str, Any]:
    """GET /api/v1/veo/video/{videoId} — статус Veo-задачи."""
    return await _retry_get(f"/api/v1/veo/video/{video_id}")


# Aliases for backward-compat with old Wan 2.7 Pro calls
async def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await _retry_post(path, payload)


async def get(path: str) -> dict[str, Any]:
    return await _retry_get(path)
