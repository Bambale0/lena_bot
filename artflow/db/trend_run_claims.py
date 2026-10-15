"""Durable admission control for one paid trend submission per request key."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TrendRunClaim


async def get_claim(session: AsyncSession, user_id: int, request_key: str) -> TrendRunClaim | None:
    return (
        await session.execute(
            select(TrendRunClaim).where(
                TrendRunClaim.user_id == user_id,
                TrendRunClaim.request_key == request_key,
            )
        )
    ).scalar_one_or_none()


async def reserve_claim(
    session: AsyncSession,
    *,
    user_id: int,
    request_key: str,
    request_hash: str,
    trend_id: int,
) -> tuple[TrendRunClaim, bool]:
    """The unique index serializes competing requests before either can spend."""
    claim = TrendRunClaim(
        user_id=user_id,
        request_key=request_key,
        request_hash=request_hash,
        trend_id=trend_id,
        status="running",
    )
    try:
        async with session.begin_nested():
            session.add(claim)
            await session.flush()
    except IntegrityError:
        existing = await get_claim(session, user_id, request_key)
        if existing is None:
            raise
        return existing, False
    await session.commit()
    return claim, True


async def release_pre_submit_claim(
    session: AsyncSession, *, user_id: int, request_key: str, request_hash: str,
) -> None:
    """Release only this request's unlinked claim after a proven pre-submit reject."""
    claim = await get_claim(session, user_id, request_key)
    if claim is None or claim.request_hash != request_hash or claim.generation_id is not None:
        return
    if claim.status != "running":
        return
    await session.delete(claim)
    await session.commit()
