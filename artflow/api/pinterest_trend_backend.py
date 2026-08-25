from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.image_service import MODEL_ASPECT_RATIOS, ImageModel
from api.pinterest_contract import (
    build_pinterest_contract,
    is_pinterest_prompt_source,
    pinterest_provider_context,
)
from api.public_files import local_upload_path_from_url

logger = logging.getLogger(__name__)

MIN_PINTEREST_REFERENCES = 2
MAX_PINTEREST_IDENTITY_ANGLES = 5
MAX_PINTEREST_REFERENCES = MIN_PINTEREST_REFERENCES + MAX_PINTEREST_IDENTITY_ANGLES
PINTEREST_MODEL = ImageModel.NANO_BANANA_PRO.value
PINTEREST_QUALITY = "2K"
PINTEREST_DEFAULT_RATIO = "9:16"
PINTEREST_SERVICE_ALIAS_ID = 0
PINTEREST_SERVICE_ID = "pinterest"
PINTEREST_SERVICE_TITLE = "Pinterest AI"
PINTEREST_SERVICE_DESCRIPTION = "Повторяй Pinterest-сцены со своей внешностью"
PINTEREST_SERVICE_BADGE = "Новинка"


class PinterestServiceRunRequest(BaseModel):
    reference_asset_ids: list[str] = Field(min_length=2, max_length=MAX_PINTEREST_REFERENCES)
    height_cm: int = Field(ge=120, le=230)
    weight_kg: int = Field(ge=30, le=250)
    confirmed: bool
    idempotency_key: str = Field(min_length=8, max_length=128)


# Backward-compatible symbol for older tests/imports while the public product is
# now a service and no longer needs a trend id to launch.
PinterestTrendRunRequest = PinterestServiceRunRequest


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


def _scene_matched_ratio(scene_url: str, configured_ratio: str | None) -> str:
    """Best-effort scene aspect matching without making image probing a blocker."""
    fallback = str(configured_ratio or PINTEREST_DEFAULT_RATIO)
    path = local_upload_path_from_url(scene_url)
    if path is None or not path.exists():
        return fallback
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return fallback
    if width <= 0 or height <= 0:
        return fallback

    supported = list(MODEL_ASPECT_RATIOS.get(ImageModel.NANO_BANANA_PRO, []))
    target = width / height
    candidates = [item for item in supported if _ratio_value(item)]
    if not candidates:
        return fallback
    selected = min(candidates, key=lambda item: abs((_ratio_value(item) or target) - target))
    logger.info("Pinterest scene ratio resolved scene=%s size=%sx%s ratio=%s", scene_url, width, height, selected)
    return selected


async def _find_pinterest_service_trend(routes: Any, session: Any) -> Any:
    """Resolve the canonical hidden Pinterest recipe without public list pagination."""
    result = await session.execute(
        routes.select(routes.UserPrompt)
        .where(routes.UserPrompt.tags.any(routes.TREND_TAG))
        .order_by(routes.desc(routes.UserPrompt.created_at), routes.desc(routes.UserPrompt.id))
    )
    for trend in result.scalars().all():
        if routes.trend_is_public(trend) and is_pinterest_prompt_source(trend):
            return trend
    raise HTTPException(status_code=404, detail="Pinterest Flow пока не опубликован")


async def _resolve_pinterest_trend(routes: Any, session: Any, trend_id: int) -> Any:
    if trend_id == PINTEREST_SERVICE_ALIAS_ID:
        return await _find_pinterest_service_trend(routes, session)
    return await routes._get_public_trend(session, trend_id)


async def _service_price_credits(routes: Any, session: Any) -> float:
    model_cost = await routes.repo.resolve_image_model_cost(
        session,
        PINTEREST_MODEL,
        quality=PINTEREST_QUALITY,
    )
    if not model_cost or not getattr(model_cost, "is_active", True):
        raise HTTPException(status_code=503, detail="Pinterest service pricing is unavailable")
    return routes._credits_out(getattr(model_cost, "credits", 0))


async def _find_idempotent_service_run(
    routes: Any,
    session: Any,
    *,
    user_id: int,
    idempotency_key: str,
) -> Any | None:
    marker = json.dumps({"pinterest_service_run_key": idempotency_key}, separators=(",", ":"))[1:-1]
    result = await session.execute(
        routes.select(routes.Generation)
        .where(routes.Generation.user_id == user_id, routes.Generation.input_params.like(f"%{marker}%"))
        .order_by(routes.desc(routes.Generation.created_at), routes.desc(routes.Generation.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _patch_pinterest_run_snapshot(
    routes: Any,
    *,
    session: Any,
    generation_id: int,
    idempotency_key: str,
    asset_ids: list[str],
    strict: bool,
    source: str,
) -> None:
    generation = await routes.repo.get_generation_by_id(session, generation_id)
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
            "pinterest_reference_asset_ids": list(asset_ids),
            "pinterest_manual_confirm": bool(strict),
            "prompt_hidden": True,
            "prompt_actions_allowed": False,
            "feed_prompt_visible": False,
        }
    )
    if source == "service":
        payload.update(
            {
                "source": "service",
                "service_id": PINTEREST_SERVICE_ID,
                "pinterest_service_run_key": idempotency_key,
            }
        )
        payload.pop("trend_run_key", None)
    else:
        payload["trend_run_key"] = idempotency_key
    generation.input_params = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    await session.commit()


async def _launch_pinterest(
    routes: Any,
    *,
    trend: Any,
    reference_urls: list[str],
    reference_asset_ids: list[str],
    height_cm: int | None,
    weight_kg: int | None,
    confirmed: bool,
    idempotency_key: str,
    session: Any,
    user: Any,
    strict: bool,
    source: str = "trend",
) -> dict[str, Any]:
    if not is_pinterest_prompt_source(trend):
        raise HTTPException(status_code=422, detail="Этот шаблон не является Pinterest-сервисом")
    if routes.trend_kind(trend) != "image":
        raise HTTPException(status_code=422, detail="Pinterest доступен только для фото")
    if strict and confirmed is not True:
        raise HTTPException(status_code=422, detail="Подтвердите генерацию кнопкой «Создать»")

    references = _dedupe(reference_urls)
    if len(references) != len(reference_urls):
        raise HTTPException(status_code=422, detail="Не добавляйте одно и то же фото несколько раз")
    if len(references) < MIN_PINTEREST_REFERENCES or len(references) > MAX_PINTEREST_REFERENCES:
        raise HTTPException(
            status_code=422,
            detail="Загрузите сцену, ваше фото и при желании до 5 дополнительных ракурсов",
        )
    if references[0] == references[1]:
        raise HTTPException(status_code=422, detail="Сцена и ваше фото должны быть разными")

    # The product contract deliberately locks Pinterest to Banana Pro.
    # Fail closed instead of silently running another provider/model contract.
    if str(getattr(trend, "model", "") or "") != PINTEREST_MODEL:
        raise HTTPException(
            status_code=409,
            detail="Pinterest service must be configured with Nano Banana Pro",
        )
    await routes._validated_model(session, PINTEREST_MODEL, "image")

    if source == "service":
        existing = await _find_idempotent_service_run(
            routes,
            session,
            user_id=user.id,
            idempotency_key=idempotency_key,
        )
    else:
        existing = await routes._find_idempotent_trend_run(
            session,
            user_id=user.id,
            idempotency_key=idempotency_key,
        )
    if existing is not None:
        await session.refresh(user)
        return {
            "ok": True,
            "task": routes._task_payload(routes.GenerationOut.model_validate(existing, from_attributes=True)),
            "credits": routes._credits_out(user.credits),
        }

    scene_reference = references[0]
    identity_reference = references[1]
    identity_evidence = references[2:]
    settings_payload = routes.trend_settings(trend)
    ratio = _scene_matched_ratio(scene_reference, settings_payload.get("ratio"))
    contract = build_pinterest_contract(
        scene_reference=scene_reference,
        identity_reference=identity_reference,
        identity_evidence=identity_evidence,
        trend_id=int(trend.id),
        height_cm=height_cm,
        weight_kg=weight_kg,
        confirmed=confirmed,
    )
    if source == "service":
        contract.update(
            {
                "source": "service",
                "service_id": PINTEREST_SERVICE_ID,
                "service_recipe_id": int(trend.id),
            }
        )
        contract.pop("trend_id", None)

    # Import dynamically so this always uses the Mini App function after all
    # API bootstrap wrappers (prompt privacy + Pinterest provider contract).
    from api import miniapp_routes

    request_body = miniapp_routes.ImageGenRequest(
        model=PINTEREST_MODEL,
        prompt="Использовать скрытый Pinterest-сценарий",
        prompt_id=int(trend.id),
        aspect_ratio=ratio,
        quality=PINTEREST_QUALITY,
        count=1,
        reference_url=identity_reference,
        reference_urls=[scene_reference],
    )
    with pinterest_provider_context(contract):
        task = await miniapp_routes.create_image_generation(
            body=request_body,
            session=session,
            user=user,
            surface="web",
        )

    await _patch_pinterest_run_snapshot(
        routes,
        session=session,
        generation_id=int(task.id),
        idempotency_key=idempotency_key,
        asset_ids=reference_asset_ids,
        strict=strict,
        source=source,
    )
    await session.refresh(user)
    return {
        "ok": True,
        "task": routes._task_payload(task),
        "credits": routes._credits_out(user.credits),
    }


def _remove_route(router: Any, path: str, method: str) -> None:
    for route in list(router.routes):
        if getattr(route, "path", None) == path and method.upper() in (getattr(route, "methods", None) or set()):
            router.routes.remove(route)


def install_pinterest_trend_backend(routes: Any) -> None:
    """Install the Pinterest service plus legacy trend compatibility routes."""
    if getattr(routes, "_pinterest_trend_backend_installed", False):
        return

    original_run = routes.run_trend
    generic_path = "/api/v1/trends/{trend_id}/run"
    _remove_route(routes.router, generic_path, "POST")

    async def get_pinterest_service(
        session=Depends(routes.get_session),
        user=Depends(routes.get_miniapp_user),
    ) -> dict[str, Any]:
        del user
        await _find_pinterest_service_trend(routes, session)
        price_credits = await _service_price_credits(routes, session)
        return {
            "id": PINTEREST_SERVICE_ID,
            "title": PINTEREST_SERVICE_TITLE,
            "description": PINTEREST_SERVICE_DESCRIPTION,
            "badge": PINTEREST_SERVICE_BADGE,
            "price_credits": price_credits,
            "quality": PINTEREST_QUALITY,
            "max_identity_angles": MAX_PINTEREST_IDENTITY_ANGLES,
            "height_min_cm": 120,
            "height_max_cm": 230,
            "weight_min_kg": 30,
            "weight_max_kg": 250,
            "available": True,
        }

    routes.router.add_api_route(
        "/services/pinterest",
        get_pinterest_service,
        methods=["GET"],
        name="get_pinterest_service",
    )

    async def upload_pinterest_reference(
        file: UploadFile = File(...),
        user=Depends(routes.get_miniapp_user),
    ) -> routes.TrendUploadResponse:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=422, detail="Empty photo")
        if len(data) > routes.MAX_TREND_USER_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="Photo is too large (max 30 MB)")
        content_type = str(file.content_type or "application/octet-stream").split(";", 1)[0].lower()
        filename = str(file.filename or "photo")[:180]
        if not routes.image_kind_from_upload(data, content_type, filename):
            raise HTTPException(status_code=422, detail="Upload one JPEG, PNG, WebP, HEIC, HEIF or AVIF photo")
        url = routes.save_public_file(data, content_type, subdir="services/pinterest")
        asset_id = routes.sign_uploaded_asset(
            user_id=user.id,
            url=url,
            kind="image",
            filename=filename,
            content_type=content_type,
            size=len(data),
        )
        return routes.TrendUploadResponse(
            asset_id=asset_id,
            url=url,
            kind="image",
            filename=filename,
            content_type=content_type,
            size=len(data),
        )

    routes.router.add_api_route(
        "/services/pinterest/upload",
        upload_pinterest_reference,
        methods=["POST"],
        response_model=routes.TrendUploadResponse,
        name="upload_pinterest_reference",
    )

    async def run_pinterest_service(
        body: PinterestServiceRunRequest,
        session=Depends(routes.get_session),
        user=Depends(routes.get_miniapp_user),
    ) -> dict[str, Any]:
        if body.confirmed is not True:
            raise HTTPException(status_code=422, detail="Подтвердите генерацию кнопкой «Создать»")
        if len(set(body.reference_asset_ids)) != len(body.reference_asset_ids):
            raise HTTPException(status_code=422, detail="Не добавляйте одно и то же фото несколько раз")

        recipe = await _find_pinterest_service_trend(routes, session)
        assets: list[dict[str, Any]] = []
        for asset_id in body.reference_asset_ids:
            asset = routes.verify_uploaded_asset(asset_id, user_id=user.id, expected_kind="image")
            asset["asset_id"] = asset_id
            assets.append(asset)
        urls = [str(asset.get("url") or "").strip() for asset in assets]
        if any(not item for item in urls):
            raise HTTPException(status_code=422, detail="Дождитесь окончания загрузки всех фото")

        return await _launch_pinterest(
            routes,
            trend=recipe,
            reference_urls=urls,
            reference_asset_ids=list(body.reference_asset_ids),
            height_cm=body.height_cm,
            weight_kg=body.weight_kg,
            confirmed=True,
            idempotency_key=body.idempotency_key,
            session=session,
            user=user,
            strict=True,
            source="service",
        )

    routes.router.add_api_route(
        "/services/pinterest/run",
        run_pinterest_service,
        methods=["POST"],
        status_code=202,
        name="run_pinterest_service",
    )

    async def run_trend_with_pinterest_compat(
        trend_id: int,
        body: routes.TrendRunRequest,
        session=Depends(routes.get_session),
        user=Depends(routes.get_miniapp_user),
    ) -> dict[str, Any]:
        trend = await _resolve_pinterest_trend(routes, session, trend_id)
        if not is_pinterest_prompt_source(trend):
            return await original_run(trend_id=trend_id, body=body, session=session, user=user)

        # Legacy compatibility only. New clients use /services/pinterest/* and do
        # not depend on public trend ids or the generic trend runner.
        asset = routes.verify_uploaded_asset(body.asset_id, user_id=user.id, expected_kind="image")
        scene_url = str(getattr(trend, "preview_url", "") or "").strip()
        identity_url = str(asset.get("url") or "").strip()
        if not scene_url:
            raise HTTPException(status_code=409, detail="Pinterest scene reference is missing")
        if not identity_url:
            raise HTTPException(status_code=422, detail="Upload an identity reference first")
        return await _launch_pinterest(
            routes,
            trend=trend,
            reference_urls=[scene_url, identity_url],
            reference_asset_ids=[body.asset_id],
            height_cm=None,
            weight_kg=None,
            confirmed=False,
            idempotency_key=body.idempotency_key,
            session=session,
            user=user,
            strict=False,
            source="trend",
        )

    routes.router.add_api_route(
        "/trends/{trend_id}/run",
        run_trend_with_pinterest_compat,
        methods=["POST"],
        status_code=202,
        name="run_trend",
    )

    async def run_pinterest_trend(
        trend_id: int,
        body: PinterestTrendRunRequest,
        session=Depends(routes.get_session),
        user=Depends(routes.get_miniapp_user),
    ) -> dict[str, Any]:
        if body.confirmed is not True:
            raise HTTPException(status_code=422, detail="Подтвердите генерацию кнопкой «Создать»")
        if len(set(body.reference_asset_ids)) != len(body.reference_asset_ids):
            raise HTTPException(status_code=422, detail="Не добавляйте одно и то же фото несколько раз")

        trend = await _resolve_pinterest_trend(routes, session, trend_id)
        assets: list[dict[str, Any]] = []
        for asset_id in body.reference_asset_ids:
            asset = routes.verify_uploaded_asset(asset_id, user_id=user.id, expected_kind="image")
            asset["asset_id"] = asset_id
            assets.append(asset)
        urls = [str(asset.get("url") or "").strip() for asset in assets]
        if any(not item for item in urls):
            raise HTTPException(status_code=422, detail="Дождитесь окончания загрузки всех фото")

        return await _launch_pinterest(
            routes,
            trend=trend,
            reference_urls=urls,
            reference_asset_ids=list(body.reference_asset_ids),
            height_cm=body.height_cm,
            weight_kg=body.weight_kg,
            confirmed=True,
            idempotency_key=body.idempotency_key,
            session=session,
            user=user,
            strict=True,
            source="trend",
        )

    routes.router.add_api_route(
        "/trends/{trend_id}/pinterest-run",
        run_pinterest_trend,
        methods=["POST"],
        status_code=202,
        name="run_pinterest_trend",
    )
    routes.PinterestServiceRunRequest = PinterestServiceRunRequest
    routes.PinterestTrendRunRequest = PinterestTrendRunRequest
    routes.PINTEREST_SERVICE_ALIAS_ID = PINTEREST_SERVICE_ALIAS_ID
    routes.PINTEREST_SERVICE_ID = PINTEREST_SERVICE_ID
    routes.get_pinterest_service = get_pinterest_service
    routes.upload_pinterest_reference = upload_pinterest_reference
    routes.run_pinterest_service = run_pinterest_service
    routes.run_pinterest_trend = run_pinterest_trend
    routes._pinterest_trend_backend_installed = True
