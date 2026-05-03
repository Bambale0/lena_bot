# db/prompt_repository.py
from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PromptCategory, PromptStatus, User, UserPrompt

logger = logging.getLogger(__name__)

PROMPT_REWARD_CREDITS = 3
MAX_ACTIVE_PROMPTS_PER_USER = 5


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def create_prompt(
    session: AsyncSession,
    author_id: int,
    title: str,
    description: str,
    category: PromptCategory,
    prompt_text: str,
) -> UserPrompt:
    prompt = UserPrompt(
        author_id=author_id,
        title=title,
        description=description,
        category=category,
        prompt_text=prompt_text,
        status=PromptStatus.pending,
    )
    session.add(prompt)
    await session.commit()
    await session.refresh(prompt)
    logger.info("Prompt created: id=%s author=%s", prompt.id, author_id)
    return prompt


async def get_prompt_by_id(session: AsyncSession, prompt_id: int) -> UserPrompt | None:
    result = await session.execute(select(UserPrompt).where(UserPrompt.id == prompt_id))
    return result.scalar_one_or_none()


async def count_active_prompts_by_author(session: AsyncSession, author_id: int) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(UserPrompt)
        .where(
            UserPrompt.author_id == author_id,
            UserPrompt.status.in_([PromptStatus.pending, PromptStatus.approved]),
        )
    )
    return result.scalar_one()


# ── Каталог ───────────────────────────────────────────────────────────────────

async def get_approved_prompts(
    session: AsyncSession,
    category: PromptCategory | None = None,
    offset: int = 0,
    limit: int = 10,
) -> list[UserPrompt]:
    q = select(UserPrompt).where(UserPrompt.status == PromptStatus.approved)
    if category:
        q = q.where(UserPrompt.category == category)
    q = q.order_by(desc(UserPrompt.uses_count)).offset(offset).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


async def count_approved_prompts(
    session: AsyncSession, category: PromptCategory | None = None
) -> int:
    q = select(func.count()).select_from(UserPrompt).where(
        UserPrompt.status == PromptStatus.approved
    )
    if category:
        q = q.where(UserPrompt.category == category)
    return (await session.execute(q)).scalar_one()


# ── Использование промпта ─────────────────────────────────────────────────────

async def use_prompt(
    session: AsyncSession,
    prompt_id: int,
    user_id: int,
) -> tuple[UserPrompt, bool]:
    """
    Регистрирует использование промпта.
    Возвращает (prompt, reward_given):
      reward_given=True — автору начислены кредиты (не свой промпт).
    """
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt or prompt.status != PromptStatus.approved:
        raise ValueError(f"Prompt {prompt_id} not available")

    # Инкремент счётчика
    await session.execute(
        update(UserPrompt)
        .where(UserPrompt.id == prompt_id)
        .values(uses_count=UserPrompt.uses_count + 1)
    )

    reward_given = False
    if prompt.author_id != user_id:
        # Начисляем кредиты автору
        from db import repository as repo
        await repo.add_credits(session, prompt.author_id, PROMPT_REWARD_CREDITS)
        reward_given = True
        logger.info(
            "Prompt reward: prompt_id=%s author=%s +%d cr",
            prompt_id, prompt.author_id, PROMPT_REWARD_CREDITS,
        )

    await session.commit()
    await session.refresh(prompt)
    return prompt, reward_given


# ── Модерация ─────────────────────────────────────────────────────────────────

async def get_pending_prompts(session: AsyncSession) -> list[UserPrompt]:
    result = await session.execute(
        select(UserPrompt)
        .where(UserPrompt.status == PromptStatus.pending)
        .order_by(UserPrompt.created_at)
    )
    return list(result.scalars().all())


async def approve_prompt(session: AsyncSession, prompt_id: int) -> UserPrompt | None:
    await session.execute(
        update(UserPrompt)
        .where(UserPrompt.id == prompt_id)
        .values(status=PromptStatus.approved)
    )
    await session.commit()
    return await get_prompt_by_id(session, prompt_id)


async def reject_prompt(
    session: AsyncSession, prompt_id: int, reason: str
) -> UserPrompt | None:
    await session.execute(
        update(UserPrompt)
        .where(UserPrompt.id == prompt_id)
        .values(status=PromptStatus.rejected, reject_reason=reason)
    )
    await session.commit()
    return await get_prompt_by_id(session, prompt_id)


async def deactivate_prompt(
    session: AsyncSession, prompt_id: int
) -> UserPrompt | None:
    await session.execute(
        update(UserPrompt)
        .where(UserPrompt.id == prompt_id)
        .values(status=PromptStatus.deactivated)
    )
    await session.commit()
    return await get_prompt_by_id(session, prompt_id)


# ── Статистика автора ─────────────────────────────────────────────────────────

async def get_author_prompts(
    session: AsyncSession, author_id: int
) -> list[UserPrompt]:
    result = await session.execute(
        select(UserPrompt)
        .where(UserPrompt.author_id == author_id)
        .order_by(desc(UserPrompt.created_at))
    )
    return list(result.scalars().all())


async def get_author_total_uses(session: AsyncSession, author_id: int) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(UserPrompt.uses_count), 0))
        .where(UserPrompt.author_id == author_id)
    )
    return result.scalar_one()
