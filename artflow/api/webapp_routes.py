from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.webapp_auth import get_webapp_user
from core.config import settings
from db import prompt_repository, repository as repo
from db.models import (
    Generation,
    GenerationStatus,
    GenerationType,
    ImageSession,
    ImageSessionStatus,
    PromptCategory,
    PromptStatus,
    User,
    UserPrompt,
)
from db.session import get_session

router = APIRouter(prefix="/api/webapp", tags=["telegram-webapp"])

DEFAULT_IMAGE_MODEL = "nano-banana-pro"
DEFAULT_ASPECT_RATIO = "9:16"
DEFAULT_QUALITY = "2K"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _author_label(username: str | None, full_name: str | None) -> str:
    if username:
        return f"@{username}"
    return full_name or "APIX creator"


def _prompt_preview(prompt: str | None, limit: int = 180) -> str:
    text = " ".join((prompt or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _image_session_payload(image_session: ImageSession | None) -> dict | None:
    if not image_session:
        return None
    reference_count = 0
    if image_session.reference_file_ids:
        try:
            import json

            reference_count = len(json.loads(image_session.reference_file_ids))
        except Exception:
            reference_count = 1
    elif image_session.reference_file_id or image_session.reference_url:
        reference_count = 1
    return {
        "id": image_session.id,
        "model": image_session.model,
        "aspect_ratio": image_session.aspect_ratio,
        "quality": image_session.quality,
        "count": image_session.count,
        "reference_count": reference_count,
        "last_result_url": image_session.last_result_url,
    }


def _generation_payload(gen: Generation) -> dict:
    return {
        "id": gen.id,
        "type": gen.gen_type.value,
        "model": gen.model,
        "preview_url": gen.result_url,
        "prompt_preview": _prompt_preview(gen.prompt),
        "created_at": _iso(gen.created_at),
        "likes": gen.likes_count,
        "shares": gen.shares_count,
    }


def _prompt_payload(prompt: UserPrompt, *, include_detail: bool = False) -> dict:
    data = {
        "id": prompt.id,
        "title": prompt.title,
        "description": prompt.description,
        "preview_url": prompt.preview_url,
        "category": prompt.category.value,
        "uses_count": prompt.uses_count,
        "price_bananas": 4,
        "model": prompt.model or DEFAULT_IMAGE_MODEL,
        "likes": prompt.likes,
        "created_at": _iso(prompt.created_at),
    }
    if include_detail:
        data.update(
            {
                "aspect_ratio": DEFAULT_ASPECT_RATIO,
                "reference_count": 1 if prompt.preview_url else 0,
                "quality": DEFAULT_QUALITY,
            }
        )
    return data


async def _create_or_update_image_session(
    session: AsyncSession,
    *,
    user_id: int,
    model: str,
    prompt: str,
    reference_url: str | None = None,
    aspect_ratio: str | None = DEFAULT_ASPECT_RATIO,
    quality: str = DEFAULT_QUALITY,
    count: int = 1,
) -> ImageSession:
    active = await repo.get_active_image_session(session, user_id)
    if active:
        await session.execute(
            update(ImageSession)
            .where(ImageSession.id == active.id, ImageSession.user_id == user_id)
            .values(
                model=model,
                mode="image" if reference_url else "text",
                aspect_ratio=aspect_ratio,
                quality=quality,
                count=count,
                base_prompt=prompt,
                last_prompt=prompt,
                reference_url=reference_url,
                last_result_url=reference_url or active.last_result_url,
                updated_at=func.now(),
            )
        )
        await session.commit()
        refreshed = await repo.get_image_session(session, active.id, user_id)
        if refreshed:
            return refreshed

    return await repo.create_image_session(
        session,
        user_id=user_id,
        model=model,
        mode="image" if reference_url else "text",
        aspect_ratio=aspect_ratio,
        quality=quality,
        count=count,
        base_prompt=prompt,
        reference_file_id=None,
        reference_url=reference_url,
    )


@router.get("/health")
async def webapp_health() -> dict:
    return {"ok": True}


@router.get("/me")
async def get_me(
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    image_session = await repo.get_active_image_session(session, user.id)
    return {
        "user": {
            "id": user.id,
            "tg_id": user.tg_id,
            "username": user.username,
            "full_name": user.full_name,
            "credits": user.credits,
            "referral_code": user.referral_code,
        },
        "active_image_session": _image_session_payload(image_session),
    }


@router.get("/feed")
async def get_feed(
    sort: str = Query("trending", pattern="^(trending|top_day|new)$"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    del user
    if sort == "top_day":
        cards = await repo.get_top_day_generations(session, limit=limit + offset)
    elif sort == "new":
        result = await session.execute(
            select(Generation, User.username, User.full_name)
            .join(User, Generation.user_id == User.id)
            .where(
                Generation.gen_type == GenerationType.image,
                Generation.status == GenerationStatus.done,
                Generation.result_url.is_not(None),
                Generation.is_public_feed.is_(True),
            )
            .order_by(desc(Generation.created_at))
            .offset(offset)
            .limit(limit)
        )
        return {
            "items": [
                {
                    "id": gen.id,
                    "author": _author_label(username, full_name),
                    "model": gen.model,
                    "preview_url": gen.result_url,
                    "prompt_preview": _prompt_preview(gen.prompt),
                    "likes": gen.likes_count,
                    "remixes": 0,
                    "shares": gen.shares_count,
                    "created_at": _iso(gen.created_at),
                }
                for gen, username, full_name in result.all()
            ]
        }
    else:
        cards = await repo.get_feed_generations(session, limit=limit + offset)

    items = []
    for card in cards[offset : offset + limit]:
        gen = card.generation
        items.append(
            {
                "id": gen.id,
                "author": _author_label(card.username, card.full_name),
                "model": gen.model,
                "preview_url": gen.result_url,
                "prompt_preview": _prompt_preview(gen.prompt),
                "likes": gen.likes_count,
                "remixes": card.remix_count,
                "shares": gen.shares_count,
                "created_at": _iso(gen.created_at),
            }
        )
    return {"items": items}


@router.post("/feed/{generation_id}/like")
async def like_feed(
    generation_id: int,
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    del user
    gen = await repo.like_feed_generation(session, generation_id)
    if not gen:
        return {"ok": True, "likes": 0, "persisted": False}
    return {"ok": True, "likes": gen.likes_count, "persisted": True}


@router.post("/feed/{generation_id}/remix")
async def remix_generation(
    generation_id: int,
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    card = await repo.get_feed_generation_card(session, generation_id)
    if not card:
        raise HTTPException(status_code=404, detail="Generation not found")
    gen = card.generation
    await _create_or_update_image_session(
        session,
        user_id=user.id,
        model=gen.model,
        prompt=gen.prompt,
        reference_url=gen.result_url,
        aspect_ratio=card.aspect_ratio or DEFAULT_ASPECT_RATIO,
        quality=card.quality or DEFAULT_QUALITY,
        count=card.count or 1,
    )
    return {
        "ok": True,
        "open_bot_required": True,
        "message": "Ремикс подготовлен. Вернись в бот и напиши, что изменить.",
    }


@router.get("/prompts")
async def get_prompts(
    category: str | None = None,
    sort: str = Query("trending", pattern="^(trending|top_day|best|new)$"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    del user
    prompt_category = None
    if category and category in {item.value for item in PromptCategory}:
        prompt_category = PromptCategory(category)

    stmt = select(UserPrompt).where(
        UserPrompt.status == PromptStatus.approved,
        UserPrompt.is_public.is_(True),
    )
    if prompt_category:
        stmt = stmt.where(UserPrompt.category == prompt_category)
    if sort == "new":
        stmt = stmt.order_by(desc(UserPrompt.created_at))
    elif sort == "best":
        stmt = stmt.order_by(desc(UserPrompt.uses_count), desc(UserPrompt.likes), desc(UserPrompt.created_at))
    else:
        stmt = stmt.order_by(desc(UserPrompt.likes), desc(UserPrompt.uses_count), desc(UserPrompt.created_at))
    result = await session.execute(stmt.offset(offset).limit(limit))
    return {"items": [_prompt_payload(prompt) for prompt in result.scalars().all()]}


@router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    del user
    prompt = await prompt_repository.get_prompt_by_id(session, prompt_id)
    if not prompt or prompt.status != PromptStatus.approved or not prompt.is_public:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _prompt_payload(prompt, include_detail=True)


@router.post("/prompts/{prompt_id}/use")
async def use_prompt(
    prompt_id: int,
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    prompt = await prompt_repository.get_prompt_by_id(session, prompt_id)
    if not prompt or prompt.status != PromptStatus.approved or not prompt.is_public:
        raise HTTPException(status_code=404, detail="Prompt not found")
    await prompt_repository.increment_usage(session, prompt.id)
    await _create_or_update_image_session(
        session,
        user_id=user.id,
        model=prompt.model or DEFAULT_IMAGE_MODEL,
        prompt=prompt.prompt_text,
        reference_url=prompt.preview_url,
    )
    return {
        "ok": True,
        "open_bot_required": True,
        "message": "Пресет применён. Вернись в бот, отправь фото или уточнение.",
    }


@router.post("/prompts/{prompt_id}/save")
async def save_prompt(
    prompt_id: int,
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    del user
    prompt = await prompt_repository.get_prompt_by_id(session, prompt_id)
    if not prompt or prompt.status != PromptStatus.approved or not prompt.is_public:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"ok": True, "persisted": False}


@router.get("/history")
async def get_history(
    kind: str = Query("all", pattern="^(all|images|video|music)$"),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(Generation).where(Generation.user_id == user.id)
    if kind == "images":
        stmt = stmt.where(Generation.gen_type == GenerationType.image)
    elif kind == "video":
        stmt = stmt.where(Generation.gen_type == GenerationType.video)
    elif kind == "music":
        stmt = stmt.where(False)
    stmt = stmt.order_by(desc(Generation.created_at)).limit(limit)
    result = await session.execute(stmt)
    return {"items": [_generation_payload(gen) for gen in result.scalars().all()]}


@router.get("/referrals")
async def get_referrals(
    user: User = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    level1, level2, level3 = await repo.count_user_referrals(session, user.id)
    earned_result = await session.execute(
        select(func.coalesce(func.sum(Generation.credits_spent), 0)).where(Generation.user_id == user.id)
    )
    referral_code = user.referral_code
    bot_username = getattr(settings, "BOT_USERNAME", "APIXBot")
    return {
        "referral_link": f"https://t.me/{bot_username}?start={referral_code}",
        "referral_code": referral_code,
        "level1_count": level1,
        "level2_count": level2,
        "level3_count": level3,
        "earned_bananas": int(earned_result.scalar_one() or 0),
        "rates": {"level1": 30, "level2": 7, "level3": 3},
    }
