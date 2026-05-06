# db/prompt_repository.py
from __future__ import annotations

import logging
import math
import re

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db import repository as repo
from db.models import PromptCategory, PromptStatus, UserPrompt

logger = logging.getLogger(__name__)

PROMPT_AUTHOR_SHARE = 0.30
PROMPT_REF_L2_SHARE = 0.07
PROMPT_REF_L3_SHARE = 0.03
PROMPT_REWARD_CREDITS = 3
MAX_ACTIVE_PROMPTS_PER_USER = 5
TOP_PROMPTS_LIMIT = 10

COLLECTION_TAGS: dict[str, str] = {
    "best": "🧠 Best prompts",
    "characters": "🎭 Characters",
    "cyberpunk": "🌆 Cyberpunk",
    "realism": "📸 Realism",
    "cinematic": "🎬 Cinematic",
    "nsfw": "🔞 NSFW",
    "music": "🎵 Music prompts",
}

COLLECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "best": ("masterpiece", "award winning", "highly detailed", "best quality"),
    "characters": ("character", "girl", "boy", "hero", "face", "portrait"),
    "cyberpunk": ("cyberpunk", "neon", "futuristic"),
    "realism": ("realistic", "photo", "photorealistic"),
    "cinematic": ("cinematic", "film still", "movie", "dramatic light"),
    "nsfw": ("nsfw", "sensual", "lingerie"),
    "music": ("music", "song", "suno", "lyrics", "instrumental"),
}


def _normalize_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for tag in tags or []:
        normalized = re.sub(r"[^a-z0-9_+-]", "", tag.lower().strip().lstrip("#"))
        if normalized and normalized not in cleaned:
            cleaned.append(normalized[:32])
    return cleaned


def infer_tags(prompt_text: str) -> list[str]:
    text = prompt_text.lower()
    tags: list[str] = []
    keyword_map = {
        "anime": ("anime", "manga"),
        "best": COLLECTION_KEYWORDS["best"],
        "characters": COLLECTION_KEYWORDS["characters"],
        "cinematic": COLLECTION_KEYWORDS["cinematic"],
        "cyberpunk": COLLECTION_KEYWORDS["cyberpunk"],
        "music": COLLECTION_KEYWORDS["music"],
        "nsfw": COLLECTION_KEYWORDS["nsfw"],
        "realism": COLLECTION_KEYWORDS["realism"],
    }
    for tag, keywords in keyword_map.items():
        if any(word in text for word in keywords):
            tags.append(tag)
    return tags or ["realism"]


def infer_category(prompt_text: str, tags: list[str]) -> PromptCategory:
    lowered = prompt_text.lower()
    if "marketing" in lowered or "advert" in lowered:
        return PromptCategory.marketing
    if "business" in lowered or "brand" in lowered:
        return PromptCategory.business
    if "photo" in lowered or "realism" in tags or "characters" in tags:
        return PromptCategory.photo
    if "anime" in tags or "cyberpunk" in tags or "cinematic" in tags:
        return PromptCategory.art
    return PromptCategory.other


def derive_title(prompt_text: str) -> str:
    text = " ".join(prompt_text.split())
    return text[:60] if len(text) <= 60 else text[:57].rstrip() + "..."


def derive_description(prompt_text: str) -> str:
    text = " ".join(prompt_text.split())
    return text[:200] if len(text) <= 200 else text[:197].rstrip() + "..."


async def create_prompt(
    session: AsyncSession,
    author_id: int,
    title: str,
    description: str,
    category: PromptCategory,
    prompt_text: str,
    *,
    preview_url: str | None = None,
    model: str | None = None,
    tags: list[str] | None = None,
    is_public: bool = True,
) -> UserPrompt:
    prompt = UserPrompt(
        author_id=author_id,
        title=title,
        description=description,
        category=category,
        prompt_text=prompt_text,
        preview_url=preview_url,
        model=model,
        tags=_normalize_tags(tags) or infer_tags(prompt_text),
        is_public=is_public,
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


async def get_top_prompts(session: AsyncSession, limit: int = TOP_PROMPTS_LIMIT) -> list[UserPrompt]:
    result = await session.execute(
        select(UserPrompt)
        .where(
            UserPrompt.status == PromptStatus.approved,
            UserPrompt.is_public.is_(True),
        )
        .order_by(desc(UserPrompt.uses_count), desc(UserPrompt.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_popular_prompts(session: AsyncSession, limit: int = TOP_PROMPTS_LIMIT) -> list[UserPrompt]:
    result = await session.execute(
        select(UserPrompt)
        .where(
            UserPrompt.status == PromptStatus.approved,
            UserPrompt.is_public.is_(True),
        )
        .order_by(desc(UserPrompt.likes), desc(UserPrompt.uses_count), desc(UserPrompt.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_prompts_by_tag(
    session: AsyncSession,
    tag: str,
    limit: int = TOP_PROMPTS_LIMIT,
) -> list[UserPrompt]:
    result = await session.execute(
        select(UserPrompt)
        .where(
            UserPrompt.status == PromptStatus.approved,
            UserPrompt.is_public.is_(True),
            UserPrompt.tags.any(tag.lower()),
        )
        .order_by(desc(UserPrompt.uses_count), desc(UserPrompt.likes), desc(UserPrompt.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_approved_prompts(
    session: AsyncSession,
    category: PromptCategory | None = None,
    offset: int = 0,
    limit: int = 10,
) -> list[UserPrompt]:
    q = select(UserPrompt).where(
        UserPrompt.status == PromptStatus.approved,
        UserPrompt.is_public.is_(True),
    )
    if category:
        q = q.where(UserPrompt.category == category)
    q = q.order_by(desc(UserPrompt.uses_count), desc(UserPrompt.likes)).offset(offset).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


async def count_approved_prompts(session: AsyncSession, category: PromptCategory | None = None) -> int:
    q = select(func.count()).select_from(UserPrompt).where(
        UserPrompt.status == PromptStatus.approved,
        UserPrompt.is_public.is_(True),
    )
    if category:
        q = q.where(UserPrompt.category == category)
    return (await session.execute(q)).scalar_one()


async def increment_usage(session: AsyncSession, prompt_id: int) -> None:
    await session.execute(
        update(UserPrompt)
        .where(UserPrompt.id == prompt_id)
        .values(uses_count=UserPrompt.uses_count + 1)
    )
    await session.commit()


async def like_prompt(session: AsyncSession, prompt_id: int) -> UserPrompt | None:
    await session.execute(
        update(UserPrompt)
        .where(UserPrompt.id == prompt_id)
        .values(likes=UserPrompt.likes + 1)
    )
    await session.commit()
    return await get_prompt_by_id(session, prompt_id)


async def apply_prompt_rewards(
    session: AsyncSession,
    prompt: UserPrompt,
    *,
    using_user_id: int,
    credits_spent: int,
) -> dict[str, int]:
    if prompt.author_id == using_user_id:
        return {"author": 0, "l2": 0, "l3": 0}

    author_reward = max(1, math.floor(credits_spent * PROMPT_AUTHOR_SHARE))
    l2_reward = math.floor(credits_spent * PROMPT_REF_L2_SHARE)
    l3_reward = math.floor(credits_spent * PROMPT_REF_L3_SHARE)

    author = await repo.get_user_by_id(session, prompt.author_id)
    if not author:
        return {"author": 0, "l2": 0, "l3": 0}

    if author_reward > 0:
        await repo.add_credits(session, author.id, author_reward)

    if l2_reward > 0 and author.referrer_id:
        await repo.add_credits(session, author.referrer_id, l2_reward)

    if l3_reward > 0 and author.referrer_l2_id:
        await repo.add_credits(session, author.referrer_l2_id, l3_reward)

    logger.info(
        "Prompt rewards: prompt_id=%s author=%s +%s l2=%s l3=%s",
        prompt.id,
        prompt.author_id,
        author_reward,
        l2_reward,
        l3_reward,
    )
    return {"author": author_reward, "l2": l2_reward, "l3": l3_reward}


async def use_prompt(
    session: AsyncSession,
    prompt_id: int,
    user_id: int,
    *,
    credits_spent: int | None = None,
) -> tuple[UserPrompt, dict[str, int]]:
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt or prompt.status != PromptStatus.approved or not prompt.is_public:
        raise ValueError(f"Prompt {prompt_id} not available")

    await increment_usage(session, prompt_id)
    rewards = {"author": 0, "l2": 0, "l3": 0}
    if credits_spent is not None:
        rewards = await apply_prompt_rewards(
            session,
            prompt,
            using_user_id=user_id,
            credits_spent=credits_spent,
        )
    refreshed = await get_prompt_by_id(session, prompt_id)
    if refreshed is None:
        raise ValueError(f"Prompt {prompt_id} not available after update")
    return refreshed, rewards


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


async def reject_prompt(session: AsyncSession, prompt_id: int, reason: str) -> UserPrompt | None:
    await session.execute(
        update(UserPrompt)
        .where(UserPrompt.id == prompt_id)
        .values(status=PromptStatus.rejected, reject_reason=reason)
    )
    await session.commit()
    return await get_prompt_by_id(session, prompt_id)


async def deactivate_prompt(session: AsyncSession, prompt_id: int) -> UserPrompt | None:
    await session.execute(
        update(UserPrompt)
        .where(UserPrompt.id == prompt_id)
        .values(status=PromptStatus.deactivated, is_public=False)
    )
    await session.commit()
    return await get_prompt_by_id(session, prompt_id)


async def get_author_prompts(session: AsyncSession, author_id: int) -> list[UserPrompt]:
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
