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
