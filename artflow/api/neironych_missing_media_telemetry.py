"""Bounded process-local suppression for repeated supplier completed/no-media logs.

This cache is observability-only: never used for payment, refund, status, or
provider retry decisions. Multiple workers may emit one message each.
"""
from __future__ import annotations

from time import monotonic

LOG_INTERVAL_SECONDS = 15 * 60
MAX_TRACKED_GENERATIONS = 4096
_last_logged: dict[int, float] = {}


def should_log_missing_media(generation_id: int, *, now: float | None = None) -> bool:
    """Return True once per generation per interval, with bounded cache growth."""
    moment = monotonic() if now is None else now
    prev = _last_logged.get(generation_id)
    if prev is not None and moment >= prev and moment - prev < LOG_INTERVAL_SECONDS:
        return False
    if len(_last_logged) >= MAX_TRACKED_GENERATIONS:
        # No tracking record is authoritative; keep only recent records.
        cutoff = moment - LOG_INTERVAL_SECONDS
        for key, logged_at in list(_last_logged.items()):
            if logged_at < cutoff:
                _last_logged.pop(key, None)
        if len(_last_logged) >= MAX_TRACKED_GENERATIONS:
            _last_logged.pop(next(iter(_last_logged)))
    _last_logged[generation_id] = moment
    return True
