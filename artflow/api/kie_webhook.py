# api/kie_webhook.py
from __future__ import annotations

from typing import Any


def extract_task_id(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") or {}
    info = payload.get("info") or {}

    return (
        str(data.get("task_id"))
        if data.get("task_id")
        else str(data.get("taskId"))
        if data.get("taskId")
        else str(payload.get("task_id"))
        if payload.get("task_id")
        else str(payload.get("taskId"))
        if payload.get("taskId")
        else str(info.get("task_id"))
        if info.get("task_id")
        else str(info.get("taskId"))
        if info.get("taskId")
        else None
    )


def is_success(payload: dict[str, Any]) -> bool:
    code = payload.get("code")
    if code is not None and str(code) not in {"0", "200", "success", "SUCCESS"}:
        return False

    data = payload.get("data") or {}
    state = str(
        data.get("state")
        or data.get("status")
        or payload.get("state")
        or payload.get("status")
        or ""
    ).lower()

    if state in {"fail", "failed", "error"}:
        return False
    if state in {"success", "succeeded", "complete", "completed", "done"}:
        return True

    # Some KIE callbacks only send code=200 + URLs.
    return bool(extract_result_urls(payload))


def extract_error(payload: dict[str, Any]) -> str:
    data = payload.get("data") or {}
    return str(
        data.get("failMsg")
        or data.get("error")
        or data.get("msg")
        or payload.get("msg")
        or payload.get("error")
        or "KIE generation failed"
    )


def extract_result_urls(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data") or {}
    info = payload.get("info") or {}

    candidates: list[Any] = [
        data.get("result_urls"),
        data.get("resultUrls"),
        data.get("result_urls".replace("_", "")),
        info.get("result_urls"),
        info.get("resultUrls"),
        payload.get("result_urls"),
        payload.get("resultUrls"),
    ]

    urls: list[str] = []
    for item in candidates:
        if isinstance(item, list):
            urls.extend(str(x) for x in item if x)
        elif isinstance(item, str) and item:
            urls.append(item)

    for key in ("video_url", "videoUrl", "image_url", "imageUrl", "url"):
        value = data.get(key) or info.get(key) or payload.get(key)
        if isinstance(value, str) and value:
            urls.append(value)

    # Keep order, remove duplicates.
    seen = set()
    deduped = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped
