from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_routes import (
    AssistantChatRequest,
    LanguageRequest,
    miniapp_assistant,
    miniapp_help,
    miniapp_set_language,
)
from api.web.deps import error_response, get_web_user_or_none, ok
from db.session import get_session

router = APIRouter(tags=["web"])


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_dump(item) for item in value]
    if isinstance(value, tuple):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    return value


async def _call(handler, *args, **kwargs) -> dict:
    try:
        return ok(_dump(await handler(*args, **kwargs)))
    except HTTPException as exc:
        return error_response(exc.status_code, str(exc.detail))


def _auth_required(user):
    if user is None:
        return error_response(401, "Authentication required")
    return None


@router.post("/assistant")
async def assistant_chat(
    body: AssistantChatRequest,
    user=Depends(get_web_user_or_none),
) -> dict:
    if auth_error := _auth_required(user):
        return auth_error
    return await _call(miniapp_assistant, body=body, user=user)


@router.post("/settings/language")
async def set_language(
    body: LanguageRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if auth_error := _auth_required(user):
        return auth_error
    return await _call(miniapp_set_language, body=body, session=session, user=user)


@router.get("/help")
async def help_text(
    topic: str = Query(default="main", pattern="^(main|stars)$"),
    user=Depends(get_web_user_or_none),
) -> dict:
    if auth_error := _auth_required(user):
        return auth_error
    return await _call(miniapp_help, topic=topic, user=user)
