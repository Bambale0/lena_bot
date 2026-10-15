"""Allowlisted callback diagnostics: never log provider bodies or media URLs."""
from __future__ import annotations

import logging
import re

_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z", re.ASCII)


def safe_identifier(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return "unknown"
    text = str(value)
    return text if _IDENTIFIER.fullmatch(text) and "://" not in text else "invalid"


def callback_anomaly(
    logger: logging.Logger, provider: str, reason: str, *, task_id: object = None,
    status: object = None, error: Exception | None = None,
) -> None:
    metadata = {
        "callback_provider": safe_identifier(provider),
        "callback_reason": safe_identifier(reason),
        "callback_task_id": safe_identifier(task_id),
        "callback_status": safe_identifier(status),
        "callback_error_type": type(error).__name__ if error is not None else "none",
    }
    logger.warning(
        "provider_callback_anomaly provider=%s reason=%s task_id=%s status=%s error_type=%s",
        *metadata.values(), extra=metadata,
    )
