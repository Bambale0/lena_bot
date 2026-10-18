"""Verify native admission receipts; a bare HTTP 503 never proves no paid work."""
from __future__ import annotations

import hashlib
import hmac

import httpx


def rejected_before_acceptance(
    response: httpx.Response, *, client_request_id: str, idempotency_key: str,
) -> bool:
    """Trust only the provider's versioned, invocation-bound rollback receipt.

    The native gateway emits this after rolling back a typed rejection and
    durably fencing the logical key against any overlapping/later acceptance. Other 5xx responses may follow an
    accepted POST and remain ambiguous, including responses from older servers.
    """
    if (
        response.status_code != 503
        or response.headers.get("X-Submission-State") != "not-accepted-v1"
        or not client_request_id or not idempotency_key
        or not hmac.compare_digest(response.headers.get("X-Client-Request-Id", "").encode(), client_request_id.encode())
        or not hmac.compare_digest(
            response.headers.get("X-Idempotency-Key-Sha256", "").encode(),
            hashlib.sha256(idempotency_key.encode()).hexdigest().encode(),
        )
    ):
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return body == {"detail": "provider_temporarily_unavailable"}
