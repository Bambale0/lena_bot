"""Settle explicit image-provider HTTP 5xx responses once, by persisted task ID."""
from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from db import repository as repo

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
    expected_task_id: str,
) -> tuple[bool, float] | None:
    """Return None for unknown outcomes; terminally refund an explicit 5xx."""
    if not is_http_5xx(error):
        return None
    return await repo.fail_generation_and_refund(
        session,
        generation_id,
        f"{provider} image HTTP {error.status_code}",
        refund_note=f"image:http_5xx:{provider}",
        expected_task_id=expected_task_id,
    )
