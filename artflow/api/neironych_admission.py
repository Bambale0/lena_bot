"""Verified native pre-admission rejection, not a generic 503 retry policy.

Contract: Bambale0/ooo@50963d35033497d5014b830bf3a1eda263d72402,
app/inference/router.py:inference and service.py:reserve. Reserve checks
idempotency before capital admission. Admission errors are FastAPI detail-only
objects with a diagnostic UUID; errors after an admitted generation use an
error envelope and generation request_id. Never infer rejection from 404 polls.
"""
from __future__ import annotations

from uuid import UUID

import httpx


def pre_admission_unavailable_trace(response: httpx.Response) -> str | None:
    """Return the safe trace UUID only for the exact verified admission shape."""
    if response.status_code != 503:
        return None
    if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        return None
    try:
        request = response.request
    except RuntimeError:
        return None
    if request.method != "POST" or request.url.path not in {
        "/v1/videos/generations", "/v1/chat/completions",
    }:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    # Extra fields could indicate accepted work or an unverified new contract.
    if body != {"detail": "provider_temporarily_unavailable"}:
        return None
    trace = response.headers.get("x-request-id", "")
    try:
        canonical = str(UUID(trace))
    except ValueError:
        return None
    return canonical if canonical == trace.lower() else None
