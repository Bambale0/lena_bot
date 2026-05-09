# api/kie_webhook.py
from __future__ import annotations

import json
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _nested_dicts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = _as_dict(payload.get("data"))
    info = _as_dict(payload.get("info"))
    nested_payload = _as_dict(payload.get("payload"))
    data_payload = _as_dict(data.get("payload"))
    data_result = _as_dict(data.get("resultJson"))
    data_info = _as_dict(data.get("info"))          # Veo3.1: data.info.resultUrls
    info_result = _as_dict(info.get("resultJson"))
    data_info_result = _as_dict(data_info.get("resultJson"))
    payload_result = _as_dict(payload.get("resultJson"))
    return [data, info, nested_payload, data_payload, data_result, data_info,
            info_result, data_info_result, payload_result]


def extract_task_id(payload: dict[str, Any]) -> str | None:
    for source in _nested_dicts(payload) + [payload]:
        for key in ("task_id", "taskId"):
            value = source.get(key)
            if value:
                return str(value)
    return None


def is_success(payload: dict[str, Any]) -> bool:
    code = payload.get("code")
    if code is not None and str(code) not in {"0", "200", "success", "SUCCESS"}:
        return False

    data = _as_dict(payload.get("data"))
    info = _as_dict(payload.get("info"))
    state = str(
        data.get("state")
        or data.get("status")
        or info.get("state")
        or info.get("status")
        or payload.get("state")
        or payload.get("status")
        or ""
    ).lower()

    if state in {"fail", "failed", "error"}:
        return False
    if state in {"success", "succeeded", "complete", "completed", "done"}:
        return True

    # Veo3.1 fallback: code=200 but fallbackFlag may indicate fallback was used
    # Still treat as success if code is 200 and there are result URLs
    if code is not None and str(code) == "200":
        if extract_result_urls(payload):
            return True

    # Some KIE callbacks only send code=200 + URLs.
    return bool(extract_result_urls(payload))


def extract_error(payload: dict[str, Any]) -> str:
    for source in _nested_dicts(payload) + [payload]:
        for key in ("failMsg", "error", "msg", "message"):
            value = source.get(key)
            if value:
                return str(value)
    return "KIE generation failed"


def extract_result_urls(payload: dict[str, Any]) -> list[str]:
    sources = _nested_dicts(payload) + [payload]
    candidates: list[Any] = []
    for source in sources:
        candidates.extend(
            [
                source.get("result_urls"),
                source.get("resultUrls"),
                source.get("video_urls"),
                source.get("videoUrls"),
                source.get("image_urls"),
                source.get("imageUrls"),
            ]
        )

    urls: list[str] = []
    for item in candidates:
        if isinstance(item, list):
            urls.extend(str(x) for x in item if x)
        elif isinstance(item, str) and item:
            urls.append(item)

    for source in sources:
        for key in ("video_url", "videoUrl", "image_url", "imageUrl", "url"):
            value = source.get(key)
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
