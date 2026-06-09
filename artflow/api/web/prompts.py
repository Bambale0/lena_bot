from __future__ import annotations

import difflib
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import PromptCard, PromptCreateRequest, PromptRejectRequest
from api.public_files import local_upload_path_from_url, public_url_is_available
from core.config import settings
from db import repository as repo
from db.models import PromptCategory, PromptStatus
from db.prompt_repository import (
    MAX_ACTIVE_PROMPTS_PER_USER,
    approve_prompt,
    count_approved_prompts,
    count_active_prompts_by_author,
    create_prompt,
    deactivate_prompt,
    derive_description,
    derive_title,
    get_prompt_by_id,
    get_approved_prompts,
    get_author_prompts,
    get_popular_prompts,
    get_pending_prompts,
    get_prompts_by_tag,
    get_top_prompts,
    infer_category,
    like_prompt,
    reject_prompt,
    use_prompt,
)
from db.session import get_session

router = APIRouter(tags=["web"])

_PROMPT_PREVIEW_POOL_MIN = 120


def _normalize_preview_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]+", " ", str(value or "").lower())).strip()


def _same_model_family(left: str | None, right: str | None) -> bool:
    left_root = str(left or "").split("-", 1)[0].strip().lower()
    right_root = str(right or "").split("-", 1)[0].strip().lower()
    return bool(left_root and right_root and left_root == right_root)


async def _prompt_preview_fallbacks(
    session: AsyncSession,
    prompts: list,
) -> dict[int, str]:
    missing = [item for item in prompts if not public_url_is_available(getattr(item, "preview_url", None))]
    if not missing:
        return {}

    feed_cards = await repo.get_feed_generations(
        session,
        limit=max(_PROMPT_PREVIEW_POOL_MIN, len(missing) * 8),
    )
    local_generations = [
        card.generation
        for card in feed_cards
        if local_upload_path_from_url(getattr(card.generation, "result_url", None))
        and public_url_is_available(getattr(card.generation, "result_url", None))
    ]
    generations = local_generations or [
        card.generation
        for card in feed_cards
        if public_url_is_available(getattr(card.generation, "result_url", None))
    ]
    if not generations:
        return {}

    normalized_generations = [
        (generation, _normalize_preview_text(getattr(generation, "prompt", ""))[:800])
        for generation in generations
    ]
    used_ids: set[int] = set()
    fallbacks: dict[int, str] = {}

    for index, prompt in enumerate(missing):
        prompt_text = _normalize_preview_text(getattr(prompt, "prompt_text", ""))[:800]
        prompt_model = getattr(prompt, "model", None)
        best_score = 0.0
        best_generation = None
        for generation, generation_text in normalized_generations:
            if not generation_text:
                continue
            score = difflib.SequenceMatcher(None, prompt_text[:500], generation_text[:500]).ratio()
            if prompt_model == getattr(generation, "model", None):
                score += 0.08
            elif _same_model_family(prompt_model, getattr(generation, "model", None)):
                score += 0.03
            if score > best_score:
                best_score = score
                best_generation = generation

        selected = best_generation if best_generation is not None and best_score >= 0.42 else None
        if selected is None:
            model_pool = [
                generation
                for generation in generations
                if generation.id not in used_ids
                and (
                    prompt_model == getattr(generation, "model", None)
                    or _same_model_family(prompt_model, getattr(generation, "model", None))
                )
            ]
            pool = model_pool or [generation for generation in generations if generation.id not in used_ids] or generations
            selected = pool[index % len(pool)]

        if selected is not None:
            used_ids.add(int(getattr(selected, "id", 0) or 0))
            fallbacks[int(getattr(prompt, "id", 0))] = str(getattr(selected, "result_url", "") or "")

    return fallbacks


async def _prompt_cards(
    session: AsyncSession,
    prompts: list,
    *,
    current_user_id: int | None = None,
) -> list[dict]:
    fallbacks = await _prompt_preview_fallbacks(session, prompts)
    return [
        PromptCard.from_prompt(
            item,
            current_user_id=current_user_id,
            fallback_preview_url=fallbacks.get(int(getattr(item, "id", 0))),
        ).model_dump()
        for item in prompts
    ]


def _is_public_approved(prompt) -> bool:
    return bool(
        prompt
        and getattr(prompt, "status", None) == PromptStatus.approved
        and getattr(prompt, "is_public", False)
    )


def _is_admin(user) -> bool:
    return bool(user and getattr(user, "tg_id", None) in settings.ADMIN_IDS)


@router.get("/prompts")
async def prompts(
    source: str = Query(default="catalog", pattern="^(catalog|top|trending|popular|best|tag|my)$"),
    tag: str | None = Query(default=None, min_length=1, max_length=32),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    prompt_category = None
    if category:
        try:
            prompt_category = PromptCategory(category)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Unknown category: {category!r}") from exc

    if source == "my":
        if user is None:
            return error_response(401, "Authentication required")
        items = await get_author_prompts(session, user.id)
        total = len(items)
        items = items[(page - 1) * limit : page * limit]
    elif tag:
        items = await get_prompts_by_tag(session, tag, limit=limit)
        total = len(items)
    elif source in {"top", "best"}:
        items = await get_top_prompts(session, limit=limit)
        total = len(items)
    elif source in {"popular", "trending"}:
        items = await get_popular_prompts(session, limit=limit)
        total = len(items)
    elif source == "tag":
        items = await get_prompts_by_tag(session, tag or "best", limit=limit)
        total = len(items)
    else:
        offset = (page - 1) * limit
        items = await get_approved_prompts(session, category=prompt_category, offset=offset, limit=limit)
        total = await count_approved_prompts(session, category=prompt_category)

    return ok(
        {
            "total": total,
            "page": page,
            "limit": limit,
            "items": await _prompt_cards(session, items, current_user_id=getattr(user, "id", None)),
        }
    )


@router.get("/prompts/{prompt_id}")
async def prompt_detail(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    prompt = await get_prompt_by_id(session, prompt_id)
    is_owner = bool(user and prompt and getattr(prompt, "author_id", None) == user.id)
    if not (_is_public_approved(prompt) or is_owner or _is_admin(user)):
        return error_response(404, "Prompt not found")
    return ok(PromptCard.from_prompt(prompt, current_user_id=getattr(user, "id", None)).model_dump())


@router.post("/prompts/{prompt_id}/like")
async def prompt_like(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")
    current = await get_prompt_by_id(session, prompt_id)
    if not _is_public_approved(current):
        return error_response(404, "Prompt not found")

    prompt, like_status = await like_prompt(session, prompt_id, user.id)
    if like_status == "duplicate":
        prompt = await get_prompt_by_id(session, prompt_id)
    if not _is_public_approved(prompt):
        return error_response(404, "Prompt not found")
    return ok({"status": like_status, "prompt": PromptCard.from_prompt(prompt, current_user_id=user.id).model_dump()})


@router.post("/prompts/{prompt_id}/use")
async def prompt_use(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")
    try:
        prompt, rewards = await use_prompt(session, prompt_id, user.id)
    except ValueError:
        return error_response(404, "Prompt not found")
    return ok({"prompt": PromptCard.from_prompt(prompt, current_user_id=user.id).model_dump(), "rewards": rewards})


@router.post("/prompts")
async def prompt_create(
    body: PromptCreateRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")

    prompt_text = body.prompt_text.strip()
    if not prompt_text:
        return error_response(422, "Prompt text is required")

    active_count = await count_active_prompts_by_author(session, user.id)
    if active_count >= MAX_ACTIVE_PROMPTS_PER_USER:
        return error_response(429, "Too many active prompts")

    tags = [tag.strip() for tag in body.tags if tag and tag.strip()]
    category = infer_category(prompt_text, tags)
    title = (body.title or "").strip() or derive_title(prompt_text)
    description = (body.description or "").strip() or derive_description(prompt_text)
    prompt = await create_prompt(
        session,
        user.id,
        title,
        description,
        category,
        prompt_text,
        preview_url=(body.preview_url or "").strip() or None,
        model=(body.model or "").strip() or None,
        tags=tags,
        is_public=True,
    )
    return ok(PromptCard.from_prompt(prompt, current_user_id=user.id).model_dump())


@router.get("/admin/prompts")
async def admin_prompts(
    status_filter: str = Query(default="pending", alias="status", pattern="^(pending)$"),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if not _is_admin(user):
        return error_response(403, "Admin access required")
    items = await get_pending_prompts(session)
    return ok(
        {
            "status": status_filter,
            "items": [PromptCard.from_prompt(item).model_dump() for item in items],
        }
    )


@router.post("/admin/prompts/{prompt_id}/approve")
async def admin_prompt_approve(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if not _is_admin(user):
        return error_response(403, "Admin access required")
    prompt = await approve_prompt(session, prompt_id)
    if prompt is None:
        return error_response(404, "Prompt not found")
    return ok(PromptCard.from_prompt(prompt).model_dump())


@router.post("/admin/prompts/{prompt_id}/reject")
async def admin_prompt_reject(
    prompt_id: int,
    body: PromptRejectRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if not _is_admin(user):
        return error_response(403, "Admin access required")
    prompt = await reject_prompt(session, prompt_id, body.reason.strip())
    if prompt is None:
        return error_response(404, "Prompt not found")
    return ok(PromptCard.from_prompt(prompt).model_dump())


@router.post("/admin/prompts/{prompt_id}/deactivate")
async def admin_prompt_deactivate(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if not _is_admin(user):
        return error_response(403, "Admin access required")
    prompt = await deactivate_prompt(session, prompt_id)
    if prompt is None:
        return error_response(404, "Prompt not found")
    return ok(PromptCard.from_prompt(prompt).model_dump())
