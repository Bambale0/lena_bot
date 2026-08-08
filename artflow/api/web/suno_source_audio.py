from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile

from api.suno_source_audio import create_source_audio_generation, upload_source_audio
from api.suno_source_audio_routes import SunoSourceGenerationRequest
from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import GenerationCard
from db.session import get_session

router = APIRouter(tags=["web", "suno"])


def _auth_required(user):
    if user is None:
        return error_response(401, "Authentication required")
    return None


@router.post("/music/source-audio", status_code=201)
async def upload_source(
    file: UploadFile = File(...),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    data = await file.read()
    try:
        return ok(
            await upload_source_audio(
                data,
                filename=file.filename,
                content_type=file.content_type,
            )
        )
    except ValueError as exc:
        return error_response(422, str(exc))
    except Exception:
        return error_response(502, "Suno audio upload failed")


@router.post("/music/from-audio", status_code=202)
async def generate_from_source(
    body: SunoSourceGenerationRequest,
    session=Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error
    try:
        gen = await create_source_audio_generation(
            session=session,
            user=user,
            operation=body.operation,
            upload_url=body.upload_url,
            prompt=body.prompt,
            model_key=body.model,
            instrumental=body.instrumental,
            style=body.style,
            title=body.title,
            continue_at=body.continue_at,
            source_duration=body.source_duration,
            surface="web",
        )
    except PermissionError as exc:
        return error_response(402, str(exc))
    except ValueError as exc:
        return error_response(422, str(exc))
    except RuntimeError as exc:
        if "concurrent" in str(exc).lower():
            return error_response(429, str(exc))
        return error_response(502, "Suno source-audio generation failed")
    except Exception:
        return error_response(502, "Suno source-audio generation failed")
    return ok(GenerationCard.from_generation(gen).model_dump())
