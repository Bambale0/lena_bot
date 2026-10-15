"""Neironych Wan POST transport, shared single-submit safety invariant.

Only route here after live model availability + provider contract validation.
No POST retry, even for HTTP 503 or a broken response body.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from api.neironych_seedance import (
    NeironychPreSubmitFailure,
    NeironychSubmissionUnknown,
    _definite_rejection,
    _safe_error,
)


async def post_wan30_neironych(
    *,
    client: httpx.AsyncClient,
    api_key: str,
    payload: dict[str, Any],
    idempotency_key: str,
    client_request_id: str,
    before_submit: Callable[[str, str], Awaitable[None]],
) -> str:
    if not str(api_key or "").strip():
        raise ValueError("Missing Neironych key")
    idem = str(idempotency_key or "").strip()
    if not 8 <= len(idem) <= 160:
        raise ValueError("Invalid Neironych Idempotency-Key")
    rid = str(uuid.UUID(client_request_id))
    if not callable(before_submit):
        raise ValueError("Durable before_submit is required for Neironych Wan")
    if not isinstance(payload, dict) or not isinstance(payload.get("model"), str) or not payload["model"]:
        raise ValueError("Verified Wan provider model is required")
    encoded = json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    try:
        await before_submit(idem, digest)
    except NeironychSubmissionUnknown:
        raise
    except Exception as exc:
        raise NeironychPreSubmitFailure(rid, idem) from exc

    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Idempotency-Key": idem,
        "X-Client-Request-Id": rid,
    }
    try:
        result = await client.post(
            "/v1/videos/generations",
            json=payload, headers=headers, follow_redirects=False,
        )
        if not result.is_success:
            if _definite_rejection(result):
                raise _safe_error(result)
            raise NeironychSubmissionUnknown(rid, idem)
        parsed = result.json()
        if not isinstance(parsed, dict):
            raise ValueError("Invalid response object")
        provider_id=parsed.get("request_id")
        if not isinstance(provider_id,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,160}",provider_id):
            raise ValueError("Provider request_id missing")
        if parsed.get("client_request_id",rid) != rid:
            raise ValueError("Client request echo mismatch")
        return provider_id
    except Exception as exc:
        if isinstance(exc, NeironychSubmissionUnknown):
            raise
        from api.neironych_seedance import NeironychSeedanceError
        if isinstance(exc, NeironychSeedanceError):
            raise
        raise NeironychSubmissionUnknown(rid,idem) from exc
