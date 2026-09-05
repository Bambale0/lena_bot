from __future__ import annotations

import inspect
import mimetypes
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_routes import (
    FeedRemixRequest,
    ImageGenRequest,
    MusicGenRequest,
    PromptImproveRequest,
    TopupRequest,
    VideoGenRequest,
    _is_supported_reference_image,
    _reconcile_user_active_generations,
    miniapp_improve_prompt,
    miniapp_photo_prompt,
)
from api.miniapp_routes import (
    create_image_generation as miniapp_create_image_generation,
)
from api.miniapp_routes import (
    create_music_generation as miniapp_create_music_generation,
)
from api.miniapp_routes import (
    create_suno_voice as miniapp_create_suno_voice,
)
from api.miniapp_routes import (
    create_video_generation as miniapp_create_video_generation,
)
from api.miniapp_routes import (
    get_feed_share_link as miniapp_get_feed_share_link,
)
from api.miniapp_routes import (
    list_image_models as miniapp_list_image_models,
)
from api.miniapp_routes import (
    list_music_models as miniapp_list_music_models,
)
from api.miniapp_routes import (
    list_payment_methods as miniapp_list_payment_methods,
)
from api.miniapp_routes import (
    list_payment_options as miniapp_list_payment_options,
)
from api.miniapp_routes import (
    list_plans as miniapp_list_plans,
)
from api.miniapp_routes import (
    list_suno_voices as miniapp_list_suno_voices,
)
from api.miniapp_routes import (
    list_video_models as miniapp_list_video_models,
)
from api.miniapp_routes import (
    publish_generation_to_library as miniapp_publish_generation,
)
from api.miniapp_routes import (
    refresh_suno_voice as miniapp_refresh_suno_voice,
)
from api.miniapp_routes import (
    remix_feed_post as miniapp_remix_feed_post,
)
from api.miniapp_routes import (
    remove_feed_post as miniapp_remove_feed_post,
)
from api.miniapp_routes import (
    remove_from_library as miniapp_remove_from_library,
)
from api.miniapp_routes import (
    share_generation as miniapp_share_generation,
)
from api.miniapp_routes import (
    share_to_library as miniapp_share_to_library,
)
from api.miniapp_routes import (
    topup_crypto as miniapp_topup_crypto,
)
from api.miniapp_routes import (
    topup_lava as miniapp_topup_lava,
)
from api.miniapp_routes import (
    topup_stars as miniapp_topup_stars,
)
from api.miniapp_routes import (
    topup_tbank as miniapp_topup_tbank,
)
from api.miniapp_routes import (
    topup_tribute as miniapp_topup_tribute,
)
from api.miniapp_routes import (
    verify_suno_voice as miniapp_verify_suno_voice,
)
from api.public_files import save_public_file
from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import GenerationCard
from db import repository as repo
from db.session import get_session

router = APIRouter(tags=["web"])

MAX_WEB_REFERENCE_IMAGE_BYTES = 20 * 1024 * 1024
MAX_WEB_REFERENCE_VIDEO_BYTES = 200 * 1024 * 1024


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


def _handler_accepts_kwarg(handler, name: str) -> bool:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return False
    return name in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


async def _call_miniapp(handler, *args, surface: str | None = None, **kwargs) -> dict | Response:
    if surface and _handler_accepts_kwarg(handler, "surface"):
        kwargs["surface"] = surface
    try:
        return ok(_dump(await handler(*args, **kwargs)))
    except HTTPException as exc:
        return error_response(exc.status_code, str(exc.detail))


def _auth_required(user):
    if user is None:
        return error_response(401, "Authentication required")
    return None


def _looks_like_reference_video(data: bytes, content_type: str | None) -> bool:
    content = (content_type or "").lower()
    if content and content.startswith("video/"):
        return True
    return (
        (len(data) > 12 and data[4:8] == b"ftyp")
        or data.startswith(b"\x1a\x45\xdf\xa3")
        or (data.startswith(b"RIFF") and b"WEBP" not in data[:16])
    )


def _file_upload_error_or_kind(data: bytes, content_type: str | None) -> tuple[str | None, str | None]:
    if _is_supported_reference_image(data, content_type):
        if len(data) > MAX_WEB_REFERENCE_IMAGE_BYTES:
            return "File too large (max 20 MB)", None
        return None, "image"
    if _looks_like_reference_video(data, content_type):
        if len(data) > MAX_WEB_REFERENCE_VIDEO_BYTES:
            return "File too large (max 200 MB)", None
        return None, "video"
    return "Only JPEG, PNG, WebP, MP4, MOV and WebM files are supported", None


@router.get("/models/image")
async def image_models(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_list_image_models, session=session, user=user)


@router.get("/models/video")
async def video_models(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_list_video_models, session=session, user=user)


@router.get("/models/music")
async def music_models(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_list_music_models, session=session, user=user)


@router.post("/generate/image", status_code=202)
async def generate_image(
    body: ImageGenRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_create_image_generation, body=body, session=session, user=user, surface="web")


@router.post("/generate/video", status_code=202)
async def generate_video(
    body: VideoGenRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_create_video_generation, body=body, session=session, user=user, surface="web")


@router.post("/generate/music", status_code=202)
async def generate_music(
    body: MusicGenRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_create_music_generation, body=body, session=session, user=user, surface="web")


@router.get("/music/voices")
async def suno_voices(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_list_suno_voices, session=session, user=user)


@router.post("/music/voices", status_code=202)
async def create_suno_voice(
    file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=128),
    description: str | None = Form(default=None, max_length=1000),
    style: str | None = Form(default=None, max_length=256),
    language: str = Form(default="en", max_length=8),
    vocal_start_s: float = Form(default=0.0),
    vocal_end_s: float = Form(default=10.0),
    singer_skill_level: str | None = Form(default=None, max_length=32),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(
        miniapp_create_suno_voice,
        file=file,
        name=name,
        description=description,
        style=style,
        language=language,
        vocal_start_s=vocal_start_s,
        vocal_end_s=vocal_end_s,
        singer_skill_level=singer_skill_level,
        session=session,
        user=user,
    )


@router.post("/music/voices/{voice_id}/refresh")
async def refresh_suno_voice(
    voice_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_refresh_suno_voice, voice_id=voice_id, session=session, user=user)


@router.post("/music/voices/{voice_id}/verify", status_code=202)
async def verify_suno_voice(
    voice_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(
        miniapp_verify_suno_voice,
        voice_id=voice_id,
        file=file,
        session=session,
        user=user,
    )


@router.get("/generations/active")
async def active_generations(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    await _reconcile_user_active_generations(session, user.id)
    items = await repo.get_user_active_generations(session, user.id)
    image_sessions = await repo.get_image_sessions_by_ids(
        session,
        [int(getattr(item, "image_session_id", 0) or 0) for item in items],
    )
    return ok([
        GenerationCard.from_generation(
            item,
            image_session=image_sessions.get(int(getattr(item, "image_session_id", 0) or 0)),
        ).model_dump()
        for item in items
    ])


@router.get("/generations/{generation_id}/download")
async def generation_download(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    generation = await repo.get_generation_by_id(session, generation_id)
    if generation is None or int(getattr(generation, "user_id", 0) or 0) != int(user.id):
        return error_response(404, "Generation not found")
    result_url = GenerationCard.from_generation(generation).result_url
    if not result_url:
        return error_response(409, "Result is not ready yet")

    parsed = urlparse(result_url)
    filename = parsed.path.rsplit("/", 1)[-1] or f"generation-{generation_id}"
    if "." not in filename:
        ext = mimetypes.guess_extension(getattr(generation, "mime_type", None) or "") or ".bin"
        filename = f"generation-{generation_id}{ext}"

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            remote = await client.get(result_url)
            remote.raise_for_status()
    except httpx.HTTPError:
        return error_response(502, "Could not fetch generated file")

    media_type = remote.headers.get("content-type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(
        content=remote.content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/generations/{generation_id}")
async def generation_detail(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    generation = await repo.get_generation_by_id(session, generation_id)
    if generation is None or int(getattr(generation, "user_id", 0) or 0) != int(user.id):
        return error_response(404, "Generation not found")
    image_session = None
    if getattr(generation, "image_session_id", None):
        image_session = await repo.get_image_session(session, int(generation.image_session_id), user_id=user.id)
    return ok(GenerationCard.from_generation(generation, image_session=image_session).model_dump())


@router.post("/generations/{generation_id}/share")
async def share_generation(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_share_generation, gen_id=generation_id, session=session, user=user)


@router.post("/generations/{generation_id}/publish")
async def publish_generation(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_publish_generation, gen_id=generation_id, session=session, user=user)


@router.post("/generations/{generation_id}/share-library")
async def share_generation_to_library(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_share_to_library, gen_id=generation_id, session=session, user=user)


@router.post("/generations/{generation_id}/remove-library")
async def remove_generation_from_library(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_remove_from_library, gen_id=generation_id, session=session, user=user)


@router.post("/feed/{generation_id}/remove")
async def remove_feed_generation(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_remove_feed_post, gen_id=generation_id, session=session, user=user)


@router.post("/feed/{generation_id}/remix", status_code=202)
async def remix_feed_generation(
    generation_id: int,
    body: FeedRemixRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_remix_feed_post, gen_id=generation_id, body=body, session=session, user=user, surface="web")


@router.get("/feed/{generation_id}/link")
async def feed_share_link(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_get_feed_share_link, gen_id=generation_id, session=session, user=user)


async def _save_uploaded_generation_media(file: UploadFile, user) -> dict | Response:
    if auth_error := _auth_required(user):
        return auth_error
    data = await file.read()
    if not data:
        return error_response(422, "Empty file")
    error, media_kind = _file_upload_error_or_kind(data, file.content_type)
    if error:
        return error_response(413 if "too large" in error.lower() else 422, error)
    url = save_public_file(data, file.content_type, subdir="miniapp")
    return ok({"url": url, "kind": media_kind, "content_type": file.content_type, "size": len(data)})


@router.post("/upload-media")
async def upload_media(
    file: UploadFile = File(...),
    user=Depends(get_web_user_or_none),
):
    return await _save_uploaded_generation_media(file, user)


@router.post("/uploads/reference")
async def upload_reference(
    file: UploadFile = File(...),
    user=Depends(get_web_user_or_none),
):
    return await _save_uploaded_generation_media(file, user)


@router.post("/photo-prompt")
async def photo_prompt(
    file: UploadFile = File(...),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_photo_prompt, file=file, user=user)


@router.post("/prompt/improve")
async def improve_prompt(
    body: PromptImproveRequest,
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_improve_prompt, body=body, user=user)


@router.get("/billing/plans")
async def billing_plans(
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    return await _call_miniapp(miniapp_list_plans, response=response, session=session)


@router.get("/billing/payment-methods")
async def billing_payment_methods(
    session: AsyncSession = Depends(get_session),
):
    return await _call_miniapp(miniapp_list_payment_methods, session=session)


@router.get("/billing/payment-options")
async def billing_payment_options(
    session: AsyncSession = Depends(get_session),
):
    return await _call_miniapp(miniapp_list_payment_options, session=session)


@router.post("/billing/topup/tbank")
async def topup_tbank(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_topup_tbank, body=body, session=session, user=user)


@router.post("/billing/topup/stars")
async def topup_stars(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_topup_stars, body=body, session=session, user=user)


@router.post("/billing/topup/crypto")
async def topup_crypto(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_topup_crypto, body=body, session=session, user=user)


@router.post("/billing/topup/tribute")
async def topup_tribute(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_topup_tribute, body=body, session=session, user=user)


@router.post("/billing/topup/lava")
async def topup_lava(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    return await _call_miniapp(miniapp_topup_lava, body=body, session=session, user=user)
