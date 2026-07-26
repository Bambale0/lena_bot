"""Atomic/idempotent billing helpers for provider operations."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import repository as repo
from db.models import Generation


async def refund_generation_once(
    session: AsyncSession,
    *,
    user_id: int,
    credits: int,
    generation_id: int | None,
    contract_id: str,
) -> bool:
    """Refund one generation at most once.

    The generation row is locked first. The refund marker and credit ledger entry
    are committed together by the existing repository credit transaction, so a
    concurrent status poll observes the marker and cannot refund twice.
    """
    if credits <= 0 or generation_id is None:
        return False

    result = await session.execute(
        select(Generation)
        .where(Generation.id == generation_id, Generation.tg_id == user_id)
        .with_for_update()
    )
    generation = result.scalar_one_or_none()
    if generation is None:
        return False

    params = dict(generation.input_params or {})
    if params.get("refund_applied") is True:
        return False

    params["refund_applied"] = True
    params["refund_contract_id"] = contract_id
    generation.input_params = params
    await session.flush()

    await repo.add_credits(
        session,
        user_id,
        credits,
        reason=f"provider_operation_refund:{contract_id}",
        ref_id=generation_id,
    )
    return True
