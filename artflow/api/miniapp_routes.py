"""Mini-app REST API — generation endpoints for the Telegram WebApp frontend."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api import image_service, video_service
from api.image_service import ImageModel
from api.miniapp_auth import get_miniapp_user
from api.video_service import VideoModel
from bot.keyboards.models import IMAGE_CAPS, VIDEO_CAPS, _KLING_PER_SEC
from core.config import settings
from db import repository as repo
from db.models import (
    GenerationType,
    ImageGenerationAction,
    User,
)

MUSIC_CREDITS = 20  # cost per music generation
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["miniapp"])

MAX_CONCURRENT = 6


# ── helpers ───────────────────────────────────────────────────────────────────

def _kie_callback_url() -> str:
    params = {}
    if settings.KIE_WEBHOOK_SECRET:
        params["secret"] = settings.KIE_WEBHOOK_SECRET
    qs = f"?{urlencode(params)}" if params else ""
    return f"{settings.WEBHOOK_URL.rstrip('/')}{settings.KIE_WEBHOOK_PATH}{qs}"


# ── schemas ───────────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    id: int
    tg_id: int
    username: str | None
    full_name: str | None
    credits: int
    referral_code: str
    referral_balance: float


class ModelInfo(BaseModel):
    key: str
    display_name: str
    credits: int
    modes: list[str]
    aspect_ratios: list[str]
    quality_options: list[dict[str, str]]
    counts: list[int]
    has_quality: bool
    is_per_second: bool = False
    credits_per_sec: int | None = None
    durations: list[int] = []
    resolutions: list[str] = []


class GenerationOut(BaseModel):
    id: int
    model: str
    gen_type: str
    prompt: str
    status: str
    result_url: str | None
    credits_spent: int
    created_at: str
    is_public_feed: bool = False
    is_prompt_library: bool = False


class ImageGenRequest(BaseModel):
    model: str
    prompt: str = Field(..., min_length=1, max_length=4000)
    aspect_ratio: str | None = None
    quality: str = "basic"
    count: int = Field(default=1, ge=1, le=6)
    reference_url: str | None = None
    reference_urls: list[str] = []


class VideoGenRequest(BaseModel):
    model: str
    prompt: str = Field(..., min_length=1, max_length=4000)
    mode: str = "text"                    # "text" | "image"
    duration: int = Field(default=5, ge=2, le=30)
    aspect_ratio: str | None = None
    resolution: str | None = None
    image_url: str | None = None
    grok_mode: str = "normal"


class PromptSubmitRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    description: str = Field(default="", max_length=500)
    prompt_text: str = Field(..., min_length=10, max_length=4000)
    category: str = "other"


class MusicGenRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    instrumental: bool = False


class TopupRequest(BaseModel):
    plan_key: str


# ── user ─────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserProfile)
async def get_me(user: User = Depends(get_miniapp_user)) -> UserProfile:
    """Current user profile with balance."""
    return UserProfile(
        id=user.id,
        tg_id=user.tg_id,
        username=user.username,
        full_name=user.full_name,
        credits=user.credits,
        referral_code=user.referral_code,
        referral_balance=user.referral_balance,
    )


# ── models ────────────────────────────────────────────────────────────────────

@router.get("/models/image", response_model=list[ModelInfo])
async def list_image_models(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> list[ModelInfo]:
    """All active image models with costs and capabilities."""
    model_costs = await repo.get_all_model_costs(session)
    image_keys = {m.value for m in ImageModel}
    result = []
    for mc in model_costs:
        if mc.model_key not in image_keys:
            continue
        caps: dict[str, Any] = IMAGE_CAPS.get(mc.model_key, {})
        quality_raw = caps.get("quality_options", [])
        result.append(ModelInfo(
            key=mc.model_key,
            display_name=mc.display_name,
            credits=mc.credits,
            modes=caps.get("modes", ["text"]),
            aspect_ratios=caps.get("aspect_ratios", []),
            quality_options=[{"value": v, "label": l} for v, l in quality_raw],
            counts=caps.get("counts", [1]),
            has_quality=bool(caps.get("has_quality")),
        ))
    return result


@router.get("/models/video", response_model=list[ModelInfo])
async def list_video_models(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> list[ModelInfo]:
    """All active video models with costs and capabilities."""
    model_costs = await repo.get_all_model_costs(session)
    video_keys = {m.value for m in VideoModel}
    result = []
    for mc in model_costs:
        if mc.model_key not in video_keys:
            continue
        caps: dict[str, Any] = VIDEO_CAPS.get(mc.model_key, {})
        kling_rates = _KLING_PER_SEC.get(mc.model_key, {})
        is_per_sec = bool(kling_rates)
        credits_per_sec = min(kling_rates.values()) if kling_rates else None
        result.append(ModelInfo(
            key=mc.model_key,
            display_name=mc.display_name,
            credits=credits_per_sec if is_per_sec else mc.credits,
            modes=caps.get("modes", ["text"]),
            aspect_ratios=caps.get("aspect_ratios", []),
            quality_options=[{"value": r, "label": r} for r in (caps.get("resolutions") or [])],
            counts=[],
            has_quality=bool(caps.get("has_resolution")),
            is_per_second=is_per_sec,
            credits_per_sec=credits_per_sec,
            durations=caps.get("duration_options", []),
            resolutions=caps.get("resolutions") or [],
        ))
    return result


# ── image generation ──────────────────────────────────────────────────────────

@router.post("/generate/image", response_model=GenerationOut, status_code=202)
async def create_image_generation(
    body: ImageGenRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """
    Start an async image generation.

    Returns immediately with `status: pending` and the generation `id`.
    Poll `GET /api/v1/generations/{id}` until `status` is `done` or `failed`.
    """
    try:
        model = ImageModel(body.model)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown image model: {body.model!r}")

    model_cost = await repo.resolve_image_model_cost(session, body.model, quality=body.quality)
    if not model_cost:
        raise HTTPException(status_code=422, detail="Model not available")

    if user.credits < model_cost.credits:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits: need {model_cost.credits}, have {user.credits}",
        )

    active = await repo.count_user_active_generations(session, user.id)
    if active >= MAX_CONCURRENT:
        raise HTTPException(status_code=429, detail="Too many concurrent generations")

    ok = await repo.spend_credits(session, user.id, model_cost.credits)
    if not ok:
        raise HTTPException(status_code=402, detail="Failed to spend credits")

    if body.reference_url and (body.reference_url.startswith("blob:") or not body.reference_url.startswith("http")):
        raise HTTPException(status_code=422, detail="Invalid reference URL — upload the image first")

    # Determine mode from reference presence
    has_ref = bool(body.reference_url)
    image_session = await repo.create_image_session(
        session=session,
        user_id=user.id,
        model=body.model,
        mode="image" if has_ref else "text",
        aspect_ratio=body.aspect_ratio,
        quality=body.quality,
        count=body.count,
        base_prompt=body.prompt,
        reference_url=body.reference_url,
    )

    gen = await repo.create_generation(
        session, user.id, body.model, GenerationType.image,
        body.prompt, model_cost.credits,
        image_session_id=image_session.id,
        action_type=ImageGenerationAction.initial,
    )

    # Merge reference_url + reference_urls into a single list
    ref_urls: str | list[str] | None = None
    all_refs = [u for u in ([body.reference_url] if body.reference_url else []) + list(body.reference_urls) if u and u.startswith("http")]
    if len(all_refs) == 1:
        ref_urls = all_refs[0]
    elif len(all_refs) > 1:
        ref_urls = all_refs

    try:
        result = await image_service.generate_image(
            model,
            body.prompt,
            image_url=ref_urls,
            aspect_ratio=body.aspect_ratio,
            n=body.count,
            quality=body.quality,
            callback_url=_kie_callback_url(),
        )
    except Exception as exc:
        logger.error("miniapp image gen error user=%s: %s", user.id, exc)
        await repo.fail_generation(session, gen.id, str(exc))
        await repo.add_credits(session, user.id, model_cost.credits)
        raise HTTPException(status_code=502, detail="Generation service error")

    await repo.update_generation_task(session, gen.id, result.task_id or "")
    await repo.update_image_session_last_prompt(session, image_session.id, body.prompt)

    await session.refresh(gen)
    return _gen_out(gen)


# ── video generation ──────────────────────────────────────────────────────────

@router.post("/generate/video", response_model=GenerationOut, status_code=202)
async def create_video_generation(
    body: VideoGenRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """
    Start an async video generation.

    Returns immediately with `status: pending`.
    Poll `GET /api/v1/generations/{id}` until done.
    """
    try:
        model = VideoModel(body.model)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown video model: {body.model!r}")

    model_cost = await repo.resolve_video_model_cost(
        session, body.model, duration=body.duration, resolution=body.resolution,
    )
    if not model_cost:
        raise HTTPException(status_code=422, detail="Model not available")

    if user.credits < model_cost.credits:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits: need {model_cost.credits}, have {user.credits}",
        )

    active = await repo.count_user_active_generations(session, user.id)
    if active >= MAX_CONCURRENT:
        raise HTTPException(status_code=429, detail="Too many concurrent generations")

    ok = await repo.spend_credits(session, user.id, model_cost.credits)
    if not ok:
        raise HTTPException(status_code=402, detail="Failed to spend credits")

    gen = await repo.create_generation(
        session, user.id, body.model, GenerationType.video,
        body.prompt, model_cost.credits,
    )

    image_url = body.image_url if body.mode == "image" else None
    if image_url and (image_url.startswith("blob:") or not image_url.startswith("http")):
        raise HTTPException(status_code=422, detail="Invalid image URL — upload the image first")

    try:
        result = await video_service.generate_video(
            model,
            body.prompt,
            image_url=image_url,
            duration=body.duration,
            aspect_ratio=body.aspect_ratio,
            resolution=body.resolution,
            grok_mode=body.grok_mode,
            callback_url=_kie_callback_url(),
        )
    except Exception as exc:
        logger.error("miniapp video gen error user=%s: %s", user.id, exc)
        await repo.fail_generation(session, gen.id, str(exc))
        await repo.add_credits(session, user.id, model_cost.credits)
        raise HTTPException(status_code=502, detail="Generation service error")

    await repo.update_generation_task(session, gen.id, result.task_id or "")

    await session.refresh(gen)
    return _gen_out(gen)


# ── music generation ──────────────────────────────────────────────────────────

@router.post("/generate/music", response_model=GenerationOut, status_code=202)
async def create_music_generation(
    body: MusicGenRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """Start Suno music generation. Returns immediately; poll /generations/{id}."""
    from api.music_service import create_music_task, register_miniapp_task

    if user.credits < MUSIC_CREDITS:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits: need {MUSIC_CREDITS}, have {user.credits}",
        )

    active = await repo.count_user_active_generations(session, user.id)
    if active >= MAX_CONCURRENT:
        raise HTTPException(status_code=429, detail="Too many concurrent generations")

    ok = await repo.spend_credits(session, user.id, MUSIC_CREDITS)
    if not ok:
        raise HTTPException(status_code=402, detail="Failed to spend credits")

    gen = await repo.create_generation(
        session, user.id, "suno/v4.5", GenerationType.music,
        body.prompt, MUSIC_CREDITS,
    )

    try:
        task_id = await create_music_task(body.prompt, body.instrumental)
    except Exception as exc:
        logger.error("miniapp music gen error user=%s: %s", user.id, exc)
        await repo.fail_generation(session, gen.id, str(exc))
        await repo.add_credits(session, user.id, MUSIC_CREDITS)
        raise HTTPException(status_code=502, detail="Music generation service error")

    await repo.update_generation_task(session, gen.id, task_id)
    register_miniapp_task(task_id, gen.id)

    await session.refresh(gen)
    return _gen_out(gen)


# ── generation status / history ───────────────────────────────────────────────

@router.get("/generations/{gen_id}", response_model=GenerationOut)
async def get_generation(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """Poll a single generation for status and result_url."""
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    return _gen_out(gen)


@router.get("/history", response_model=list[GenerationOut])
async def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[GenerationOut]:
    """Last N generations for the current user."""
    gens = await repo.get_user_history(session, user.id, limit=limit)
    return [_gen_out(g) for g in gens]


# ── feed ──────────────────────────────────────────────────────────────────────

@router.get("/feed")
async def get_feed(
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[dict]:
    """Public image feed — prompt is hidden from non-authors."""
    cards = await repo.get_feed_generations(session, limit=limit)
    return [
        {
            "id": c.generation.id,
            "model": c.generation.model,
            "result_url": c.generation.result_url,
            "likes_count": c.generation.likes_count,
            "shares_count": c.generation.shares_count,
            "aspect_ratio": c.aspect_ratio,
            "author": c.username or c.full_name or "anon",
            "is_mine": c.generation.user_id == user.id,
        }
        for c in cards
    ]


@router.post("/generations/{gen_id}/share", status_code=200)
async def share_generation(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Publish own generation to the public feed."""
    gen = await repo.share_to_feed(session, gen_id, user.id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found or not ready")
    return {"id": gen.id, "is_public_feed": gen.is_public_feed}


@router.post("/feed/{gen_id}/like", status_code=200)
async def like_feed_post(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> dict:
    gen = await repo.like_feed_generation(session, gen_id)
    if not gen:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"likes_count": gen.likes_count}


@router.post("/feed/{gen_id}/remix", response_model=GenerationOut, status_code=202)
async def remix_feed_post(
    gen_id: int,
    body: VideoGenRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """
    Start a generation using the hidden prompt of a public feed post.
    The user chooses model/params; the original author's prompt is used silently.
    """
    source = await repo.get_public_feed_generation(session, gen_id)
    if not source:
        raise HTTPException(status_code=404, detail="Post not found or not public")

    # Use the source prompt but with the user-chosen model
    try:
        model = VideoModel(body.model)
        gen_type = "video"
    except ValueError:
        try:
            img_model = ImageModel(body.model)
            gen_type = "image"
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown model: {body.model!r}")

    model_cost = await repo.resolve_video_model_cost(session, body.model, duration=body.duration, resolution=body.resolution) \
        if gen_type == "video" else await repo.resolve_image_model_cost(session, body.model, quality=body.quality or "basic")
    if not model_cost:
        raise HTTPException(status_code=422, detail="Model not available")

    if user.credits < model_cost.credits:
        raise HTTPException(status_code=402, detail=f"Insufficient credits: need {model_cost.credits}")

    active = await repo.count_user_active_generations(session, user.id)
    if active >= MAX_CONCURRENT:
        raise HTTPException(status_code=429, detail="Too many concurrent generations")

    ok = await repo.spend_credits(session, user.id, model_cost.credits)
    if not ok:
        raise HTTPException(status_code=402, detail="Failed to spend credits")

    from db.models import GenerationType as GT
    gen_type_enum = GT.video if gen_type == "video" else GT.image
    gen = await repo.create_generation(
        session, user.id, body.model, gen_type_enum,
        source.prompt, model_cost.credits,
        source_feed_gen_id=gen_id,
    )

    try:
        if gen_type == "video":
            result = await video_service.generate_video(
                model, source.prompt,
                image_url=body.image_url if body.mode == "image" else None,
                duration=body.duration, aspect_ratio=body.aspect_ratio,
                resolution=body.resolution, grok_mode=body.grok_mode,
                callback_url=_kie_callback_url(),
            )
        else:
            result = await image_service.generate_image(
                img_model, source.prompt,
                image_url=body.image_url if body.mode == "image" else None,
                aspect_ratio=body.aspect_ratio, n=1,
                quality=body.quality or "basic",
                callback_url=_kie_callback_url(),
            )
    except Exception as exc:
        logger.error("feed remix error user=%s gen=%s: %s", user.id, gen_id, exc)
        await repo.fail_generation(session, gen.id, str(exc))
        await repo.add_credits(session, user.id, model_cost.credits)
        raise HTTPException(status_code=502, detail="Generation service error")

    await repo.update_generation_task(session, gen.id, result.task_id or "")
    await repo.increment_feed_share(session, gen_id)
    await session.refresh(gen)
    return _gen_out(gen)


@router.get("/feed/{gen_id}/link")
async def get_feed_share_link(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Returns a shareable Telegram deeplink for this public post. Only the author can get it."""
    from db.models import GenerationStatus
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    if not gen.is_public_feed:
        raise HTTPException(status_code=400, detail="Generation is not public yet — share to feed first")
    from core.config import settings
    bot_username = settings.BOT_USERNAME if hasattr(settings, "BOT_USERNAME") else "apixbot"
    link = f"https://t.me/{bot_username}?start=feed_{gen_id}"
    return {"link": link, "gen_id": gen_id}


@router.post("/generations/{gen_id}/share-library", status_code=200)
async def share_to_library(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Opt this generation's prompt into the public prompt library."""
    gen = await repo.share_to_library(session, gen_id, user.id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found or not ready")
    return {"id": gen.id, "is_prompt_library": gen.is_prompt_library}


# ── prompt library ────────────────────────────────────────────────────────────

@router.get("/prompts")
async def list_prompts(
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> dict:
    """Paginated list of approved prompts. Optionally filter by category."""
    from db.prompt_repository import get_approved_prompts, count_approved_prompts
    from db.models import PromptCategory

    cat = None
    if category:
        try:
            cat = PromptCategory(category)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown category: {category!r}")

    prompts = await get_approved_prompts(session, category=cat, limit=limit, offset=(page - 1) * limit)
    total = await count_approved_prompts(session, category=cat)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [_prompt_out(p) for p in prompts],
    }


@router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> dict:
    from db.prompt_repository import get_prompt_by_id
    p = await get_prompt_by_id(session, prompt_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _prompt_out(p)


@router.post("/prompts", status_code=201)
async def submit_prompt(
    body: PromptSubmitRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Submit a new prompt for moderation."""
    from db.prompt_repository import create_prompt
    from db.models import PromptCategory

    try:
        cat = PromptCategory(body.category)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown category: {body.category!r}")

    p = await create_prompt(
        session,
        user.id,
        body.title,
        body.description,
        cat,
        body.prompt_text,
    )
    return {"id": p.id, "status": p.status.value, "message": "Submitted for moderation"}


# ── payments ──────────────────────────────────────────────────────────────────

@router.get("/plans")
async def list_plans(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> list[dict]:
    """Active price plans."""
    plans = await repo.get_active_price_plans(session)
    return [
        {
            "key": p.key,
            "title": p.title,
            "credits": p.credits,
            "price_rub": p.price_rub,
            "price_usdt": round(p.price_rub / 90, 2),  # approximate
        }
        for p in plans
    ]


@router.post("/topup/tbank")
async def topup_tbank(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Create a T-Bank payment invoice. Returns `pay_url` to redirect the user."""
    from payments.tbank import create_payment as tbank_create_payment
    from db.models import PaymentProvider

    plan = await repo.get_price_plan_by_key(session, body.plan_key)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    try:
        payment = await tbank_create_payment(plan, user.id)
    except Exception as exc:
        logger.error("T-Bank invoice error user=%s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail="Payment service error")

    tx = await repo.create_transaction(
        session=session,
        user_id=user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.tbank,
        external_id=payment.payment_id,
    )

    return {"pay_url": payment.payment_url, "transaction_id": tx.id, "credits": plan.credits, "amount_rub": plan.price_rub}


@router.post("/topup/crypto")
async def topup_crypto(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Create a CryptoBot invoice. Returns `pay_url` to open in CryptoBot."""
    from payments.cryptobot import create_invoice as crypto_create_invoice
    from db.models import PaymentProvider

    plan = await repo.get_price_plan_by_key(session, body.plan_key)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    usdt_amount = round(plan.price_rub / 90, 2)
    try:
        invoice = await crypto_create_invoice(
            credits=plan.credits,
            amount_usd=usdt_amount,
            plan_key=plan.key,
            user_id=user.id,
        )
    except Exception as exc:
        logger.error("CryptoBot invoice error user=%s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail="Payment service error")

    tx = await repo.create_transaction(
        session=session,
        user_id=user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.cryptobot,
        external_id=str(invoice.invoice_id),
    )

    return {"pay_url": invoice.pay_url, "transaction_id": tx.id, "credits": plan.credits, "amount_usdt": usdt_amount}


# ── serializers ───────────────────────────────────────────────────────────────

def _gen_out(gen) -> GenerationOut:
    return GenerationOut(
        id=gen.id,
        model=gen.model,
        gen_type=gen.gen_type.value,
        prompt=gen.prompt,
        status=gen.status.value,
        result_url=gen.result_url,
        credits_spent=gen.credits_spent,
        created_at=gen.created_at.isoformat() if gen.created_at else "",
        is_public_feed=bool(gen.is_public_feed),
        is_prompt_library=bool(getattr(gen, "is_prompt_library", False)),
    )


def _prompt_out(p) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description or "",
        "prompt_text": p.prompt_text,
        "category": p.category.value if p.category else "other",
        "tags": p.tags or [],
        "uses_count": p.uses_count,
        "likes": p.likes,
        "preview_url": p.preview_url,
        "model": p.model,
        "author_id": p.author_id,
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }
