"""Durable exactly-once admission for a keyed paid feed-remix request.

This claim is recorded before spending.  An ambiguous or interrupted request
must NOT be re-admitted, even if a generation was never linked.  Operators
investigate that state; background retries must never create another charge.
"""
from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import FeedRemixClaim


async def get_claim(session: AsyncSession, *, user_id: int, request_key: str) -> FeedRemixClaim | None:
    return (
        await session.execute(
            select(FeedRemixClaim).where(
                FeedRemixClaim.user_id == user_id,
                FeedRemixClaim.request_key == request_key,
            )
        )
    ).scalar_one_or_none()


async def reserve_claim(
    session: AsyncSession,
    *,
    user_id: int,
    request_key: str,
    request_hash: str,
    source_generation_id: int,
) -> tuple[FeedRemixClaim, bool]:
    """Unique constraint serializes simultaneous calls before financial effects."""
    claim = FeedRemixClaim(
        user_id=user_id, request_key=request_key,
        request_hash=request_hash, source_generation_id=source_generation_id,
        status="running",
    )
    try:
        async with session.begin_nested():
            session.add(claim)
            await session.flush()
    except IntegrityError:
        existing = await get_claim(session, user_id=user_id, request_key=request_key)
        if existing is None:
            raise
        return existing, False
    await session.commit()
    return claim, True


async def link_generation(
    session: AsyncSession, *, user_id: int, request_key: str, generation_id: int,
) -> bool:
    """Link exactly one charged generation before submitting any provider job."""
    result = await session.execute(
        update(FeedRemixClaim)
        .where(
            FeedRemixClaim.user_id == user_id,
            FeedRemixClaim.request_key == request_key,
            FeedRemixClaim.generation_id.is_(None),
            FeedRemixClaim.status == "running",
        )
        .values(generation_id=generation_id, status="linked")
        .returning(FeedRemixClaim.id)
    )
    linked = result.scalar_one_or_none() is not None
    await session.commit()
    return linked


async def release_precharge_claim(
    session: AsyncSession, *, user_id: int, request_key: str, request_hash: str,
) -> None:
    """Only call after a proven pre-charge denial, not after ambiguous submit."""
    await session.execute(
        delete(FeedRemixClaim).where(
            FeedRemixClaim.user_id == user_id,
            FeedRemixClaim.request_key == request_key,
            FeedRemixClaim.request_hash == request_hash,
            FeedRemixClaim.status == "running",
            FeedRemixClaim.generation_id.is_(None),
        )
    )
    await session.commit()
