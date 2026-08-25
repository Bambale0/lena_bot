from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.image_service import MODEL_ASPECT_RATIOS, ImageModel
from api.miniapp_auth import get_miniapp_user
from api.pinterest_service_contract import (
    DISPLAY_PROMPT,
    PINTEREST_SERVICE_ID,
    build_pinterest_service_contract,
    pinterest_service_provider_context,
)
from api.public_files import local_upload_path_from_url, save_public_file
from api.trend_assets import image_kind_from_upload, sign_uploaded_asset, verify_uploaded_asset
from db import repository as repo
from db.models import Generation, GenerationType, User
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services/pinterest", tags=["services", "pinterest"])

MIN_PINTEREST_REFERENCES = 2
MAX_PINTEREST_IDENTITY_ANGLES = 5
MAX_PINTEREST_REFERENCES = MIN_PINTEREST_REFERENCES + MAX_PINTEREST_IDENTITY_ANGLES
MAX_PINTEREST_UPLOAD_BYTES = 30 * 1024 * 1024
PINTEREST_MODEL = ImageModel.NANO_BANANA_PRO.value
PINTEREST_QUALITY = "2K"
PINTEREST_DEFAULT_RATIO = "9:16"
PINTEREST_SERVICE_TITLE = "Pinterest AI"
PINTEREST_SERVICE_DESCRIPTION = "Повторяй Pinterest-сцены со своей внешностью"
PINTEREST_SERVICE_BADGE = "Новинка"
PINTEREST_RECIPE_VERSION = "pinterest-service-v1"
PINTEREST_PRIVATE_RECIPE = (
    "Create a photorealistic recreation of the source photograph using the provided user as the "
    "subject. Recreate the scene, pose, framing, camera perspective, lighting, shadows, background, "
    "wardrobe silhouette and mood from SCENE_REFERENCE while preserving the exact recognizable "
    "identity of USER_IDENTITY_REFERENCE. No text, no collage, no split-screen, no watermark."
)


class PinterestServiceRunRequest(BaseModel):
    reference_asset_ids: list[str] = Field(min_length=2, max_length=MAX_PINTEREST_REFERENCES)
    height_cm: int = Field(ge=120, le=230)
    weight_kg: int = Field(ge=30, le=250)
    confirmed: bool
    idempotency_key: str = Field(min_length=8, max_length=128)


class PinterestUploadResponse(BaseModel):
    asset_id: str
    url: str
    kind: str
    filename: str
    content_type: str
    size: int


def _credits_out(value: float | int | None) -> float:
    return round(float(value or 0), 2)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _ratio_value(value: str | None) -> float | None:
    text = str(value or "").strip().lower()
    if ":" not in text:
        return None
    left, right = text.split(":", 1)
    try:
        width = float(left)
        height = float(right)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width / height


def _scene_matched_ratio(scene_url: str) -> str:
    """Best-effort output ratio matching against the uploaded Pinterest scene."""
    path = local_upload_path_from_url(scene_url)
    if path is None or not path.exists():
        return PINTEREST_DEFAULT_RATIO
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return PINTEREST_DEFAULT_RATIO
    if width <= 0 or height <= 0:
        return PINTEREST_DEFAULT_RATIO

    supported = list(MODEL_ASPECT_RATIOS.get(ImageModel.NANO_BANANA_PRO, []))
    target = width / height
    candidates = [item for item in supported if _ratio_value(item)]
    if not candidates:
        return PINTEREST_DEFAULT_RATIO
    selected = min(candidates, key=lambda item: abs((_ratio_value(item) or target) - target))
    logger.info("Pinterest service ratio resolved scene=%s size=%sx%s ratio=%s", scene_url, width, height, selected)
    return selected


async def _validate_runtime(session: AsyncSession) -> None:
    model = await repo.get_model_cost(session, PINTEREST_MODEL)
    if not model or not getattr(model, "is_active", True):
        raise HTTPException(status_code=503, detail="Pinterest AI временно недоступен")
    if getattr(model, "gen_type", None) != GenerationType.image:
        raise HTTPException(status_code=503, detail="Pinterest AI model contract is invalid")


async def _service_price_credits(session: AsyncSession) -> float:
    model_cost = await repo.resolve_image_model_cost(
        session,
        PINTEREST_MODEL,
        quality=PINTEREST_QUALITY,
    )
    if not model_cost or not getattr(model_cost, "is_active", True):
        raise HTTPException(status_code=503, detail="Цена Pinterest AI временно недоступна")
    return _credits_out(getattr(model_cost, "credits", 0))


async def _find_idempotent_run(
    session: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
) -> Generation | None:
    marker = json.dumps({"pinterest_service_run_key": idempotency_key}, separators=(",", ":"))[1:-1]
    result = await session.execute(
        select(Generation)
        .where(Generation.user_id == user_id, Generation.input_params.like(f"%{marker}%"))
        .order_by(desc(Generation.created_at), desc(Generation.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


def _task_payload(task: Any) -> dict[str, Any]:
    payload = task.model_dump()
    payload["cost"] = payload.get("credits_spent", 0)
    payload["type"] = payload.get("gen_type")
    return payload


async def _patch_service_snapshot(
    session: AsyncSession,
    *,
    generation_id: int,
    idempotency_key: str,
    asset_ids: list[str],
    price_credits: float,
) -> None:
    generation = await repo.get_generation_by_id(session, generation_id)
    if generation is None:
        return
    try:
        payload = json.loads(generation.input_params or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.update(
        {
            "source": "service",
            "service_id": PINTEREST_SERVICE_ID,
            "service_recipe_version": PINTEREST_RECIPE_VERSION,
            "pinterest_service_run_key": idempotency_key,
            "pinterest_reference_asset_ids": list(asset_ids),
            "pinterest_manual_confirm": True,
            "service_price_credits": price_credits,
            "prompt_hidden": True,
            "prompt_actions_allowed": False,
            "feed_prompt_visible": False,
        }
    )
    payload.pop("trend_id", None)
    payload.pop("trend_run_key", None)
    payload.pop("service_recipe_id", None)
    generation.prompt = DISPLAY_PROMPT
    generation.input_params = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    await session.commit()


@router.get("")
async def get_pinterest_service(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    del user
    await _validate_runtime(session)
    price_credits = await _service_price_credits(session)
    return {
        "id": PINTEREST_SERVICE_ID,
        "title": PINTEREST_SERVICE_TITLE,
        "description": PINTEREST_SERVICE_DESCRIPTION,
        "badge": PINTEREST_SERVICE_BADGE,
        "price_credits": price_credits,
        "model": PINTEREST_MODEL,
        "quality": PINTEREST_QUALITY,
        "max_identity_angles": MAX_PINTEREST_IDENTITY_ANGLES,
        "height_min_cm": 120,
        "height_max_cm": 230,
        "weight_min_kg": 30,
        "weight_max_kg": 250,
        "available": True,
    }


@router.post("/upload", response_model=PinterestUploadResponse)
async def upload_pinterest_reference(
    file: UploadFile = File(...),
    user: User = Depends(get_miniapp_user),
) -> PinterestUploadResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Пустой файл")
    if len(data) > MAX_PINTEREST_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Фото слишком большое (максимум 30 МБ)")
    content_type = str(file.content_type or "application/octet-stream").split(";", 1)[0].lower()
    filename = str(file.filename or "photo")[:180]
    if not image_kind_from_upload(data, content_type, filename):
        raise HTTPException(status_code=422, detail="Загрузите JPEG, PNG, WebP, HEIC, HEIF или AVIF")
    url = save_public_file(data, content_type, subdir="services/pinterest")
    asset_id = sign_uploaded_asset(
        user_id=user.id,
        url=url,
        kind="image",
        filename=filename,
        content_type=content_type,
        size=len(data),
    )
    return PinterestUploadResponse(
        asset_id=asset_id,
        url=url,
        kind="image",
        filename=filename,
        content_type=content_type,
        size=len(data),
    )


@router.post("/run", status_code=202)
async def run_pinterest_service(
    body: PinterestServiceRunRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    if body.confirmed is not True:
        raise HTTPException(status_code=422, detail="Подтвердите генерацию кнопкой «Создать»")
    if len(set(body.reference_asset_ids)) != len(body.reference_asset_ids):
        raise HTTPException(status_code=422, detail="Не добавляйте одно и то же фото несколько раз")

    await _validate_runtime(session)
    price_credits = await _service_price_credits(session)

    existing = await _find_idempotent_run(
        session,
        user_id=user.id,
        idempotency_key=body.idempotency_key,
    )
    if existing is not None:
        from api import miniapp_routes

        await session.refresh(user)
        task = miniapp_routes.GenerationOut.model_validate(existing, from_attributes=True)
        return {
            "ok": True,
            "task": _task_payload(task),
            "credits": _credits_out(user.credits),
            "price_credits": price_credits,
        }

    assets: list[dict[str, Any]] = []
    for asset_id in body.reference_asset_ids:
        asset = verify_uploaded_asset(asset_id, user_id=user.id, expected_kind="image")
        assets.append(asset)
    references = _dedupe([str(asset.get("url") or "").strip() for asset in assets])
    if len(references) != len(assets):
        raise HTTPException(status_code=422, detail="Дождитесь загрузки всех фото и не дублируйте их")
    if len(references) < MIN_PINTEREST_REFERENCES or len(references) > MAX_PINTEREST_REFERENCES:
        raise HTTPException(
            status_code=422,
            detail="Загрузите Pinterest-референс, ваше фото и при желании до 5 дополнительных ракурсов",
        )
    if references[0] == references[1]:
        raise HTTPException(status_code=422, detail="Референс и ваше фото должны быть разными")

    scene_reference = references[0]
    identity_reference = references[1]
    identity_evidence = references[2:]
    ratio = _scene_matched_ratio(scene_reference)
    contract = build_pinterest_service_contract(
        scene_reference=scene_reference,
        identity_reference=identity_reference,
        identity_evidence=identity_evidence,
        height_cm=body.height_cm,
        weight_kg=body.weight_kg,
        confirmed=True,
    )
    contract["service_recipe_version"] = PINTEREST_RECIPE_VERSION
    contract["service_price_credits"] = price_credits

    # Import only at execution time. The API package mounts this router after
    # miniapp_routes finishes importing, so there is no package bootstrap cycle.
    from api import miniapp_routes

    request_body = miniapp_routes.ImageGenRequest(
        model=PINTEREST_MODEL,
        prompt=PINTEREST_PRIVATE_RECIPE,
        prompt_id=None,
        aspect_ratio=ratio,
        quality=PINTEREST_QUALITY,
        count=1,
        reference_url=scene_reference,
        reference_urls=[identity_reference, *identity_evidence],
    )
    with pinterest_service_provider_context(contract):
        task = await miniapp_routes.create_image_generation(
            body=request_body,
            session=session,
            user=user,
            # Pinterest is launched from the Mini App but its completed image and
            # lossless source file must still be delivered into the user's bot chat.
            # Only the legacy "web" surface prefixes task ids with web: and suppresses
            # Telegram completion delivery in main.py.
            surface="miniapp",
        )

    await _patch_service_snapshot(
        session,
        generation_id=int(task.id),
        idempotency_key=body.idempotency_key,
        asset_ids=list(body.reference_asset_ids),
        price_credits=price_credits,
    )
    await session.refresh(user)
    return {
        "ok": True,
        "task": _task_payload(task),
        "credits": _credits_out(user.credits),
        "price_credits": price_credits,
    }


def install_pinterest_service_router(parent_router: APIRouter) -> None:
    """Mount the standalone Pinterest Service on the shared /api/v1 router once."""
    if getattr(parent_router, "_pinterest_service_router_installed", False):
        return
    parent_router.include_router(router)
    parent_router._pinterest_service_router_installed = True
