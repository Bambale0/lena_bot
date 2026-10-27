"""Settle explicit image-provider HTTP 5xx responses once, by persisted task ID."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from db import repository as repo

logger = logging.getLogger(__name__)

ImageProvider = Literal["neironych", "nexus"]


def is_http_5xx(error: BaseException) -> bool:
    status = getattr(error, "status_code", None)
    return isinstance(status, int) and not isinstance(status, bool) and 500 <= status <= 599


async def settle_image_http_5xx(
    session: AsyncSession,
    generation_id: int,
    error: BaseException,
    *,
    provider: ImageProvider,
    expected_task_id: str | None = None,
) -> tuple[bool, float] | None:
    """Return None for unknown outcomes; terminally refund an explicit 5xx."""
    if not is_http_5xx(error):
        return None
    review = {
        "state": "pending",
        "provider": provider,
        "original_task_id": expected_task_id or "",
        "last_provider_status": "http_5xx",
        "refunded_at": datetime.now(timezone.utc).isoformat(),
    }
    settlement = await repo.fail_generation_and_refund(
        session,
        generation_id,
        f"{provider} image HTTP {error.status_code}",
        refund_note=f"image:http_5xx:{provider}",
        expected_task_id=expected_task_id,
        require_missing_task_id=expected_task_id is None,
        provider_review=review,
        provider_review_key=repo.IMAGE_REFUND_PROVIDER_REVIEW_KEY,
    )
    if settlement[0] and settlement[1] > 0:
        logger.info(
            "Image 5xx supplier review recorded gen=%s provider=%s http_status=%s refunded=%s",
            generation_id, provider, error.status_code, settlement[1],
        )
    return settlement
