"""Read and update the audited instruction used for feed image identity repeats."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import FeedRecipeIdentityPolicy, FeedRecipeIdentityPolicyAudit

MIN_LENGTH = 100
MAX_LENGTH = 3000


def validate_instruction(value: str) -> str:
    instruction = str(value or "").strip()
    if not MIN_LENGTH <= len(instruction) <= MAX_LENGTH:
        raise ValueError("Identity instruction length must be 100–3000 characters")
    return instruction


async def get_feed_recipe_identity_instruction(session: AsyncSession) -> str:
    policy = await session.get(FeedRecipeIdentityPolicy, 1)
    if policy is None:
        raise RuntimeError("Feed recipe identity policy is missing")
    return validate_instruction(policy.instruction)


async def set_feed_recipe_identity_instruction(
    session: AsyncSession, instruction: str, *, admin_tg_id: int,
) -> str:
    validated = validate_instruction(instruction)
    if not int(admin_tg_id):
        raise ValueError("Admin actor is required")
    policy = (await session.execute(
        select(FeedRecipeIdentityPolicy).where(FeedRecipeIdentityPolicy.id == 1).with_for_update()
    )).scalar_one()
    previous = policy.instruction
    if previous != validated or policy.updated_by_admin_tg_id is None:
        policy.instruction = validated
        policy.updated_by_admin_tg_id = int(admin_tg_id)
        session.add(FeedRecipeIdentityPolicyAudit(
            previous_instruction=previous,
            new_instruction=validated,
            changed_by_admin_tg_id=int(admin_tg_id),
        ))
    await session.commit()
    return policy.instruction
