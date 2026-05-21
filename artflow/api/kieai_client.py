# api/kieai_client.py
"""
HTTP-клиент для api.kie.ai — единый провайдер всех моделей (кроме Midjourney).

Эндпоинты:
  POST /api/v1/jobs/createTask          — создать задачу (все модели кроме Veo)
  GET  /api/v1/jobs/recordInfo?taskId=  — статус задачи (все модели кроме Veo)
  POST /api/v1/veo/generate             — создать Veo-задачу
  GET  /api/v1/veo/record-info?taskId=  — статус Veo-задачи
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.kie.ai"
_UPLOAD_BASE_URL = "https://kieai.redpandaai.co"
_client: httpx.AsyncClient | None = None
_upload_client: httpx.AsyncClient | None = None


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


def get_upload_client() -> httpx.AsyncClient:
    global _upload_client
    if _upload_client is None or _upload_client.is_closed:
        _upload_client = httpx.AsyncClient(
            base_url=_UPLOAD_BASE_URL,
            headers={"Authorization": f"Bearer {settings.KIE_AI_KEY}"},
            timeout=60.0,
        )
    return _upload_client


async def close_client() -> None:
    global _client, _upload_client
    if _client and not _client.is_closed:
        await _client.aclose()
    if _upload_client and not _upload_client.is_closed:
        await _upload_client.aclose()


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


def _ensure_dict(resp: Any) -> dict[str, Any]:
    """Ensure response is a dict, return empty dict if None."""
    if resp is None:
        return {}
    if isinstance(resp, dict):
        return resp
    return {}


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


def _extract_upload_url(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("downloadUrl", "fileUrl", "url", "download_url", "file_url"):
            url = value.get(key)
            if isinstance(url, str) and url.startswith("http"):
                return url
        for nested in value.values():
            url = _extract_upload_url(nested)
            if url:
                return url
    if isinstance(value, list):
        for item in value:
            url = _extract_upload_url(item)
            if url:
                return url
    return None


async def upload_file_stream(
    data: bytes,
    *,
    filename: str,
    content_type: str,
    upload_path: str = "images/apix-refs",
) -> str:
    client = get_upload_client()
    files = {"file": (filename, data, content_type)}
    form = {"uploadPath": upload_path}
    for attempt in range(3):
        try:
            resp = await client.post("/api/file-stream-upload", data=form, files=files)
            resp.raise_for_status()
            payload = resp.json()
            url = _extract_upload_url(payload)
            if not url:
                raise RuntimeError(f"empty upload url in response: {payload!r}")
            return url
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            logger.warning("kie.ai file upload HTTP %s (attempt %d)", e.response.status_code, attempt + 1)
        except (httpx.RequestError, RuntimeError, ValueError) as e:
            logger.warning("kie.ai file upload error: %s (attempt %d)", e, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError("kie.ai: max retries exceeded for file upload")


# ── Public API ────────────────────────────────────────────────────────────────

async def create_task(
    payload: dict[str, Any],
    callback_url: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/jobs/createTask — для всех моделей кроме Veo."""
    request_payload = dict(payload)
    if callback_url:
        request_payload["callBackUrl"] = callback_url
    return await _retry_post("/api/v1/jobs/createTask", request_payload)


async def get_task_status(task_id: str) -> dict[str, Any]:
    """GET /api/v1/jobs/recordInfo?taskId= — универсальный статус."""
    return await _retry_get("/api/v1/jobs/recordInfo", params={"taskId": task_id})


async def create_veo_task(payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/v1/veo/generate — только для Veo 3."""
    return await _retry_post("/api/v1/veo/generate", payload)


async def get_veo_status(task_id: str) -> dict[str, Any]:
    """GET /api/v1/veo/record-info?taskId= — статус Veo-задачи."""
    return await _retry_get("/api/v1/veo/record-info", params={"taskId": task_id})



# ── Veo 3.1 4K enhancement ──────────────────────────────────────────────────

async def create_veo_4k_task(
    task_id: str,
    index: int = 0,
    callback_url: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/veo/4k/generate — запросить 4K-улучшение видео."""
    payload: dict[str, Any] = {"taskId": task_id, "index": index}
    if callback_url:
        payload["callBackUrl"] = callback_url
    return await _retry_post("/api/v1/veo/4k/generate", payload)


async def get_veo_4k_status(task_id: str) -> dict[str, Any]:
    """GET /api/v1/veo/4k/record-info?taskId= — статус 4K-улучшения."""
    return await _retry_get("/api/v1/veo/4k/record-info", params={"taskId": task_id})


# Aliases for backward-compat with old Wan 2.7 Pro calls

async def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await _retry_post(path, payload)


async def get(path: str) -> dict[str, Any]:
    return await _retry_get(path)
