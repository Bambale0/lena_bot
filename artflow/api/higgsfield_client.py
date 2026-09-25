"""Minimal async Higgsfield V2 client used by APIX Genjutsu.

The implementation mirrors the official server SDK contract without adding a
runtime SDK dependency: server-side Key auth, bounded retries and authenticated
status reconciliation via /requests/{request_id}/status.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_TERMINAL_FAILURES = {"failed", "nsfw", "cancelled", "canceled"}
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class HiggsfieldError(RuntimeError):
    """Provider error safe to propagate through APIX failure/refund handling."""


def _credentials() -> str:
    value = str(settings.HIGGSFIELD_CREDENTIALS or "").strip()
    key_id, sep, key_secret = value.partition(":")
    if not sep or not key_id.strip() or not key_secret.strip():
        raise HiggsfieldError(
            "Higgsfield credentials are not configured (expected KEY_ID:KEY_SECRET)"
        )
    return f"{key_id.strip()}:{key_secret.strip()}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Key {_credentials()}",
        "Content-Type": "application/json",
        "User-Agent": "apix-higgsfield/1.0",
    }


def _detail(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        raw = payload.get("detail") or payload.get("message") or payload.get("error")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list):
            messages = [
                str(item.get("msg") or item)
                for item in raw
                if isinstance(item, dict) or str(item).strip()
            ]
            if messages:
                return "; ".join(messages)[:1000]
    return fallback


async def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = str(settings.HIGGSFIELD_BASE_URL or "https://api.higgsfield.ai").rstrip("/")
    timeout_seconds = max(5.0, float(settings.HIGGSFIELD_TIMEOUT_SECONDS))
    retries = max(0, int(settings.HIGGSFIELD_MAX_RETRIES))
    backoff = max(0.1, float(settings.HIGGSFIELD_RETRY_BACKOFF_SECONDS))
    max_backoff = max(backoff, float(settings.HIGGSFIELD_RETRY_MAX_BACKOFF_SECONDS))

    timeout = httpx.Timeout(timeout_seconds)
    last_exc: Exception | None = None
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, headers=_headers()) as client:
        for attempt in range(retries + 1):
            try:
                response = await client.request(method, path, json=json_body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt >= retries:
                    raise HiggsfieldError(f"Higgsfield network error: {exc}") from exc
            else:
                payload: Any
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}

                if response.status_code < 400:
                    if not isinstance(payload, dict):
                        raise HiggsfieldError("Higgsfield returned a non-object response")
                    return payload

                if response.status_code not in _RETRYABLE_STATUS or attempt >= retries:
                    detail = _detail(payload, response.text[:500] or "provider request failed")
                    if response.status_code == 401:
                        raise HiggsfieldError("Higgsfield authentication failed")
                    if response.status_code in {402, 403}:
                        raise HiggsfieldError("Higgsfield account has insufficient credits or access")
                    if response.status_code == 422:
                        raise HiggsfieldError(f"Higgsfield validation failed: {detail}")
                    raise HiggsfieldError(
                        f"Higgsfield HTTP {response.status_code}: {detail}"
                    )

            if attempt < retries:
                delay = min(max_backoff, backoff * (2 ** attempt))
                logger.warning(
                    "Higgsfield transient error method=%s path=%s attempt=%s/%s retry_in=%.1fs",
                    method,
                    path,
                    attempt + 1,
                    retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)

    raise HiggsfieldError(f"Higgsfield request failed: {last_exc or 'unknown error'}")


async def submit(endpoint: str, input_payload: dict[str, Any]) -> str:
    path = "/" + str(endpoint or "").strip().lstrip("/")
    if path == "/":
        raise ValueError("Higgsfield endpoint is required")
    payload = await _request("POST", path, json_body=dict(input_payload))
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        raise HiggsfieldError("Higgsfield returned no request_id")
    logger.info(
        "Higgsfield task accepted endpoint=%s request_id=%s status=%s",
        endpoint,
        request_id,
        payload.get("status"),
    )
    return request_id


async def get_status(request_id: str) -> dict[str, Any]:
    safe_id = quote(str(request_id or "").strip(), safe="")
    if not safe_id:
        raise ValueError("Higgsfield request_id is required")
    return await _request("GET", f"/requests/{safe_id}/status")


def _video_url(payload: dict[str, Any]) -> str | None:
    video = payload.get("video")
    if isinstance(video, dict):
        url = video.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
    videos = payload.get("videos")
    if isinstance(videos, list):
        for item in videos:
            if isinstance(item, dict):
                url = item.get("url")
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    return url
    return None


async def poll_video_status(request_id: str) -> str | None:
    payload = await get_status(request_id)
    status = str(payload.get("status") or "").strip().lower()
    if status == "completed":
        url = _video_url(payload)
        if not url:
            raise HiggsfieldError("Higgsfield task completed without a video URL")
        return url
    if status in _TERMINAL_FAILURES:
        detail = _detail(payload, status or "provider task failed")
        raise HiggsfieldError(f"Higgsfield task {status}: {detail}")
    if status in {"queued", "in_progress", "processing", ""}:
        return None
    logger.warning("Unknown Higgsfield task state request_id=%s status=%r", request_id, status)
    return None
