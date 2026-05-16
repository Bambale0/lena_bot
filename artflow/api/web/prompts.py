from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import PromptCard, PromptCreateRequest
from db.models import PromptCategory, PromptStatus
from db.prompt_repository import (
    MAX_ACTIVE_PROMPTS_PER_USER,
    count_approved_prompts,
    count_active_prompts_by_author,
    create_prompt,
    derive_description,
    derive_title,
    get_prompt_by_id,
    get_approved_prompts,
    get_popular_prompts,
    get_prompts_by_tag,
    get_top_prompts,
    infer_category,
    like_prompt,
    use_prompt,
)
from db.session import get_session

router = APIRouter(tags=["web"])


def _is_public_approved(prompt) -> bool:
    return bool(
        prompt
        and getattr(prompt, "status", None) == PromptStatus.approved
        and getattr(prompt, "is_public", False)
    )


@router.get("/prompts")
async def prompts(
    source: str = Query(default="catalog", pattern="^(catalog|top|trending|popular|best|tag)$"),
    tag: str | None = Query(default=None, min_length=1, max_length=32),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    prompt_category = None
    if category:
        try:
            prompt_category = PromptCategory(category)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Unknown category: {category!r}") from exc

    if tag:
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
            "items": [PromptCard.from_prompt(item).model_dump() for item in items],
        }
    )


@router.get("/prompts/{prompt_id}")
async def prompt_detail(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    prompt = await get_prompt_by_id(session, prompt_id)
    if not _is_public_approved(prompt):
        return error_response(404, "Prompt not found")
    return ok(PromptCard.from_prompt(prompt).model_dump())


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
    return ok({"status": like_status, "prompt": PromptCard.from_prompt(prompt).model_dump()})


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
    return ok({"prompt": PromptCard.from_prompt(prompt).model_dump(), "rewards": rewards})


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
    return ok(PromptCard.from_prompt(prompt).model_dump())
