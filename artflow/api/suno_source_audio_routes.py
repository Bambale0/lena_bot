"""Mini App routes for uploading and transforming a user's own audio with Suno."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.miniapp_auth import get_miniapp_user
from api.suno_source_audio import (
    SunoSourceOperation,
    create_source_audio_generation,
    upload_source_audio,
)
from db.session import get_session


class SunoSourceGenerationRequest(BaseModel):
    operation: SunoSourceOperation
    upload_url: str = Field(..., min_length=8, max_length=4000)
    prompt: str = Field(..., min_length=1, max_length=5000)
    model: str | None = None
    instrumental: bool = False
    style: str | None = Field(default=None, max_length=1000)
    title: str | None = Field(default=None, max_length=100)
    continue_at: float | None = Field(default=None, gt=0, le=480)
    source_duration: float | None = Field(default=None, gt=0, le=480)


def install_suno_source_audio_routes(routes: Any) -> None:
    if getattr(routes, "_suno_source_audio_routes_installed", False):
        return

    router = APIRouter(prefix="/music", tags=["miniapp", "suno"])

    @router.post("/source-audio", status_code=201)
    async def upload_source(
        file: UploadFile = File(...),
        user=Depends(get_miniapp_user),
    ) -> dict[str, Any]:
        del user
        data = await file.read()
        try:
            return await upload_source_audio(
                data,
                filename=file.filename,
                content_type=file.content_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            routes.logger.error("Suno source upload failed: %s", exc)
            raise HTTPException(status_code=502, detail="Suno audio upload failed") from exc

    @router.post("/from-audio", status_code=202)
    async def generate_from_source(
        body: SunoSourceGenerationRequest,
        session=Depends(get_session),
        user=Depends(get_miniapp_user),
        surface: str = "miniapp",
    ):
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
                surface=surface,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            if "concurrent" in str(exc).lower():
                raise HTTPException(status_code=429, detail=str(exc)) from exc
            routes.logger.error("Suno source generation failed user=%s: %s", user.id, exc)
            raise HTTPException(status_code=502, detail="Suno source-audio generation failed") from exc
        except Exception as exc:
            routes.logger.error("Suno source generation failed user=%s: %s", user.id, exc)
            raise HTTPException(status_code=502, detail="Suno source-audio generation failed") from exc
        return routes._gen_out(gen)

    routes.router.include_router(router)
    routes._suno_source_audio_routes_installed = True
    routes.SunoSourceGenerationRequest = SunoSourceGenerationRequest
